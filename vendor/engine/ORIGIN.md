# Vendored native engine build inputs

Imported native engine baseline: **2.2.3**.
Source revision: `6e8f87760a4dd96771e96fc9d55440dcd8845243`.

The source archive was verified with SHA-256:
`861dcba65752c3408b1ce23e4ac9861b330f544d67e77e3c9bc47f897839b129`.
The snapshot is incorporated directly in this project.

The imported subset contains CMakeLists.txt, Makefile, LICENSE, three CMake
helpers, the libidn2 preparation script, and five dependency patches. All 12
imported files were initially byte-for-byte copies. Executable permissions are preserved.
Browser profile definitions are included in patches/curl.patch. The Rust CLI
uses its own profile-name catalog and does not need the upstream CLI wrappers,
CI workflows, documentation, or test harness, which are not imported here.

The original MIT notice is preserved in LICENSE. The build downloads curl,
BoringSSL, and the other native dependencies from their respective source hosts;
those full dependency trees are not included in this directory. Their license
notices are collected during compilation and shipped with the runtime.

SHA256SUMS lists this document and every imported file. Its SHA-256 is pinned in
the root engine.lock. Update both when intentionally changing the snapshot,
and record the origin of any replacement files. The import revision describes
the baseline; it does not replace the file checksums.

## Local maintenance in Curlimp 0.3.1

- Rebase the curl impersonation patch onto the official `curl-8_23_0` tag,
  preserving upstream security fixes and the existing browser profile definitions.
- Update the pinned curl archive and build libpsl 0.23.3 statically with its
  bundled Public Suffix List. Require PSL support in native feature checks.
- Collect libpsl, Chromium DAFSA, and Public Suffix List source notices with
  the other dependency licenses.

These local changes are covered by the current manifest; the baseline revision
above remains historical provenance, not the version of every dependency.
