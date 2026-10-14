use crate::{body::read_source, cli::CliError};

pub enum Token {
    Text(Vec<u8>),
    Variable(String),
}

pub fn parse(format: &str) -> Result<Vec<Token>, CliError> {
    let source = if let Some(path) = format.strip_prefix('@') {
        let mut bytes = read_source(path)?;
        bytes.retain(|b| !matches!(b, b'\r' | b'\n' | 0));
        bytes
    } else {
        format.as_bytes().to_vec()
    };
    let mut chars = source.into_iter().peekable();
    let mut tokens = Vec::new();
    let mut text = Vec::new();
    while let Some(ch) = chars.next() {
        match ch {
            b'\\' => match chars.next() {
                Some(b'n') => text.push(b'\n'),
                Some(b'r') => text.push(b'\r'),
                Some(b't') => text.push(b'\t'),
                Some(c) => {
                    text.push(b'\\');
                    text.push(c);
                }
                None => text.push(b'\\'),
            },
            b'%' if chars.peek() == Some(&b'%') => {
                chars.next();
                text.push(b'%');
            }
            b'%' if chars.peek() == Some(&b'{') => {
                chars.next();
                let mut name = Vec::new();
                loop {
                    match chars.next() {
                        Some(b'}') => break,
                        Some(c) => name.push(c),
                        None => return Err(CliError::new(2, "unterminated write-out variable")),
                    }
                }
                let name = String::from_utf8(name)
                    .map_err(|_| CliError::new(2, "write-out variable must be UTF-8"))?;
                if !matches!(
                    name.as_str(),
                    "http_code"
                        | "response_code"
                        | "url_effective"
                        | "content_type"
                        | "num_redirects"
                        | "http_version"
                        | "time_total"
                        | "exitcode"
                ) {
                    return Err(CliError::new(
                        2,
                        format!("unsupported write-out variable: {name}"),
                    ));
                }
                if !text.is_empty() {
                    tokens.push(Token::Text(std::mem::take(&mut text)));
                }
                tokens.push(Token::Variable(name));
            }
            _ => text.push(ch),
        }
    }
    if !text.is_empty() {
        tokens.push(Token::Text(text));
    }
    Ok(tokens)
}
