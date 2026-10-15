//! Private temporary storage. Open files are unlinked before any response bytes are written.
use std::{
    fs::{self, File, OpenOptions},
    io,
    os::unix::fs::OpenOptionsExt,
    path::Path,
    sync::atomic::{AtomicU64, Ordering},
};

static NEXT: AtomicU64 = AtomicU64::new(0);

pub(crate) fn create() -> io::Result<File> {
    create_in(&std::env::temp_dir())
}

fn create_in(directory: &Path) -> io::Result<File> {
    for _ in 0..1000 {
        let sequence = NEXT.fetch_add(1, Ordering::Relaxed);
        let path = directory.join(format!(".curlimp-{}-{sequence}.tmp", std::process::id()));
        match OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&path)
        {
            Ok(file) => {
                // All supported targets allow unlinking an open file. Refuse to
                // store payloads if immediate unlink fails.
                fs::remove_file(path)?;
                return Ok(file);
            }
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(error),
        }
    }
    Err(io::Error::new(
        io::ErrorKind::AlreadyExists,
        "cannot create a private response spool",
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        io::{Read, Seek, SeekFrom, Write},
        os::unix::fs::MetadataExt,
    };

    #[test]
    fn private_storage_is_unlinked_and_preserves_seekable_bytes() {
        let mut file = create().unwrap();
        let metadata = file.metadata().unwrap();
        assert_eq!(metadata.mode() & 0o777, 0o600);
        assert_eq!(metadata.nlink(), 0);
        file.write_all(b"a\x00\xffz").unwrap();
        file.seek(SeekFrom::Start(1)).unwrap();
        let mut actual = Vec::new();
        file.read_to_end(&mut actual).unwrap();
        assert_eq!(actual, b"\x00\xffz");
    }
}
