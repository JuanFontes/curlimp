use crate::{
    body,
    cli::{CliError, Config, DataKind, TransferTarget},
    export::Export,
    writeout::Token,
};
use std::{
    cell::RefCell,
    ffi::{c_char, c_int, c_long, c_void, CStr, CString},
    fs::File,
    io::{self, Write},
    panic::{catch_unwind, AssertUnwindSafe},
    ptr::NonNull,
    rc::Rc,
    sync::OnceLock,
};

type Writer = unsafe extern "C" fn(*const u8, usize, *mut c_void) -> usize;
extern "C" {
    fn ci_global_init() -> c_int;
    fn ci_session_new(jar: *const c_char) -> *mut c_void;
    fn ci_session_free(session: *mut c_void);
    fn ci_session_attach(session: *mut c_void, handle: *mut c_void) -> c_int;
    fn ci_version() -> *const c_char;
    fn ci_new(body: Writer, header: Writer, state: *mut c_void) -> *mut c_void;
    fn ci_free(handle: *mut c_void);
    fn ci_string(handle: *mut c_void, name: *const c_char, value: *const c_char) -> c_int;
    fn ci_long(handle: *mut c_void, name: *const c_char, value: c_long) -> c_int;
    fn ci_header(handle: *mut c_void, value: *const c_char) -> c_int;
    fn ci_body(handle: *mut c_void, data: *const u8, len: usize) -> c_int;
    fn ci_perform(handle: *mut c_void) -> c_int;
    fn ci_error(handle: *mut c_void, code: c_int) -> *const c_char;
    fn ci_info_long(handle: *mut c_void, name: *const c_char) -> c_long;
    fn ci_info_string(handle: *mut c_void, name: *const c_char) -> *const c_char;
    fn ci_total_time(handle: *mut c_void) -> f64;
}

static INIT: OnceLock<i32> = OnceLock::new();

fn initialize() -> Result<(), CliError> {
    // libcurl initialization is process-wide and must precede handle creation.
    let code = *INIT.get_or_init(|| unsafe { ci_global_init() });
    if code == 0 {
        Ok(())
    } else {
        Err(CliError::new(code, "native engine initialization failed"))
    }
}

fn cstring(s: &str) -> Result<CString, CliError> {
    CString::new(s).map_err(|_| CliError::new(2, "an option contains a NUL byte"))
}

// Only called for non-null, NUL-terminated strings owned by live native handles.
unsafe fn text(ptr: *const c_char) -> String {
    if ptr.is_null() {
        String::new()
    } else {
        unsafe { CStr::from_ptr(ptr) }
            .to_string_lossy()
            .into_owned()
    }
}

pub fn version() -> Result<String, CliError> {
    initialize()?;
    Ok(unsafe { text(ci_version()) })
}

struct Output {
    export: Option<Export>,
    body: Box<dyn Write>,
    header: Option<Box<dyn Write>>,
    flush_chunks: bool,
    error: Option<String>,
}

unsafe fn receive(data: *const u8, len: usize, state: *mut c_void, header: bool) -> usize {
    if len == 0 {
        return 0;
    }
    // The C bridge invokes this synchronously during perform. Handle owns the
    // boxed state until AFTER curl_easy_cleanup and no callback runs concurrently.
    let output = unsafe { &mut *state.cast::<Output>() };
    let result = catch_unwind(AssertUnwindSafe(|| {
        let bytes = unsafe { std::slice::from_raw_parts(data, len) };
        if let Some(export) = &mut output.export {
            return export.receive(bytes, header, output.flush_chunks);
        }
        let writer: &mut dyn Write = if header {
            match output.header.as_mut() {
                Some(w) => w.as_mut(),
                None => return Ok(()),
            }
        } else {
            output.body.as_mut()
        };
        writer.write_all(bytes)?;
        if output.flush_chunks {
            writer.flush()?;
        }
        Ok::<(), io::Error>(())
    }));
    match result {
        Ok(Ok(())) => len,
        Ok(Err(e)) => {
            output.error = Some(e.to_string());
            0
        }
        Err(_) => {
            output.error = Some("output callback failed".into());
            0
        }
    }
}

unsafe extern "C" fn body_callback(data: *const u8, len: usize, state: *mut c_void) -> usize {
    unsafe { receive(data, len, state, false) }
}

unsafe extern "C" fn header_callback(data: *const u8, len: usize, state: *mut c_void) -> usize {
    unsafe { receive(data, len, state, true) }
}

struct Handle {
    raw: NonNull<c_void>,
    output: Box<Output>,
}

