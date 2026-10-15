//! Invocation-level scheduling and diagnostics; response state belongs to each transfer.
use crate::{
    body,
    cli::{CliError, Config},
    engine::{Session, Transfer},
};
use std::io::{self, Write};

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
    if config.outputs.len() > config.urls.len() && !config.silent {
        let _ = writeln!(
            io::stderr().lock(),
            "Warning: Got more output options than URLs"
        );
    }
    let mut result = Ok(());
    for target in config.targets() {
        let mut transfer = Transfer::prepare(config, &prepared, target, &session)?;
        let code = transfer.perform();
        result = transfer
            .complete(code, &prepared.format)
            .and_then(|result| result.error.map_or(Ok(()), Err))
            .map_err(|mut error| {
                if config.urls.len() > 1 {
                    error.message = format!("transfer {}: {}", transfer.index + 1, error.message);
                }
                report(config, error)
            });
        if result
            .as_ref()
            .is_err_and(|error| matches!(error.code, 2 | 4 | 27))
        {
            break;
        }
    }
    result
}
