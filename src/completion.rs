use crate::{cli, profiles};

pub const ZSH: &str = include_str!("../completions/_curlimp");

/// Complete only profile positions, respecting the parser's option arities.
/// `words` excludes the executable and ends with the word at the cursor.
pub fn profile_candidates(words: &[String]) -> Vec<&'static str> {
    let Some((current, before)) = words.split_last() else {
        return Vec::new();
    };
    let mut config = cli::Config::default();
    let mut args = before.iter();
    let mut waiting = None;
    let mut positional_profile = false;
    while let Some(arg) = args.next() {
        if arg == "--" {
            return Vec::new();
        }
        if let Some(long) = arg.strip_prefix("--") {
            let (name, attached) = long
                .split_once('=')
                .map_or((long, None), |(n, v)| (n, Some(v)));
            let value = if cli::takes_value(name) {
                match attached.or_else(|| args.next().map(String::as_str)) {
                    Some(value) => Some(value.to_owned()),
                    None => {
                        waiting = Some(name);
                        break;
                    }
                }
            } else {
                attached.map(str::to_owned)
            };
            if !matches!(cli::apply(&mut config, name, value), Ok(None)) {
                return Vec::new();
            }
        } else if arg.starts_with('-') && arg.len() > 1 {
            let mut chars = arg[1..].char_indices().peekable();
            while let Some((_, ch)) = chars.next() {
                let Ok(name) = cli::short_name(ch) else {
                    return Vec::new();
                };
                let value = if cli::takes_value(name) {
                    let next = if let Some((pos, _)) = chars.peek() {
                        Some(&arg[1 + pos..])
                    } else {
                        args.next().map(String::as_str)
                    };
                    match next {
                        Some(value) => Some(value.to_owned()),
                        None => {
                            waiting = Some(name);
                            break;
                        }
                    }
                } else {
                    None
                };
                if !matches!(cli::apply(&mut config, name, value), Ok(None)) {
                    return Vec::new();
                }
                if cli::takes_value(name) {
                    break;
                }
            }
        } else if config.urls.is_empty() && !positional_profile && profiles::contains(arg) {
            positional_profile = true;
            config.impersonate = Some(arg.to_owned());
        } else {
            return Vec::new();
        }
    }
    let prefix = match waiting {
        Some("impersonate") => current.as_str(),
        Some(_) => return Vec::new(),
        None => {
            if let Some(prefix) = current.strip_prefix("--impersonate=") {
                prefix
            } else if config.urls.is_empty() && !positional_profile && config.impersonate.is_none()
            {
                current.as_str()
            } else {
                return Vec::new();
            }
        }
    };
    profiles::names()
        .filter(|name| name.starts_with(prefix))
        .collect()
}
