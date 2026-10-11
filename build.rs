use std::{env, path::PathBuf, process::Command};

fn main() {
    println!("cargo:rerun-if-changed=native/bridge.c");
    println!("cargo:rerun-if-env-changed=CURL_IMPERSONATE_DIR");
    println!("cargo:rerun-if-env-changed=CC");
    println!("cargo:rerun-if-env-changed=AR");
    let root = PathBuf::from(env::var("CURL_IMPERSONATE_DIR").expect(
        "Set CURL_IMPERSONATE_DIR to the verified native release directory; see README.md or build with Docker",
    ));
    let root = root
        .canonicalize()
        .expect("native release directory is missing");
    assert!(
        root.join("include/curl/curl.h").is_file(),
        "native headers are missing"
    );
    let libs = if root.join("lib").is_dir() {
        root.join("lib")
    } else {
        root.clone()
    };
    let out = PathBuf::from(env::var_os("OUT_DIR").unwrap());
    let status = Command::new(env::var_os("CC").unwrap_or_else(|| "cc".into()))
        .args([
            "-std=c11", "-O2", "-fPIC", "-Wall", "-Wextra", "-Werror", "-I",
        ])
        .arg(root.join("include"))
        .args(["-c", "native/bridge.c", "-o"])
        .arg(out.join("bridge.o"))
        .status()
        .expect("C compiler is required");
    assert!(status.success(), "compiling the native ABI bridge failed");
    let status = Command::new(env::var_os("AR").unwrap_or_else(|| "ar".into()))
        .arg("crs")
        .arg(out.join("libimpersonate_bridge.a"))
        .arg(out.join("bridge.o"))
        .status()
        .expect("ar is required");
    assert!(status.success(), "archiving the native ABI bridge failed");
    println!("cargo:rustc-link-search=native={}", out.display());
    println!("cargo:rustc-link-search=native={}", libs.display());
    println!("cargo:rustc-link-lib=static=impersonate_bridge");
    println!("cargo:rustc-link-lib=dylib=curl-impersonate");
    println!("cargo:rustc-link-arg=-Wl,-rpath,{}", libs.display());
}
