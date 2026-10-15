//! Bounded-memory JSON fields with whole-field UTF-8 validation.
use crate::spool;
use std::{
    fs::File,
    io::{self, Read, Seek, Write},
};

const CHUNK: usize = 64 * 1024;

#[derive(Default)]
struct Utf8 {
    invalid: bool,
    remaining: u8,
    minimum: u8,
    maximum: u8,
}

impl Utf8 {
    fn feed(&mut self, bytes: &[u8]) {
        for &byte in bytes {
            if self.invalid {
                return;
            }
            if self.remaining != 0 {
                if byte < self.minimum || byte > self.maximum {
                    self.invalid = true;
                    return;
                }
                self.remaining -= 1;
                self.minimum = 0x80;
                self.maximum = 0xbf;
            } else {
                let (count, minimum, maximum) = match byte {
                    0..=0x7f => (0, 0, 0),
                    0xc2..=0xdf => (1, 0x80, 0xbf),
                    0xe0 => (2, 0xa0, 0xbf),
                    0xed => (2, 0x80, 0x9f),
                    0xe1..=0xec | 0xee..=0xef => (2, 0x80, 0xbf),
                    0xf0 => (3, 0x90, 0xbf),
                    0xf1..=0xf3 => (3, 0x80, 0xbf),
                    0xf4 => (3, 0x80, 0x8f),
                    _ => {
                        self.invalid = true;
                        return;
                    }
                };
                self.remaining = count;
                self.minimum = minimum;
                self.maximum = maximum;
            }
        }
    }
}

#[derive(Default)]
pub(crate) struct Field {
    file: Option<File>,
    pub len: usize,
    utf8: Utf8,
}

impl Field {
    pub fn append(&mut self, bytes: &[u8]) -> io::Result<()> {
        if bytes.is_empty() {
            return Ok(());
        }
        if self.file.is_none() {
            self.file = Some(spool::create()?);
        }
        self.file
            .as_mut()
            .expect("spool created")
            .write_all(bytes)?;
        self.utf8.feed(bytes);
        self.len += bytes.len();
        Ok(())
    }

    pub fn encoding(&self) -> &'static str {
        if !self.utf8.invalid && self.utf8.remaining == 0 {
            "utf-8"
        } else {
            "base64"
        }
    }

    pub fn json(&mut self, out: &mut dyn Write, lines: bool) -> io::Result<()> {
        let utf8 = self.encoding() == "utf-8";
        let mut encoder = Encoder::new(utf8);
        if lines {
            out.write_all(b"[")?;
        } else {
            out.write_all(b"\"")?;
        }
        let mut line_open = false;
        let mut any_line = false;
        if let Some(file) = &mut self.file {
            file.rewind()?;
            let mut buffer = [0; CHUNK];
            loop {
                let count = file.read(&mut buffer)?;
                if count == 0 {
                    break;
                }
                if !lines {
                    encoder.write(out, &buffer[..count])?;
                    continue;
                }
                for part in buffer[..count].split_inclusive(|&b| b == b'\n') {
                    if !line_open {
                        if any_line {
                            out.write_all(b",")?;
                        }
                        out.write_all(b"\n    \"")?;
                        line_open = true;
                        any_line = true;
                    }
                    encoder.write(out, part)?;
                    if part.last() == Some(&b'\n') {
                        encoder.finish(out)?;
                        out.write_all(b"\"")?;
                        line_open = false;
                    }
                }
            }
        }
        if !lines || line_open {
            encoder.finish(out)?;
            out.write_all(b"\"")?;
        }
        if lines {
            out.write_all(b"\n  ]")?;
        }
        Ok(())
    }
}

pub(crate) fn string(out: &mut dyn Write, value: &str) -> io::Result<()> {
    out.write_all(b"\"")?;
    escaped(out, value.as_bytes())?;
    out.write_all(b"\"")
}