impl Handle {
    fn new(output: Output) -> Result<Self, CliError> {
        initialize()?;
        let mut output = Box::new(output);
        let raw = unsafe {
            ci_new(
                body_callback,
                header_callback,
                (&mut *output as *mut Output).cast(),
            )
        };
        let raw = NonNull::new(raw).ok_or_else(|| {
            CliError::new(2, "cannot create native handle; check engine installation")
        })?;
        Ok(Self { raw, output })
    }

    fn check(&self, code: i32) -> Result<(), CliError> {
        if code == 0 {
            Ok(())
        } else {
            Err(CliError::new(code, unsafe {
                text(ci_error(self.raw.as_ptr(), code))
            }))
        }
    }

    fn string(&self, name: &str, value: &str) -> Result<(), CliError> {
        let name = cstring(name)?;
        let value = cstring(value)?;
        // All exposed string setopts copy their values before returning.
        self.check(unsafe { ci_string(self.raw.as_ptr(), name.as_ptr(), value.as_ptr()) })
    }

    fn number(&self, name: &str, value: i64) -> Result<(), CliError> {
        let name = cstring(name)?;
        let value = c_long::try_from(value)
            .map_err(|_| CliError::new(2, "numeric option exceeds native range"))?;
        self.check(unsafe { ci_long(self.raw.as_ptr(), name.as_ptr(), value) })
    }

    fn header(&self, value: &str) -> Result<(), CliError> {
        let value = cstring(value)?;
        self.check(unsafe { ci_header(self.raw.as_ptr(), value.as_ptr()) })
    }

    fn info_number(&self, name: &str) -> i64 {
        let name = CString::new(name).expect("internal info name");
        unsafe { ci_info_long(self.raw.as_ptr(), name.as_ptr()) as i64 }
    }

    fn info_bytes(&self, name: &str) -> Vec<u8> {
        let name = CString::new(name).expect("internal info name");
        // libcurl owns this NUL-terminated metadata until handle cleanup.
        unsafe { CStr::from_ptr(ci_info_string(self.raw.as_ptr(), name.as_ptr())) }
            .to_bytes()
            .to_vec()
    }

    fn write_out(&self, tokens: &[Token], code: i32) -> Result<(), CliError> {
        let mut stdout = io::stdout().lock();
        for token in tokens {
            let value = match token {
                Token::Text(t) => {
                    stdout
                        .write_all(t)
                        .map_err(|e| CliError::new(23, format!("writing write-out: {e}")))?;
                    continue;
                }
                Token::Variable(name) => match name.as_str() {
                    "http_code" | "response_code" => {
                        format!("{:03}", self.info_number("http_code"))
                    }
                    "num_redirects" => self.info_number(name).to_string(),
                    "url_effective" | "content_type" => {
                        stdout
                            .write_all(&self.info_bytes(name))
                            .map_err(|e| CliError::new(23, format!("writing write-out: {e}")))?;
                        continue;
                    }
                    "time_total" => format!("{:.6}", unsafe { ci_total_time(self.raw.as_ptr()) }),
                    "exitcode" => code.to_string(),
                    "http_version" => match self.info_number(name) {
                        1 => "1.0",
                        2 => "1.1",
                        3 => "2",
                        30 | 31 => "3",
                        _ => "0",
                    }
                    .into(),
                    _ => unreachable!("write-out was validated before transfer"),
                },
            };
            stdout
                .write_all(value.as_bytes())
                .map_err(|e| CliError::new(23, format!("writing write-out: {e}")))?;
        }
        stdout.flush().map_err(|e| CliError::new(23, e.to_string()))
    }
}

impl Drop for Handle {
    fn drop(&mut self) {
        // The native easy handle and its header list die before callback state.
        unsafe {
            ci_free(self.raw.as_ptr());
        }
    }
}

struct LazyFile {
    path: String,
    file: Option<File>,
}

impl Write for LazyFile {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        if self.file.is_none() {
            self.file = Some(File::create(&self.path)?);
        }
        self.file.as_mut().expect("file was opened").write(bytes)
    }

    fn flush(&mut self) -> io::Result<()> {
        match &mut self.file {
            Some(file) => file.flush(),
            None => Ok(()),
        }
    }
}

fn writer(path: Option<&str>, defer_file_creation: bool) -> Result<Box<dyn Write>, CliError> {
    match path {
        None | Some("-") => Ok(Box::new(io::stdout())),
        Some(path) if defer_file_creation => Ok(Box::new(LazyFile {
            path: path.to_owned(),
            file: None,
        })),
        Some(path) => File::create(path)
            .map(|f| Box::new(f) as Box<dyn Write>)
            .map_err(|e| CliError::new(23, format!("opening output {path}: {e}"))),
    }
}

fn has_header(headers: &[String], name: &str) -> bool {
    headers.iter().any(|h| {
        h.split_once([':', ';'])
            .is_some_and(|(n, _)| n.eq_ignore_ascii_case(name))
    })
}

