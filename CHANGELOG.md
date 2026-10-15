# Changelog

## 0.5.1 — 2026-10-15

### Security

- Backport the official ngtcp2 CVE-2026-40170 qlog buffer fix while keeping the pinned 1.20.0 source and existing impersonation changes.
- Add an AddressSanitizer regression for long qlog transport-parameter events on Linux amd64/arm64 and macOS arm64. Test instrumentation is not included in published artifacts.
- Record the c-ares CVE-2026-33630 disposition against the exact 1.34.8 source archive and build recipe, which retain the upstream 1.34.7 fix despite conflicting advisory metadata.
- Keep reviewed findings and primary evidence visible in native dependency reports. Changed source hashes, patches, build recipes, or advisory ranges reopen triage; new and ambiguous advisories still fail closed.

CLI behavior, native dependency versions, and the 38 browser profiles are unchanged.

## 0.5.0 — 2026-10-14

### Multiple transfers

- Accept several HTTP(S) URLs, sequentially by default, with one common profile and request configuration. Pair `-o` destinations with URLs by ordinal position; missing destinations use stdout.
- Add `-Z` / `--parallel`, `--no-parallel`, and `--parallel-max`. The default maximum is 50; setting only the maximum does not enable parallelism. Use independent outputs or JSON exports to avoid interleaved parallel stdout.
- Drive transfers through libcurl multi, reusing connections and sharing cookies within the invocation. Prepare request input once, write one final cookie jar, open a shared `-D` destination once, and apply `-w` to each completed transfer.
- Sequential exit status follows the last transfer; parallel execution retains the first observed failure. Ordinary transfer errors do not stop queued URLs. Export storage failures remain exit 23.

### Response exports

- Create one automatic TXT or JSON file per URL. Multi-URL JSON includes `transfer_index` and a normalized `url` without credentials or fragment. Query strings remain; malformed URLs use an empty URL field.
- Emit an input-ordered array for multi-URL `--json-output`, including ordinary failed transfers. Preserve the single-URL JSON object and selected body/header semantics.
- Replace JSON payload buffers with private, unlink-on-open temporary files and bounded chunked serialization. Preserve the 64 MiB selected-content limit per response. JSON needs writable temporary storage; aggregate storage/serialization failures suppress the array and return 23.

### Validation and scope

- Add local fixtures for concurrency limits, queue advancement, cookies, ordinal outputs, binary exports, failure handling, temporary-storage errors, and bounded memory/file descriptors. Run transfer checks in the minimal Linux filesystem and extracted Linux/macOS bundles.
- Keep the native dependency versions, 38 browser profiles, and Chrome 150 default unchanged. `--next`, URL globbing, per-URL profiles, retries, and progress meters remain unsupported. Browser fingerprint equivalence and HTTP/3 fidelity remain unverified.

## 0.4.0 — 2026-10-14

### Behavior and compatibility

- Correct CA trust precedence: explicit `--cacert` or `CURL_CA_BUNDLE` suppresses `SSL_CERT_DIR`; without either, `SSL_CERT_FILE` and `SSL_CERT_DIR` can both apply.
- Preserve an existing `-o` file after a successful HTTP 304 when no selected response bytes arrive. Validate profiles before opening response or header files. Read stdin body, header and write-out sources in argument order, including superseded `-w @-` readers.
- Make `-I` select HEAD and included headers according to flag order; a later `--no-include` keeps HEAD but omits selected headers, including in exports. Reject `--json-output -c -` before transfer so stdout remains one JSON document. TXT and JSON-file exports may still use a stdout cookie jar.
- Mask supported `-u`/`-U` credential forms in the process argument area after startup on shipped Linux and macOS builds. Shell history remains exposed, and startup observation races remain possible. Remove a redundant resolved upload buffer after handing a copy to libcurl; uploads remain buffered.
- Retire `okhttp4_android` and the native `okhttp4` alias because the preset's headers were inconsistent with the advertised client. Both names now fail early. The catalog has 38 browser profiles; `chrome150` remains the default.

### Native inputs and distribution

- Update zlib to 1.3.2. Keep nghttp2 at 1.63.0 for legacy HTTP/2 priorities and backport the official stop-reading fix for CVE-2026-27135. The release does not imply that an exploit against Curlimp was demonstrated or that browser fingerprints changed.
- Refresh the five copied Debian runtime packages through a weekly UTC cache generation and record package versions and refresh generation. Test the final derived image on both Linux architectures with bounded DNS/HTTPS and a mounted nonroot JSON export. A refresh creates a new candidate; existing version tags are not republished.
- Set the root Dockerfile's default runtime image to the versioned `juanfontes/curlimp:0.4.0` tag, with `RUNTIME_IMAGE` available for digest selection. Gate Docker `latest`, Docker Hub stable text, GitHub Latest, and Pages against the same newer-stable policy and complete published downloads. Versioned releases can remain available without advancing stable channels.
- Add a read-only dependency report for official release sources and curl/nghttp2 advisories. It identifies manual review candidates, not complete vulnerability coverage; network and schema failures produce an incomplete report and nonzero result.

Use `docker pull juanfontes/curlimp` for a refreshed stable image, or pin `juanfontes/curlimp:0.4.0` (or a digest). Native Linux amd64/arm64 and experimental macOS Apple Silicon bundles are accompanied by `SHA256SUMS`; verify the matching archive and keep its extracted files together. macOS binaries target 13.0 and are signed ad hoc, not notarized; validation on an actual macOS 13 system is not claimed. Windows and Intel Mac native bundles are unavailable.

Release checks require the exact source revision to pass Linux amd64, Linux arm64 and Apple Silicon CI, including package and final-container checks. Real-browser fingerprint equivalence and HTTP/3 browser fidelity remain unverified.

## 0.3.1 — 2026-10-14

### Security and native engine

- Update the patched libcurl engine to 8.23.0, incorporating upstream security fixes, including the HTTP/2 upload use-after-free fix (CVE-2026-92392). Browser profile definitions remain unchanged.
- Build libpsl 0.23.3 with its pinned, built-in Public Suffix List. Cookies scoped to public or private suffixes are rejected; legitimate parent-domain cookies remain supported. No runtime database download is required.
- Require PSL support in native feature checks and include libpsl, Chromium DAFSA, and Public Suffix List source notices in distributed packages.

### Fixes

- Honor the `;auto` suffix in `-e` / `--referer`: preserve an optional initial Referer and update it when following redirects. Repeated options use the last value.
- Rebuild the C bridge and relink the CLI when native headers, libraries, or provenance change at the same installation path.

### Validation and maintenance

- Add regression coverage for automatic Referer handling, public/private/internationalized suffix cookies, valid domain exceptions, and native build invalidation.
- Cache native CI builds while rerunning runtime tests, and deploy documentation only after matching release downloads and Docker platforms are published.

The release retains 39 profiles, the `chrome150` default, and the existing CLI scope. Browser fingerprint equivalence and HTTP/3 end-to-end behavior remain unverified.

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
