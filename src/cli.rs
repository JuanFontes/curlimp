pub const DEFAULT_PROFILE: &str = "chrome150";

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum DataKind {
    Form,
    Raw,
    Binary,
    Json,
}

#[derive(Debug, Clone, PartialEq)]
pub struct DataPart {
    pub kind: DataKind,
    pub value: String,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum ExportMode {
    Text,
    JsonOutput,
    JsonFile,
}

#[derive(Debug, PartialEq)]
pub enum Input {
    Data(usize),
    Header(usize),
    WriteOut(String),
}

#[derive(Debug, Default, PartialEq)]
pub struct Config {
    pub inputs: Vec<Input>,
    pub export: Option<ExportMode>,
    pub urls: Vec<String>,
    pub silent: bool,
    pub show_error: bool,
    pub follow: bool,
    pub method: Option<String>,
    pub headers: Vec<String>,
    pub data: Vec<DataPart>,
    pub outputs: Vec<String>,
    pub parallel: bool,
    pub parallel_max: Option<usize>,
    pub timeout_ms: Option<i64>,
    pub connect_timeout_ms: Option<i64>,
    pub dump_header: Option<String>,
    pub include: bool,
    pub head: bool,
    pub get: bool,
    pub verbose: bool,
    pub insecure: bool,
    pub compressed: Option<bool>,
    pub no_buffer: bool,
    pub fail: bool,
    pub fail_with_body: bool,
    pub max_redirects: Option<i64>,
    pub ca_cert: Option<String>,
    pub user_agent: Option<String>,
    pub referer: Option<String>,
    pub user: Option<String>,
    pub proxy: Option<String>,
    pub proxy_user: Option<String>,
    pub no_proxy: Option<String>,
    pub cookies: Vec<String>,
    pub cookie_jar: Option<String>,
    pub impersonate: Option<String>,
    pub no_impersonate: bool,
    pub http_version: Option<i64>,
    pub write_out: Option<String>,
}

#[derive(Debug, PartialEq)]
pub struct TransferTarget {
    pub index: usize,
    pub url: String,
    pub output: Option<String>,
}

impl Config {
    pub fn targets(&self) -> impl Iterator<Item = TransferTarget> + '_ {
        self.urls
            .iter()
            .enumerate()
            .map(|(index, url)| TransferTarget {
                index,
                url: url.clone(),
                output: self.outputs.get(index).cloned(),
            })
    }
}

#[derive(Debug, PartialEq)]
pub enum Action {
    Help,
    Version,
    Profiles,
    Completions,
    CompleteProfiles(Vec<String>),
    Transfer(Box<Config>),
}

#[derive(Debug, PartialEq)]
pub struct CliError {
    pub code: i32,
    pub message: String,
    pub reported: bool,
}

impl CliError {
    pub fn new(code: i32, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
            reported: false,
        }
    }
}

impl std::fmt::Display for CliError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.message)
    }
}

impl std::error::Error for CliError {}

fn error(message: impl Into<String>) -> CliError {
    CliError::new(2, message)
}

pub(crate) fn takes_value(name: &str) -> bool {
    matches!(
        name,
        "url"
            | "completions"
            | "request"
            | "header"
            | "data"
            | "data-raw"
            | "data-binary"
            | "json"
            | "output"
            | "parallel-max"
            | "dump-header"
            | "max-time"
            | "connect-timeout"
            | "max-redirs"
            | "cacert"
            | "user-agent"
            | "referer"
            | "user"
            | "proxy"
            | "proxy-user"
            | "noproxy"
            | "cookie"
            | "cookie-jar"
            | "impersonate"
            | "write-out"
    )
}

pub(crate) fn short_name(c: char) -> Result<&'static str, CliError> {
    Ok(match c {
        'h' => "help",
        'V' => "version",
        's' => "silent",
        'S' => "show-error",
        'L' => "location",
        'X' => "request",
        'H' => "header",
        'd' => "data",
        'o' => "output",
        'D' => "dump-header",
        'i' => "include",
        'I' => "head",
        'G' => "get",
        'v' => "verbose",
        'k' => "insecure",
        'f' => "fail",
        'm' => "max-time",
        'A' => "user-agent",
        'e' => "referer",
        'u' => "user",
        'x' => "proxy",
        'U' => "proxy-user",
        'b' => "cookie",
        'c' => "cookie-jar",
        'w' => "write-out",
        'N' => "no-buffer",
        'q' => "disable",
        'Z' => "parallel",
        _ => {
            return Err(error(format!(
                "unsupported option -{c}; see --help for supported options"
            )))
        }
    })
}

fn milliseconds(value: &str) -> Result<i64, CliError> {
    let n: f64 = value
        .parse()
        .map_err(|_| error("timeout must be a non-negative number of seconds"))?;
    if !n.is_finite() || n < 0.0 || n >= (i64::MAX / 1000) as f64 {
        return Err(error("timeout is outside the supported range"));
    }
    Ok(if n == 0.0 {
        0
    } else {
        (n * 1000.0).ceil() as i64
    })
}