fn escaped(out: &mut dyn Write, bytes: &[u8]) -> io::Result<()> {
    let mut start = 0;
    for (index, &byte) in bytes.iter().enumerate() {
        if byte >= 32 && byte != b'"' && byte != b'\\' {
            continue;
        }
        out.write_all(&bytes[start..index])?;
        match byte {
            b'"' => out.write_all(b"\\\"")?,
            b'\\' => out.write_all(b"\\\\")?,
            b'\n' => out.write_all(b"\\n")?,
            b'\r' => out.write_all(b"\\r")?,
            b'\t' => out.write_all(b"\\t")?,
            _ => write!(out, "\\u{byte:04x}")?,
        }
        start = index + 1;
    }
    out.write_all(&bytes[start..])
}

struct Encoder {
    utf8: bool,
    pending: [u8; 3],
    used: usize,
}

impl Encoder {
    fn new(utf8: bool) -> Self {
        Self {
            utf8,
            pending: [0; 3],
            used: 0,
        }
    }

    fn write(&mut self, out: &mut dyn Write, mut bytes: &[u8]) -> io::Result<()> {
        if self.utf8 {
            return escaped(out, bytes);
        }
        if self.used != 0 {
            let take = (3 - self.used).min(bytes.len());
            self.pending[self.used..self.used + take].copy_from_slice(&bytes[..take]);
            self.used += take;
            bytes = &bytes[take..];
            if self.used == 3 {
                base64(out, &self.pending)?;
                self.used = 0;
            }
        }
        let count = bytes.len() / 3 * 3;
        base64(out, &bytes[..count])?;
        if !bytes[count..].is_empty() {
            self.used = bytes.len() - count;
            self.pending[..self.used].copy_from_slice(&bytes[count..]);
        }
        Ok(())
    }

    fn finish(&mut self, out: &mut dyn Write) -> io::Result<()> {
        base64(out, &self.pending[..self.used])?;
        self.used = 0;
        Ok(())
    }
}

fn base64(out: &mut dyn Write, bytes: &[u8]) -> io::Result<()> {
    const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
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
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn large_field_serialization_uses_bounded_writes() {
        struct Sink {
            largest: usize,
            total: usize,
        }
        impl Write for Sink {
            fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
                self.largest = self.largest.max(bytes.len());
                self.total += bytes.len();
                Ok(bytes.len())
            }
            fn flush(&mut self) -> io::Result<()> {
                Ok(())
            }
        }
        let mut field = Field::default();
        for _ in 0..32 {
            field.append(&[b'a'; 65536]).unwrap();
        }
        let mut sink = Sink {
            largest: 0,
            total: 0,
        };
        field.json(&mut sink, false).unwrap();
        assert_eq!(sink.total, 2 * 1024 * 1024 + 2);
        assert!(sink.largest <= 65536);
    }

    #[test]
    fn utf8_state_matches_standard_validation_across_chunk_boundaries() {
        for bytes in [
            "é☃😀".as_bytes(),
            b"\xed\xa0\x80",
            b"\xf4\x90\x80\x80",
            b"\xe0\x9f\xbf",
            b"\xc0\xaf",
            b"\xf0\x90",
            b"\x80",
        ] {
            for split in 0..=bytes.len() {
                let mut field = Field::default();
                field.append(&bytes[..split]).unwrap();
                field.append(&bytes[split..]).unwrap();
                assert_eq!(
                    field.encoding() == "utf-8",
                    std::str::from_utf8(bytes).is_ok()
                );
            }
        }
    }

    #[test]
    fn header_lines_and_base64_carry_survive_serialization_chunks() {
        let mut field = Field::default();
        field.append(b"\xff\n\x80\r\n").unwrap();
        let mut result = Vec::new();
        field.json(&mut result, true).unwrap();
        assert_eq!(result, b"[\n    \"/wo=\",\n    \"gA0K\"\n  ]");
        for chunk_size in 1..=5 {
            let mut encoder = Encoder::new(false);
            let mut result = Vec::new();
            for chunk in b"\xffhello\x80world".chunks(chunk_size) {
                encoder.write(&mut result, chunk).unwrap();
            }
            encoder.finish(&mut result).unwrap();
            assert_eq!(result, b"/2hlbGxvgHdvcmxk");
        }
    }
}
