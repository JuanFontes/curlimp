# Changelog

## 0.3.0 — 2026-10-11

### Features

- Rust CLI with familiar curl-style options, calling a modified libcurl engine through a small C bridge.
- Browser impersonation enabled by default with the fixed `chrome150` profile and automatic response decompression.
- 39 browser and HTTP client profiles. Select an exact profile before the URL or with `--impersonate`; inspect the catalog with `--list-profiles`.
- Optional Zsh profile completion with literal prefix matching of any length. `--completions zsh` prints the integration script.
- HTTP requests, redirects, authentication, cookies, proxies, TLS configuration, headers, body output and selected write-out variables.
- `--txt` and `--json-file` save timestamped response files; `--json-output` prints a structured response object. Body-only, `-i` headers/body and `-I` headers-only selection are preserved.
- JSON exports retain complete text or explicit Base64 for binary content, with a 64 MiB selected-content limit. TXT exports stream raw bytes. `--json DATA` sends request JSON.

### Distribution

- Build and packaging support for Docker and native Linux amd64/arm64 bundles, plus experimental macOS Apple Silicon packages.
- Zsh completion, dependency notices, checksums and source provenance included with native packages.
- Documentation covering profiles, practical request examples, output formats, builds and compatibility limits.

### Scope

One URL per invocation and a documented subset of curl flags. The CLI does not render pages or execute JavaScript. HTTP/3 behavior and equivalence to real-browser fingerprints remain unverified.

The macOS package is signed ad hoc and is not notarized. Windows and Intel Mac native packages are not available. See the [compatibility guide](README.md#current-compatibility) and [platform table](README.md#platform-support).