fn add_url(c: &mut Config, url: String) -> Result<(), CliError> {
    if url.is_empty() {
        return Err(error("URL must not be empty"));
    }
    c.urls.push(url);
    Ok(())
}

pub(crate) fn apply(
    c: &mut Config,
    name: &str,
    value: Option<String>,
) -> Result<Option<Action>, CliError> {
    if !takes_value(name) && value.is_some() {
        return Err(error(format!("--{name} does not take a value")));
    }
    let v = value.unwrap_or_default();
    match name {
        "help" => return Ok(Some(Action::Help)),
        "version" => return Ok(Some(Action::Version)),
        "list-profiles" => return Ok(Some(Action::Profiles)),
        "completions" => {
            if v != "zsh" {
                return Err(error("--completions currently supports zsh only"));
            }
            return Ok(Some(Action::Completions));
        }
        "url" => add_url(c, v)?,
        "request" => c.method = Some(v),
        "header" => {
            c.inputs.push(Input::Header(c.headers.len()));
            c.headers.push(v);
        }
        "data" | "data-raw" | "data-binary" | "json" => {
            let kind = match name {
                "data" => DataKind::Form,
                "data-raw" => DataKind::Raw,
                "data-binary" => DataKind::Binary,
                _ => DataKind::Json,
            };
            c.inputs.push(Input::Data(c.data.len()));
            c.data.push(DataPart { kind, value: v });
        }
        "txt" | "json-output" | "json-file" => {
            let mode = match name {
                "txt" => ExportMode::Text,
                "json-output" => ExportMode::JsonOutput,
                _ => ExportMode::JsonFile,
            };
            if c.export.is_some_and(|previous| previous != mode) {
                return Err(error(
                    "--txt, --json-output and --json-file are mutually exclusive",
                ));
            }
            c.export = Some(mode);
        }
        "output" => c.outputs.push(v),
        "parallel" => c.parallel = true,
        "no-parallel" => c.parallel = false,
        "parallel-max" => {
            let value: u64 = v
                .parse()
                .map_err(|_| error("--parallel-max requires an unsigned integer"))?;
            c.parallel_max = Some(if value == 0 {
                50
            } else {
                value.min(65535) as usize
            });
        }
        "dump-header" => c.dump_header = Some(v),
        "write-out" => {
            c.inputs.push(Input::WriteOut(v.clone()));
            c.write_out = Some(v);
        }
        "max-time" => c.timeout_ms = Some(milliseconds(&v)?),
        "connect-timeout" => c.connect_timeout_ms = Some(milliseconds(&v)?),
        "max-redirs" => {
            let n: i64 = v
                .parse()
                .map_err(|_| error("--max-redirs requires an integer"))?;
            if n < -1 {
                return Err(error("--max-redirs must be -1 or greater"));
            }
            c.max_redirects = Some(n);
        }
        "cacert" => c.ca_cert = Some(v),
        "user-agent" => c.user_agent = Some(v),
        "referer" => c.referer = Some(v),
        "user" => c.user = Some(v),
        "proxy" => c.proxy = Some(v),
        "proxy-user" => c.proxy_user = Some(v),
        "noproxy" => c.no_proxy = Some(v),
        "cookie" => c.cookies.push(v),
        "cookie-jar" => c.cookie_jar = Some(v),
        "impersonate" => {
            c.impersonate = Some(v);
            c.no_impersonate = false;
        }
        "no-impersonate" => {
            c.impersonate = None;
            c.no_impersonate = true;
        }
        "http1.0" => c.http_version = Some(0),
        "http1.1" => c.http_version = Some(1),
        "http2" => c.http_version = Some(2),
        "http3" => c.http_version = Some(3),
        "http3-only" => c.http_version = Some(4),
        "silent" => c.silent = true,
        "no-silent" => c.silent = false,
        "show-error" => c.show_error = true,
        "no-show-error" => c.show_error = false,
        "location" => c.follow = true,
        "no-location" => c.follow = false,
        "include" => c.include = true,
        "no-include" => c.include = false,
        "head" => {
            c.head = true;
            c.include = true;
        }
        "no-head" => {
            c.head = false;
            c.include = false;
        }
        "get" => c.get = true,
        "verbose" => c.verbose = true,
        "no-verbose" => c.verbose = false,
        "insecure" => c.insecure = true,
        "no-insecure" => c.insecure = false,
        "compressed" => c.compressed = Some(true),
        "no-compressed" => c.compressed = Some(false),
        "no-buffer" => c.no_buffer = true,
        "buffer" => c.no_buffer = false,
        "fail" => c.fail = true,
        "no-fail" => c.fail = false,
        "fail-with-body" => c.fail_with_body = true,
        "no-fail-with-body" => c.fail_with_body = false,
        "disable" => {} // Curlimp never reads .curlrc; retained for reproducible scripts.
        _ => {
            return Err(error(format!(
                "unsupported option --{name}; see --help for supported options"
            )))
        }
    }
    Ok(None)
}

