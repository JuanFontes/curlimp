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
    for (i, part) in parts.iter().enumerate() {
        if i > 0 && part.kind != DataKind::Json {
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
    if query.is_empty() {
        return Ok(url.to_owned());
    }
    let (base, fragment) = url
        .split_once('#')
        .map_or((url, None), |(u, f)| (u, Some(f)));
    let separator = if base.ends_with('?') {
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