#[derive(Clone)]
struct SharedWriter(Rc<RefCell<Box<dyn Write>>>);
impl Write for SharedWriter {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        self.0.borrow_mut().write(bytes)
    }
    fn flush(&mut self) -> io::Result<()> {
        self.0.borrow_mut().flush()
    }
}

pub(crate) struct Session {
    raw: NonNull<c_void>,
    header: Option<SharedWriter>,
}
impl Session {
    pub(crate) fn new(config: &Config) -> Result<Self, CliError> {
        initialize()?;
        // Validate the live engine before opening any shared output.
        let probe = Handle::new(Output {
            export: None,
            body: Box::new(io::sink()),
            header: None,
            flush_chunks: false,
            error: None,
        })?;
        if let Some(profile) = &config.impersonate {
            crate::profiles::validate(profile)?;
            probe.string("impersonate", profile)?;
        }
        let jar = config.cookie_jar.as_deref().map(cstring).transpose()?;
        let raw = NonNull::new(unsafe {
            ci_session_new(jar.as_ref().map_or(std::ptr::null(), |s| s.as_ptr()))
        })
        .ok_or_else(|| CliError::new(27, "cannot create shared transfer state"))?;
        let mut session = Self { raw, header: None };
        session.header = config
            .dump_header
            .as_deref()
            .map(|p| writer(Some(p), false).map(|w| SharedWriter(Rc::new(RefCell::new(w)))))
            .transpose()?;
        Ok(session)
    }
}
impl Drop for Session {
    fn drop(&mut self) {
        unsafe { ci_session_free(self.raw.as_ptr()) };
    }
}

pub(crate) struct Transfer {
    handle: Handle,
    pub index: usize,
    fail_with_body: bool,
    silent: bool,
}

pub(crate) struct TransferResult {
    pub error: Option<CliError>,
}

impl Transfer {
    pub(crate) fn prepare(
        config: &Config,
        prepared: &body::Prepared,
        target: TransferTarget,
        session: &Session,
    ) -> Result<Self, CliError> {
        let body::Prepared { data, headers, .. } = prepared;
        let url = if config.get && data.is_some() {
            body::with_query(&target.url, data.as_deref().unwrap_or_default())?
        } else {
            target.url.clone()
        };
        initialize()?;
        // Apply profile validation on a sink handle before creating any output.
        let mut handle = Handle::new(Output {
            export: None,
            body: Box::new(io::sink()),
            header: None,
            flush_chunks: false,
            error: None,
        })?;
        if let Some(profile) = &config.impersonate {
            crate::profiles::validate(profile)?;
            handle.string("impersonate", profile)?;
        }
        let export = config
            .export
            .map(|mode| Export::new(config, mode, &url))
            .transpose()?;
        let json_export = export.as_ref().is_some_and(Export::is_json);
        let output = Output {
            export,
            // curl preserves an existing -o file when no body is received and the
            // transfer fails; -D has eager creation semantics instead.
            body: if config.export.is_some() {
                Box::new(io::sink())
            } else {
                writer(target.output.as_deref(), true)?
            },
            header: session
                .header
                .clone()
                .map(|w| Box::new(w) as Box<dyn Write>),
            flush_chunks: config.no_buffer,
            error: None,
        };
        // Keep callback state at its original stable allocation.
        *handle.output = output;
        handle.check(unsafe { ci_session_attach(session.raw.as_ptr(), handle.raw.as_ptr()) })?;

        let impersonating = config.impersonate.is_some();
        let decompress = config.compressed.unwrap_or(impersonating);
        if !impersonating {
            handle.string("user_agent", "curl/8.23.0")?;
        }

        handle.string("url", &url)?;
        for (name, value) in [
            ("follow", i64::from(config.follow)),
            ("include", i64::from(config.include && !json_export)),
            ("fail", i64::from(config.fail)),
            ("verbose", i64::from(config.verbose)),
            ("verify_peer", i64::from(!config.insecure)),
            ("verify_host", if config.insecure { 0 } else { 2 }),
            ("decode", i64::from(decompress)),
        ] {
            handle.number(name, value)?;
        }
        for (name, value) in [
            ("timeout_ms", config.timeout_ms),
            ("connect_timeout_ms", config.connect_timeout_ms),
            ("max_redirects", config.max_redirects),
            ("http_version", config.http_version),
        ] {
            if let Some(value) = value {
                handle.number(name, value)?;
            }
        }
        let bundle_ca = std::env::var("CURL_CA_BUNDLE")
            .ok()
            .filter(|s| !s.is_empty());
        let env_ca = bundle_ca.clone().or_else(|| {
            std::env::var("SSL_CERT_FILE")
                .ok()
                .filter(|s| !s.is_empty())
        });
        for (name, value) in [
            ("ca_cert", config.ca_cert.as_ref().or(env_ca.as_ref())),
            ("user_agent", config.user_agent.as_ref()),
            ("user", config.user.as_ref()),
            ("proxy", config.proxy.as_ref()),
            ("proxy_user", config.proxy_user.as_ref()),
            ("no_proxy", config.no_proxy.as_ref()),
        ] {
            if let Some(value) = value {
                handle.string(name, value)?;
            }
        }
        if let Some(referer) = &config.referer {
            let initial = referer.strip_suffix(";auto");
            handle.number("auto_referer", i64::from(initial.is_some()))?;
            let initial = initial.unwrap_or(referer);
            if !initial.is_empty() {
                handle.string("referer", initial)?;
            }
        }
        if config.ca_cert.is_none() && bundle_ca.is_none() {
            if let Ok(path) = std::env::var("SSL_CERT_DIR") {
                if !path.is_empty() {
                    handle.string("ca_path", &path)?;
                }
            }
        }
        if decompress {
            handle.string("encoding", "")?;
        }
        let mut cookie_values = Vec::new();
        for cookie in &config.cookies {
            if cookie.contains('=') {
                cookie_values.push(cookie.as_str());
            } else {
                handle.string("cookie_file", cookie)?;
            }
        }
        if !cookie_values.is_empty() {
            handle.string("cookie", &cookie_values.join(";"))?;
        }
        if config.data.iter().any(|p| p.kind == DataKind::Json) {
            if !has_header(&headers, "content-type") {
                handle.header("Content-Type: application/json")?;
            }
            if !has_header(&headers, "accept") {
                handle.header("Accept: application/json")?;
            }
        } else if !impersonating && !has_header(&headers, "accept") {
            // The impersonate fork removes libcurl's default Accept header. Restore
            // curl CLI behavior only when no browser profile owns that default.
            handle.header("Accept: */*")?;
        }
        for header in headers {
            handle.header(header)?;
        }
        if !config.get {
            if let Some(bytes) = data {
                handle
                    .check(unsafe { ci_body(handle.raw.as_ptr(), bytes.as_ptr(), bytes.len()) })?;
            }
        } else {
            handle.number("get", 1)?;
        }
        if config.head {
            handle.number("head", 1)?;
        }
        if let Some(method) = &config.method {
            handle.string("method", method)?;
        }

        Ok(Self {
            handle,
            index: target.index,
            fail_with_body: config.fail_with_body,
            silent: config.silent,
        })
    }

