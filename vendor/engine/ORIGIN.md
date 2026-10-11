# Vendored native engine build inputs

Imported native engine baseline: **2.2.3**.
Source revision: `6e8f87760a4dd96771e96fc9d55440dcd8845243`.

The source archive was verified with SHA-256:
`861dcba65752c3408b1ce23e4ac9861b330f544d67e77e3c9bc47f897839b129`.
The snapshot is incorporated directly in this project.

The imported subset contains CMakeLists.txt, Makefile, LICENSE, three CMake
helpers, the libidn2 preparation script, and five dependency patches. All 12
imported files are byte-for-byte copies. Executable permissions are preserved.
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
