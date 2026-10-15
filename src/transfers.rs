//! Invocation-level scheduling and diagnostics; response state belongs to each transfer.
use crate::{
    body,
    cli::{CliError, Config, ExportMode},
    engine::{Session, Transfer},
    export::Aggregate,
};
use std::{
    collections::HashMap,
    ffi::{c_char, c_int, c_void, CStr},
    io::{self, Write},
    marker::PhantomData,
    ptr::NonNull,
};

extern "C" {
    fn ci_multi_new() -> *mut c_void;
    fn ci_multi_free(multi: *mut c_void);
    fn ci_multi_add(multi: *mut c_void, handle: *mut c_void) -> c_int;
    fn ci_multi_remove(multi: *mut c_void, handle: *mut c_void) -> c_int;
    fn ci_multi_perform(multi: *mut c_void) -> c_int;
    fn ci_multi_poll(multi: *mut c_void) -> c_int;
    fn ci_multi_next(multi: *mut c_void, code: *mut c_int) -> *mut c_void;
    fn ci_multi_error(code: c_int) -> *const c_char;
    fn ci_multi_exit_code(code: c_int) -> c_int;
}

fn check(code: i32) -> Result<(), CliError> {
    if code == 0 {
        return Ok(());
    }
    // libcurl owns this static error string; the bridge maps enum values using pinned headers.
    Err(CliError::new(unsafe { ci_multi_exit_code(code) }, unsafe {
        CStr::from_ptr(ci_multi_error(code))
            .to_string_lossy()
            .into_owned()
    }))
}

struct Multi<'a> {
    raw: NonNull<c_void>,
    active: HashMap<*mut c_void, Transfer>,
    session: PhantomData<&'a Session>,
}

impl<'a> Multi<'a> {
    fn new(_session: &'a Session) -> Result<Self, CliError> {
        Ok(Self {
            raw: NonNull::new(unsafe { ci_multi_new() })
                .ok_or_else(|| CliError::new(27, "cannot create transfer scheduler"))?,
            active: HashMap::new(),
            session: PhantomData,
        })
    }

    fn add(&mut self, transfer: Transfer) -> Result<(), CliError> {
        self.active
            .try_reserve(1)
            .map_err(|_| CliError::new(27, "cannot allocate transfer state"))?;
        check(unsafe { ci_multi_add(self.raw.as_ptr(), transfer.raw()) })?;
        self.active.insert(transfer.raw(), transfer);
        Ok(())
    }

    fn next(&mut self) -> Result<Option<(Transfer, i32)>, CliError> {
        let mut code = 0;
        let raw = unsafe { ci_multi_next(self.raw.as_ptr(), &mut code) };
        if raw.is_null() {
            return Ok(None);
        }
        // Leave ownership in active until native removal succeeds, including on errors.
        check(unsafe { ci_multi_remove(self.raw.as_ptr(), raw) })?;
        let transfer = self
            .active
            .remove(&raw)
            .ok_or_else(|| CliError::new(2, "unknown completed transfer"))?;
        Ok(Some((transfer, code)))
    }
}

impl Drop for Multi<'_> {
    fn drop(&mut self) {
        for transfer in self.active.values() {
            unsafe {
                ci_multi_remove(self.raw.as_ptr(), transfer.raw());
            }
        }
        // Multi cleanup may call callbacks. Retain every easy handle and its boxed state until afterward.
        unsafe {
            ci_multi_free(self.raw.as_ptr());
        }
        self.active.clear();
    }
}

pub(crate) fn report(config: &Config, mut error: CliError) -> CliError {
    if !config.silent || config.show_error {
        let _ = writeln!(
            io::stderr().lock(),
            "curlimp: ({}) {}",
            error.code,
            error.message
        );
    }
    error.reported = true;
    error
}

pub fn run(config: &Config) -> Result<(), CliError> {
    let prepared = body::prepare(config)?;
    let session = Session::new(config)?;
    let mut multi = Multi::new(&session)?;
    let mut aggregate = if config.urls.len() > 1 && config.export == Some(ExportMode::JsonOutput) {
        Some(
            Aggregate::new(config.urls.len())
                .map_err(|e| CliError::new(23, format!("creating JSON spool: {e}")))?,
        )
    } else {
        None
    };
    let mut export_error = None;
    if config.outputs.len() > config.urls.len() && !config.silent {
        let _ = writeln!(
            io::stderr().lock(),
            "Warning: Got more output options than URLs"
        );
    }
    let limit = if config.parallel {
        config.parallel_max.unwrap_or(50)
    } else {
        1
    };
    let mut pending = config.targets().peekable();
    let mut result = Ok(());
    loop {
        while multi.active.len() < limit {
            let Some(target) = pending.next() else {
                break;
            };
            let transfer = Transfer::prepare(config, &prepared, target, &session)?;
            multi.add(transfer)?;
        }
        if multi.active.is_empty() {
            break;
        }
        check(unsafe { ci_multi_perform(multi.raw.as_ptr()) })?;
        while let Some((mut transfer, code)) = multi.next()? {
            let current = transfer
                .complete(code, &prepared.format, aggregate.as_mut())
                .and_then(|result| result.error.map_or(Ok(()), Err))
                .map_err(|mut error| {
                    if config.urls.len() > 1 {
                        error.message =
                            format!("transfer {}: {}", transfer.index + 1, error.message);
                    }
                    report(config, error)
                });
            if config.export.is_some() {
                if let Err(error) = &current {
                    if error.code == 23 && export_error.is_none() {
                        export_error = Some(error.clone());
                    }
                }
            }
            let fatal = current
                .as_ref()
                .is_err_and(|error| matches!(error.code, 2 | 4 | 27));
            // curl serial returns the last result; parallel retains the first failure.
            if !config.parallel || result.is_ok() || fatal {
                result = current;
            }
            if fatal {
                return result;
            }
        }
        if pending.peek().is_some() && multi.active.len() < limit {
            continue;
        }
        if !multi.active.is_empty() {
            check(unsafe { ci_multi_poll(multi.raw.as_ptr()) })?;
        }
    }
    if let Some(error) = export_error {
        return Err(error);
    }
    if let Some(aggregate) = &mut aggregate {
        aggregate
            .finish(&mut io::stdout().lock())
            .map_err(|e| CliError::new(23, format!("writing JSON output: {e}")))?;
    }
    result
}
