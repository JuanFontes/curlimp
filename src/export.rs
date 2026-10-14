//! Opt-in response exports; ordinary curl-style output stays in the engine.
use crate::cli::{CliError, Config, ExportMode};
#[cfg(unix)]
use std::os::unix::fs::OpenOptionsExt;
use std::{
    ffi::{c_char, c_int, CStr, CString},
    fs::{File, OpenOptions},
    io::{self, BufWriter, Write},
    path::PathBuf,
};

extern "C" {
    fn ci_local_timestamp(buffer: *mut c_char, capacity: usize) -> c_int;
    fn ci_url_host_path(url: *const c_char, buffer: *mut c_char, capacity: usize) -> c_int;
}

const JSON_LIMIT: usize = 64 * 1024 * 1024;

pub struct Export {
    mode: ExportMode,
    include_headers: bool,
    head: bool,
    stem: String,
    path: Option<PathBuf>,
    file: Option<File>,
    body: Vec<u8>,
    headers: Vec<u8>,
}

impl Export {
    pub fn new(config: &Config, mode: ExportMode) -> Result<Self, CliError> {
        let mut timestamp = [0 as c_char; 32];
        // The bridge fills a bounded, NUL-terminated buffer using libc localtime.
        if unsafe { ci_local_timestamp(timestamp.as_mut_ptr(), timestamp.len()) } == 0 {
            return Err(CliError::new(23, "cannot format the export timestamp"));
        }
        let timestamp = unsafe { CStr::from_ptr(timestamp.as_ptr()) }.to_string_lossy();
        Ok(Self {
            mode,
            include_headers: config.include,
            head: config.head,
            stem: format!("{timestamp}_{}", url_slug(&config.url)),
            path: None,
            file: None,
            body: Vec::new(),
            headers: Vec::new(),
        })
    }

    pub fn is_json(&self) -> bool {
        self.mode != ExportMode::Text
    }

    fn ensure_file(&mut self) -> io::Result<&mut File> {
        if self.file.is_none() {
            let extension = if self.mode == ExportMode::Text {
                "txt"
            } else {
                "json"
            };
            for sequence in 0..10_000 {
                let suffix = if sequence == 0 {
                    String::new()
                } else {
                    format!("-{sequence}")
                };
                let path = PathBuf::from(format!("{}{suffix}.{extension}", self.stem));
                let mut options = OpenOptions::new();
                options.write(true).create_new(true);
                #[cfg(unix)]
                options.mode(0o600);
                match options.open(&path) {
                    Ok(file) => {
                        self.path = Some(path);
                        self.file = Some(file);
                        break;
                    }
                    Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
                    Err(error) => return Err(error),
                }
            }
        }
        self.file.as_mut().ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::AlreadyExists,
                "too many export filename collisions",
            )
        })
    }

    pub fn receive(&mut self, bytes: &[u8], header: bool, flush: bool) -> io::Result<()> {
        if !self.is_json() {
            // CURLOPT_HEADER supplies the selected headers through the body callback.
            if !header {
                let file = self.ensure_file()?;
                file.write_all(bytes)?;
                if flush {
                    file.flush()?;
                }
            }
            return Ok(());
        }
        if header && !self.include_headers {
            return Ok(());
        }
        if !header && self.head {
            return Ok(());
        }
        let used = self.body.len() + self.headers.len();
        if bytes.len() > JSON_LIMIT.saturating_sub(used) {
            return Err(io::Error::other(
                "JSON export exceeds 64 MiB; use --txt or ordinary -o for larger responses",
            ));
        }
        let destination = if header {
            &mut self.headers
        } else {
            &mut self.body
        };
        destination
            .try_reserve(bytes.len())
            .map_err(|_| io::Error::other("cannot allocate JSON export buffer"))?;
        destination.extend_from_slice(bytes);
        Ok(())
    }

    pub fn finish(&mut self, status: i64, exit_code: i32) -> io::Result<Option<PathBuf>> {
        if !self.is_json() {
            if exit_code == 0 {
                self.ensure_file()?;
            }
            if let Some(file) = &mut self.file {
                file.flush()?;
            }
        } else {
            let destination: Box<dyn Write> = if self.mode == ExportMode::JsonFile {
                self.ensure_file()?;
                Box::new(self.file.take().expect("export file opened"))
            } else {
                Box::new(io::stdout())
            };
            let mut out = BufWriter::new(destination);
            write!(out, "{{\n  \"schema_version\": 1,\n  \"status\": {status},\n  \"exit_code\": {exit_code}")?;
            if self.include_headers {
                let utf8 = std::str::from_utf8(&self.headers).is_ok();
                write!(
                    out,
                    ",\n  \"headers_encoding\": \"{}\",\n  \"headers\": [",
                    encoding(utf8)
                )?;
                for (index, line) in self.headers.split_inclusive(|b| *b == b'\n').enumerate() {
                    if index != 0 {
                        out.write_all(b",")?;
                    }
                    out.write_all(b"\n    ")?;
                    json_bytes(&mut out, line, utf8)?;
                }
                out.write_all(b"\n  ]")?;
            }
            if !self.head {
                let utf8 = std::str::from_utf8(&self.body).is_ok();
                write!(
                    out,
                    ",\n  \"body_encoding\": \"{}\",\n  \"body\": ",
                    encoding(utf8)
                )?;
                json_bytes(&mut out, &self.body, utf8)?;
            }
            out.write_all(b"\n}\n")?;
            out.flush()?;
        }
        Ok(self.path.clone())
    }
}

