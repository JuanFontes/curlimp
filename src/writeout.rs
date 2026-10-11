use crate::{body::read_source, cli::CliError};

pub enum Token {
    Text(String),
    Variable(String),
}

pub fn parse(format: &str) -> Result<Vec<Token>, CliError> {
    let source = if let Some(path) = format.strip_prefix('@') {
        String::from_utf8(read_source(path)?)
            .map_err(|_| CliError::new(2, "write-out format must be UTF-8"))?
    } else {
        format.to_owned()
    };
    let mut chars = source.chars().peekable();
    let mut tokens = Vec::new();
    let mut text = String::new();
    while let Some(ch) = chars.next() {
        match ch {
            '\\' => match chars.next() {
                Some('n') => text.push('\n'),
                Some('r') => text.push('\r'),
                Some('t') => text.push('\t'),
                Some('\\') => text.push('\\'),
                Some(c) => {
                    text.push('\\');
                    text.push(c);
                }
                None => text.push('\\'),
            },
            '%' if chars.peek() == Some(&'%') => {
                chars.next();
                text.push('%');
            }
            '%' if chars.peek() == Some(&'{') => {
                chars.next();
                let mut name = String::new();
                loop {
                    match chars.next() {
                        Some('}') => break,
                        Some(c) => name.push(c),
                        None => return Err(CliError::new(2, "unterminated write-out variable")),
                    }
                }
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
