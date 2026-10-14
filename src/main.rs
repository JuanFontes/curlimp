use curlimp::{
    cli::{self, Action, CliError},
    completion, engine,
};
use std::{
    ffi::OsString,
    io::{self, Write},
};

fn selected_profile(
    config: &cli::Config,
    environment_profile: Option<OsString>,
    environment_headers: Option<OsString>,
) -> Result<Option<String>, CliError> {
    if config.no_impersonate {
        return Ok(None);
    }
    if let Some(profile) = &config.impersonate {
        return Ok(Some(profile.clone()));
    }
    let mut profile = match environment_profile {
        Some(value) => value
            .into_string()
            .map_err(|_| CliError::new(2, "CURL_IMPERSONATE must contain a UTF-8 profile name"))?,
        None => cli::DEFAULT_PROFILE.to_owned(),
    };
    if profile.is_empty() {
        return Err(CliError::new(2, "CURL_IMPERSONATE must not be empty"));
    }
    if !profile.contains(':')
        && environment_headers
            .as_deref()
            .and_then(|value| value.to_str())
            .is_some_and(|value| value.eq_ignore_ascii_case("no"))
    {
        profile.push_str(":no");
    }
    Ok(Some(profile))
}

fn output(bytes: &[u8]) -> Result<(), CliError> {
    let mut stdout = io::stdout().lock();
    stdout
        .write_all(bytes)
        .and_then(|_| stdout.flush())
        .map_err(|e| CliError::new(23, e.to_string()))
}

fn main() {
    // Consume these before initializing libcurl or starting any threads. The
    // native init hook must not apply a lower-priority profile before the CLI
    // selects one (or reject --no-impersonate because an env profile is invalid).
    let environment_profile = std::env::var_os("CURL_IMPERSONATE");
    let environment_headers = std::env::var_os("CURL_IMPERSONATE_HEADERS");
    std::env::remove_var("CURL_IMPERSONATE");
    std::env::remove_var("CURL_IMPERSONATE_HEADERS");
    let args: Result<Vec<_>, _> = std::env::args_os()
        .skip(1)
        .map(|s| s.into_string())
        .collect();
    if let Ok(args) = &args {
        extern "C" {
            fn ci_mask_argument(index: usize, offset: usize);
        }
        for (index, offset) in cli::credential_arguments(args) {
            // The C helper bounds-checks argv and overwrites writable OS storage;
            // parsing retains the owned Rust copies made above.
            unsafe {
                ci_mask_argument(index, offset);
            }
        }
    }
    let parsed = args
        .map_err(|_| CliError::new(2, "Curlimp requires UTF-8 arguments"))
        .and_then(cli::parse);
    let mut show_error = true;
    let result = match parsed {
        Ok(Action::Help) => output(include_bytes!("help.txt")),
        Ok(Action::Version) => engine::version().and_then(|v| {
            output(
                format!(
                    "curlimp {}\nEngine: {v}\nDefault profile: {}\n",
                    env!("CARGO_PKG_VERSION"),
                    cli::DEFAULT_PROFILE,
                )
                .as_bytes(),
            )
        }),
        Ok(Action::Profiles) => engine::list_profiles().and_then(|p| output(p.as_bytes())),
        Ok(Action::Completions) => output(completion::ZSH.as_bytes()),
        Ok(Action::CompleteProfiles(words)) => {
            let candidates = completion::profile_candidates(&words);
            if candidates.is_empty() {
                Ok(())
            } else {
                output((candidates.join("\n") + "\n").as_bytes())
            }
        }
        Ok(Action::Transfer(mut config)) => {
            show_error = !config.silent || config.show_error;
            selected_profile(&config, environment_profile, environment_headers).and_then(
                |profile| {
                    config.impersonate = profile;
                    engine::run(&config)
                },
            )
        }
        Err(error) => Err(error),
    };
    if let Err(error) = result {
        if show_error {
            let _ = writeln!(
                io::stderr().lock(),
                "curlimp: ({}) {}",
                error.code,
                error.message
            );
        }
        std::process::exit(error.code.clamp(1, 255));
    }
}