fn encoding(utf8: bool) -> &'static str {
    if utf8 {
        "utf-8"
    } else {
        "base64"
    }
}

// Callers validate UTF-8 once for the entire field before splitting header lines.
fn json_bytes(out: &mut dyn Write, bytes: &[u8], utf8: bool) -> io::Result<()> {
    out.write_all(b"\"")?;
    if utf8 {
        for byte in bytes {
            match byte {
                b'"' => out.write_all(b"\\\"")?,
                b'\\' => out.write_all(b"\\\\")?,
                b'\n' => out.write_all(b"\\n")?,
                b'\r' => out.write_all(b"\\r")?,
                b'\t' => out.write_all(b"\\t")?,
                0..=31 => write!(out, "\\u{byte:04x}")?,
                _ => out.write_all(&[*byte])?,
            }
        }
    } else {
        const ALPHABET: &[u8; 64] =
            b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        for chunk in bytes.chunks(3) {
            let a = chunk[0] as usize;
            let b = *chunk.get(1).unwrap_or(&0) as usize;
            let c = *chunk.get(2).unwrap_or(&0) as usize;
            out.write_all(&[
                ALPHABET[a >> 2],
                ALPHABET[((a & 3) << 4) | (b >> 4)],
                if chunk.len() > 1 {
                    ALPHABET[((b & 15) << 2) | (c >> 6)]
                } else {
                    b'='
                },
                if chunk.len() > 2 {
                    ALPHABET[c & 63]
                } else {
                    b'='
                },
            ])?;
        }
    }
    out.write_all(b"\"")
}

fn url_slug(url: &str) -> String {
    let Ok(url) = CString::new(url) else {
        return "response".into();
    };
    let mut parts = [0 as c_char; 1024];
    // libcurl validates the URL and excludes userinfo, query and fragment.
    // Malformed input must never become part of a filename.
    if unsafe { ci_url_host_path(url.as_ptr(), parts.as_mut_ptr(), parts.len()) } == 0 {
        return "response".into();
    }
    let parts = unsafe { CStr::from_ptr(parts.as_ptr()) }.to_bytes();
    let mut slug = String::new();
    for byte in parts {
        if slug.len() >= 96 {
            break;
        }
        if byte.is_ascii_alphanumeric() {
            slug.push((*byte as char).to_ascii_lowercase());
        } else if !slug.is_empty() && !slug.ends_with('-') {
            slug.push('-');
        }
    }
    let slug = slug.trim_end_matches('-');
    if slug.is_empty() {
        "response".into()
    } else {
        slug.into()
    }
}
