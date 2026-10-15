//! Opt-in response exports; ordinary curl-style output stays in the engine.
use crate::{
    cli::{CliError, Config, ExportMode},
    export_field::{self, Field},
    spool,
};
#[cfg(unix)]
use std::os::unix::fs::OpenOptionsExt;
use std::{
    ffi::{c_char, c_int, CStr, CString},
    fs::{File, OpenOptions},
    io::{self, BufWriter, Read, Seek, SeekFrom, Write},
    path::PathBuf,
};

extern "C" {
    fn ci_local_timestamp(buffer: *mut c_char, capacity: usize) -> c_int;
    fn ci_report_url(url: *const c_char) -> *mut c_char;
    fn ci_string_free(value: *mut c_char);
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
    body: Field,
    headers: Field,
    identity: Option<TransferIdentity>,
}

impl Export {
    pub fn new(config: &Config, mode: ExportMode, url: &str) -> Result<Self, CliError> {
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
            stem: format!("{timestamp}_{}", url_slug(url)),
            path: None,
            file: None,
            body: Field::default(),
            headers: Field::default(),
            identity: None,
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
        let used = self.body.len + self.headers.len;
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
        destination.append(bytes)
    }

    pub fn identify(&mut self, index: usize, url: &str) -> Result<(), CliError> {
        let url = CString::new(url).map_err(|_| CliError::new(2, "URL contains a NUL byte"))?;
        let pointer = unsafe { ci_report_url(url.as_ptr()) };
        let url = if pointer.is_null() {
            // Malformed URLs must not leak raw credential text into a report.
            String::new()
        } else {
            let value = unsafe { CStr::from_ptr(pointer) }
                .to_string_lossy()
                .into_owned();
            unsafe { ci_string_free(pointer) };
            value
        };
        self.identity = Some(TransferIdentity {
            transfer_index: index,
            url,
        });
        Ok(())
    }

    fn write_json(&mut self, out: &mut dyn Write, status: i64, code: i32) -> io::Result<()> {
        write!(
            out,
            "{{\n  \"schema_version\": 1,\n  \"status\": {status},\n  \"exit_code\": {code}"
        )?;
        if let Some(identity) = &self.identity {
            write!(
                out,
                ",\n  \"transfer_index\": {},\n  \"url\": ",
                identity.transfer_index
            )?;
            export_field::string(out, &identity.url)?;
        }
        if self.include_headers {
            write!(
                out,
                ",\n  \"headers_encoding\": \"{}\",\n  \"headers\": ",
                self.headers.encoding()
            )?;
            self.headers.json(out, true)?;
        }
        if !self.head {
            write!(
                out,
                ",\n  \"body_encoding\": \"{}\",\n  \"body\": ",
                self.body.encoding()
            )?;
            self.body.json(out, false)?;
        }
        out.write_all(b"\n}\n")
    }

    pub(crate) fn finish(
        &mut self,
        status: i64,
        exit_code: i32,
        aggregate: Option<&mut Aggregate>,
    ) -> io::Result<Option<PathBuf>> {
        if !self.is_json() {
            if exit_code == 0 {
                self.ensure_file()?;
            }
            if let Some(file) = &mut self.file {
                file.flush()?;
            }
        } else if let Some(aggregate) = aggregate {
            aggregate.push(self, status, exit_code)?;
        } else {
            let destination: Box<dyn Write> = if self.mode == ExportMode::JsonFile {
                self.ensure_file()?;
                Box::new(self.file.take().expect("export file opened"))
            } else {
                Box::new(io::stdout())
            };
            let mut out = BufWriter::new(destination);
            self.write_json(&mut out, status, exit_code)?;
            out.flush()?;
        }
        Ok(self.path.clone())
    }
}

struct TransferIdentity {
    transfer_index: usize,
    url: String,
}

pub(crate) struct Aggregate {
    file: File,
    entries: Vec<Option<(u64, u64)>>,
}

impl Aggregate {
    pub fn new(count: usize) -> io::Result<Self> {
        let mut entries = Vec::new();
        entries
            .try_reserve_exact(count)
            .map_err(|_| io::Error::other("cannot allocate JSON result index"))?;
        entries.resize(count, None);
        Ok(Self {
            file: spool::create()?,
            entries,
        })
    }

    fn push(&mut self, export: &mut Export, status: i64, code: i32) -> io::Result<()> {
        let index = export
            .identity
            .as_ref()
            .ok_or_else(|| io::Error::other("missing transfer identity"))?
            .transfer_index;
        let start = self.file.stream_position()?;
        {
            let mut writer = BufWriter::new(&mut self.file);
            export.write_json(&mut writer, status, code)?;
            writer.flush()?;
        }
        let end = self.file.stream_position()?;
        let entry = self
            .entries
            .get_mut(index)
            .ok_or_else(|| io::Error::other("invalid transfer identity"))?;
        if entry.is_some() {
            return Err(io::Error::other("duplicate transfer result"));
        }
        *entry = Some((start, end - start));
        Ok(())
    }

    pub fn finish(&mut self, out: &mut dyn Write) -> io::Result<()> {
        if self.entries.iter().any(Option::is_none) {
            return Err(io::Error::other("incomplete JSON result set"));
        }
        out.write_all(b"[\n")?;
        let mut buffer = [0; 64 * 1024];
        for (index, entry) in self.entries.iter().enumerate() {
            let (offset, mut remaining) = entry.expect("validated complete result set");
            if index != 0 {
                out.write_all(b",\n")?;
            }
            self.file.seek(SeekFrom::Start(offset))?;
            while remaining != 0 {
                let count = (remaining as usize).min(buffer.len());
                self.file.read_exact(&mut buffer[..count])?;
                out.write_all(&buffer[..count])?;
                remaining -= count as u64;
            }
        }
        out.write_all(b"]\n")?;
        out.flush()
    }
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
