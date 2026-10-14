use crate::cli::{CliError, DataKind, DataPart};
use std::io::Read;

pub fn read_source(path: &str) -> Result<Vec<u8>, CliError> {
    if path == "-" {
        let mut bytes = Vec::new();
        std::io::stdin()
            .read_to_end(&mut bytes)
            .map_err(|e| CliError::new(26, format!("reading stdin: {e}")))?;
        Ok(bytes)
    } else {
        std::fs::read(path).map_err(|e| CliError::new(26, format!("reading {path}: {e}")))
    }
}

pub fn materialize(parts: &[DataPart]) -> Result<Option<Vec<u8>>, CliError> {
    if parts.is_empty() {
        return Ok(None);
    }
    let mut result = Vec::new();
    for part in parts {
        if !result.is_empty() && part.kind != DataKind::Json {
            result.push(b'&');
        }
        let mut bytes = if part.kind != DataKind::Raw && part.value.starts_with('@') {
            let mut bytes = read_source(&part.value[1..])?;
            if part.kind == DataKind::Form {
                bytes.retain(|b| !matches!(b, b'\r' | b'\n' | 0));
            }
            bytes
        } else {
            part.value.as_bytes().to_vec()
        };
        result.append(&mut bytes);
    }
    Ok(Some(result))
}

pub fn headers(values: &[String]) -> Result<Vec<String>, CliError> {
    let mut result = Vec::new();
    for value in values {
        if let Some(path) = value.strip_prefix('@') {
            let text = String::from_utf8(read_source(path)?)
                .map_err(|_| CliError::new(2, "header files must be UTF-8"))?;
            result.extend(text.lines().filter(|s| !s.is_empty()).map(String::from));
        } else {
            result.push(value.clone());
        }
    }
    if result.iter().any(|s| s.contains(['\r', '\n', '\0'])) {
        return Err(CliError::new(
            2,
            "header values must not contain CR, LF, or NUL",
        ));
    }
    Ok(result)
}

pub fn with_query(url: &str, body: &[u8]) -> Result<String, CliError> {
    let query = std::str::from_utf8(body)
        .map_err(|_| CliError::new(2, "--get query data must be UTF-8"))?;
    let (base, fragment) = url
        .split_once('#')
        .map_or((url, None), |(u, f)| (u, Some(f)));
    if query.is_empty()
        && (!base.contains('?')
            || base
                .split_once('?')
                .is_some_and(|(_, query)| query.is_empty()))
    {
        let mut result = base.strip_suffix('?').unwrap_or(base).to_owned();
        if let Some(fragment) = fragment {
            result.push('#');
            result.push_str(fragment);
        }
        return Ok(result);
    }
    let separator = if base
        .split_once('?')
        .is_some_and(|(_, query)| query.is_empty())
    {
        ""
    } else if base.contains('?') {
        "&"
    } else {
        "?"
    };
    let mut result = format!("{base}{separator}{query}");
    if let Some(fragment) = fragment {
        result.push('#');
        result.push_str(fragment);
    }
    Ok(result)
}

/// Resolve all input readers in argument order, including superseded write-outs.
pub fn prepare(config: &crate::cli::Config) -> Result<Prepared, CliError> {
    use crate::cli::Input;
    let mut prepared = Prepared {
        data: None,
        headers: Vec::new(),
        format: Vec::new(),
    };
    let mut write_out = Vec::new();
    for input in &config.inputs {
        match input {
            Input::Data(index) => {
                let part = &config.data[*index];
                let bytes = materialize(std::slice::from_ref(part))?.unwrap_or_default();
                let data = prepared.data.get_or_insert_with(Vec::new);
                if !data.is_empty() && part.kind != DataKind::Json {
                    data.push(b'&');
                }
                data.extend(bytes);
            }
            Input::Header(index) => prepared
                .headers
                .extend(headers(std::slice::from_ref(&config.headers[*index]))?),
            Input::WriteOut(value) => write_out = crate::writeout::read(value)?,
        }
    }
    prepared.format = crate::writeout::parse(&write_out)?;
    Ok(prepared)
}

pub struct Prepared {
    pub data: Option<Vec<u8>>,
    pub headers: Vec<String>,
    pub format: Vec<crate::writeout::Token>,
}