pub fn parse(args: Vec<String>) -> Result<Action, CliError> {
    // Shell completion only reads local catalog data. Never interpret these
    // words as a transfer or evaluate their values as shell code.
    if args.first().is_some_and(|arg| arg == "--complete-profiles") {
        return Ok(Action::CompleteProfiles(args.into_iter().skip(1).collect()));
    }
    let mut c = Config::default();
    let mut args = args.into_iter();
    let mut literal = false;
    let mut positional_profile = false;
    while let Some(arg) = args.next() {
        if arg.contains('\0') {
            return Err(error("arguments must not contain NUL bytes"));
        }
        if literal {
            add_url(&mut c, arg)?;
            continue;
        }
        if arg == "--" {
            literal = true;
            continue;
        }
        if let Some(long) = arg.strip_prefix("--") {
            let (name, attached) = match long.split_once('=') {
                Some((n, v)) => (n, Some(v.to_owned())),
                None => (long, None),
            };
            let value = if takes_value(name) {
                Some(
                    attached
                        .or_else(|| args.next())
                        .ok_or_else(|| error(format!("--{name} requires a value")))?,
                )
            } else {
                attached
            };
            if let Some(action) = apply(&mut c, name, value)? {
                return Ok(action);
            }
        } else if arg.starts_with('-') && arg.len() > 1 {
            let mut chars = arg[1..].char_indices().peekable();
            while let Some((_, ch)) = chars.next() {
                let name = short_name(ch)?;
                let value = if takes_value(name) {
                    let v = if let Some((pos, _)) = chars.peek() {
                        arg[1 + pos..].to_owned()
                    } else {
                        args.next()
                            .ok_or_else(|| error(format!("-{ch} requires a value")))?
                    };
                    Some(v)
                } else {
                    None
                };
                if let Some(action) = apply(&mut c, name, value)? {
                    return Ok(action);
                }
                if takes_value(name) {
                    break;
                }
            }
        } else if c.urls.is_empty() && crate::profiles::contains(&arg) {
            if positional_profile {
                return Err(error(
                    "only one positional profile is allowed; use --impersonate to override it",
                ));
            }
            positional_profile = true;
            apply(&mut c, "impersonate", Some(arg))?;
        } else {
            add_url(&mut c, arg)?;
        }
    }
    if c.urls.is_empty() {
        return Err(error("no URL specified; see --help"));
    }
    if c.head && !c.get && !c.data.is_empty() {
        return Err(error(
            "HEAD and POST data cannot be combined; use --get for query data",
        ));
    }
    if c.fail && c.fail_with_body {
        return Err(error("--fail and --fail-with-body cannot be combined"));
    }
    if c.data.iter().any(|p| p.kind == DataKind::Json)
        && c.data.iter().any(|p| p.kind != DataKind::Json)
    {
        return Err(error(
            "Curlimp does not support mixing --json with other data options",
        ));
    }
    if c.urls.len() > 1 && c.export == Some(ExportMode::JsonOutput) {
        return Err(error("multiple-URL JSON output is not available yet"));
    }
    if let Some(mode) = c.export {
        if !c.outputs.is_empty() || c.dump_header.is_some() || c.write_out.is_some() {
            return Err(error("export modes cannot be combined with --output (-o), --dump-header (-D), or --write-out (-w)"));
        }
        if mode == ExportMode::JsonOutput && c.cookie_jar.as_deref() == Some("-") {
            return Err(error(
                "--json-output cannot be combined with --cookie-jar -",
            ));
        }
        if mode != ExportMode::Text && c.no_buffer {
            return Err(error(
                "JSON export modes cannot be combined with --no-buffer (-N)",
            ));
        }
    }
    Ok(Action::Transfer(Box::new(c)))
}

/// Locate credential values using the same option grammar as parsing. Offsets
/// refer to bytes in the original OS arguments (including argv[0]).
pub fn credential_arguments(args: &[String]) -> Vec<(usize, usize)> {
    let mut spans = Vec::new();
    let mut index = 0;
    while let Some(arg) = args.get(index) {
        if arg == "--" {
            break;
        }
        if let Some(long) = arg.strip_prefix("--") {
            let (name, attached) = long
                .split_once('=')
                .map_or((long, None), |(n, v)| (n, Some(v)));
            if matches!(
                name,
                "help" | "version" | "list-profiles" | "complete-profiles" | "completions"
            ) {
                break;
            }
            if takes_value(name) {
                if matches!(name, "user" | "proxy-user") {
                    spans.push(if attached.is_some() {
                        (index + 1, 2 + name.len() + 1)
                    } else {
                        (index + 2, 0)
                    });
                }
                if attached.is_none() {
                    index += 1;
                }
            }
        } else if arg.starts_with('-') && arg.len() > 1 {
            for (position, ch) in arg[1..].char_indices() {
                let Ok(name) = short_name(ch) else {
                    break;
                };
                if matches!(name, "help" | "version") {
                    return spans;
                }
                if takes_value(name) {
                    let offset = 1 + position + ch.len_utf8();
                    let attached = offset < arg.len();
                    if matches!(name, "user" | "proxy-user") {
                        spans.push(if attached {
                            (index + 1, offset)
                        } else {
                            (index + 2, 0)
                        });
                    }
                    if !attached {
                        index += 1;
                    }
                    break;
                }
            }
        }
        index += 1;
    }
    spans
}