    pub(crate) fn raw(&self) -> *mut c_void {
        self.handle.raw.as_ptr()
    }

    pub(crate) fn perform(&mut self) -> i32 {
        unsafe { ci_perform(self.raw()) }
    }

    pub(crate) fn complete(
        &mut self,
        mut code: i32,
        format: &[Token],
    ) -> Result<TransferResult, CliError> {
        let handle = &mut self.handle;
        if code == 0 && handle.info_number("http_code") != 304 {
            // A successful empty response must still create/truncate -o. Calling
            // write (not write_all) also opens a LazyFile for an empty slice.
            if let Err(e) = handle.output.body.write(&[]) {
                handle.output.error = Some(e.to_string());
                code = 23;
            }
        }
        if code == 0 && self.fail_with_body && handle.info_number("http_code") >= 400 {
            code = 22;
        }
        if let Err(e) = handle.output.body.flush() {
            handle.output.error = Some(e.to_string());
            code = 23;
        }
        if let Some(header) = &mut handle.output.header {
            if let Err(e) = header.flush() {
                handle.output.error = Some(e.to_string());
                code = 23;
            }
        }
        if handle.output.export.is_none() {
            handle.write_out(format, code)?;
        }
        if let Some(error) = &handle.output.error {
            return Err(CliError::new(23, format!("writing output: {error}")));
        }
        let status = handle.info_number("http_code");
        if let Some(export) = &mut handle.output.export {
            let path = export
                .finish(status, code)
                .map_err(|e| CliError::new(23, format!("writing export: {e}")))?;
            if let Some(path) = path {
                if !self.silent {
                    let _ = writeln!(io::stderr().lock(), "Saved response to {}", path.display());
                }
            }
        }
        Ok(TransferResult {
            error: handle.check(code).err(),
        })
    }
}

pub fn list_profiles() -> Result<String, CliError> {
    let mut names = Vec::new();
    // Validate the catalog against the actual loaded engine, without network I/O.
    for name in crate::profiles::names() {
        let handle = Handle::new(Output {
            export: None,
            body: Box::new(io::sink()),
            header: None,
            flush_chunks: false,
            error: None,
        })?;
        handle.string("impersonate", name)?;
        names.push(name);
    }
    Ok(names.join("\n") + "\n")
}
