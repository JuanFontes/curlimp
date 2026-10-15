<div align="center">

<h1>🦎 Curlimp</h1>

<p><strong>Browser profiles. Familiar curl commands. Responses you can keep.</strong></p>

<p>Send HTTP requests with browser-specific TLS and HTTP settings.<br>
Run with Docker or a native download, explore responses, and save what matters.</p>

<p>
  <a href="Cargo.toml"><img src="https://img.shields.io/badge/Rust-CLI-E57324?style=for-the-badge&amp;logo=rust&amp;logoColor=white" alt="Rust CLI"></a>
  <a href="native/bridge.c"><img src="https://img.shields.io/badge/C-Native_bridge-526D82?style=for-the-badge&amp;logo=c&amp;logoColor=white" alt="C native bridge"></a>
  <a href="vendor/engine/"><img src="https://img.shields.io/badge/libcurl-Engine-073551?style=for-the-badge&amp;logo=curl&amp;logoColor=white" alt="Modified libcurl engine"></a>
  <a href="https://hub.docker.com/r/juanfontes/curlimp"><img src="https://img.shields.io/badge/Docker-Ready_to_run-2496ED?style=for-the-badge&amp;logo=docker&amp;logoColor=white" alt="Ready-to-run Docker image"></a>
</p>

<p>
  <a href="https://github.com/JuanFontes/curlimp/actions/workflows/ci.yml?query=branch%3Amain"><img src="https://img.shields.io/github/actions/workflow/status/JuanFontes/curlimp/ci.yml?branch=main&amp;style=flat-square&amp;label=CI&amp;logo=githubactions&amp;logoColor=white" alt="Build and package CI status on main"></a>
  <a href="https://github.com/JuanFontes/curlimp/releases/latest"><img src="https://img.shields.io/github/v/release/JuanFontes/curlimp?style=flat-square&amp;label=Release&amp;color=0F766E" alt="Latest stable release"></a>
  <a href="https://juanfontes.github.io/curlimp/docs/profiles/"><img src="https://img.shields.io/badge/Profiles-38-0F766E?style=flat-square" alt="38 browser profiles"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-0F766E?style=flat-square" alt="MIT license"></a>
</p>

<p>
  <a href="https://juanfontes.github.io/curlimp/">🌐 Website &amp; docs</a> ·
  <a href="https://hub.docker.com/r/juanfontes/curlimp">🐳 Docker Hub</a> ·
  <a href="https://github.com/JuanFontes/curlimp/releases/latest">📦 Downloads</a> ·
  <a href="#quick-start">🚀 Quick start</a> ·
  <a href="CONTRIBUTING.md">🤝 Contributing</a>
</p>

</div>

## 🦎 What is Curlimp?

Curlimp is a command-line HTTP client for making requests with browser-specific network settings. It applies versioned browser profiles to a modified libcurl engine, including TLS and HTTP configuration that goes beyond changing a User-Agent header.

The project brings those profiles into an everyday terminal workflow: inspect headers and bodies, test redirects and HTTP errors, run batches, and keep responses for later. Ready-made Docker images and native downloads let you start without compiling the engine.

**The command-line layer is written in Rust.** It handles arguments, transfer scheduling, output, and errors; a small C bridge calls the existing native engine. The engine supplies transport and browser profile behavior. Read [why the project exists](https://juanfontes.github.io/curlimp/docs/why/) and [how it works](https://juanfontes.github.io/curlimp/docs/architecture/).

## ✨ Features at a glance

| Feature                                     | What you can do                                                                                                              |
| ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| 🎭 **Browser profiles**                     | Choose among 38 presets covering Chrome, Firefox, Safari, Edge, Tor Browser, and mobile variants. Chrome 150 is the default. |
| 🧰 **Familiar request options**             | Work with headers, request bodies, authentication, cookies, proxies, redirects, and selected curl write-out variables.       |
| 📖 **Automatic response decoding**          | Receive decompressed response bytes while a browser profile is active; opt out with `--no-compressed`.                       |
| 🔀 **Multiple URLs and parallel transfers** | Run URLs sequentially or set a concurrency limit, with independent output destinations.                                      |
| 💾 **TXT and JSON exports**                 | Keep complete response content in timestamped files, or print structured JSON for one response or an entire batch.           |
| 📦 **Ready-to-run packages**                | Use Docker on Linux amd64/arm64 or native Linux bundles; macOS Apple Silicon downloads are experimental.                     |
| ⌨️ **Zsh profile completion**               | Press Tab to discover profiles and filter them by any prefix length.                                                         |

**Jump to:** [Quick start](#quick-start) · [Examples](#http-examples) · [Profiles](#browser-profiles) · [Multiple URLs](#multiple-urls) · [Exports](#response-exports) · [Downloads](#platform-support) · [Documentation](#documentation)

<a id="quick-start"></a>
<a id="use-the-published-docker-image"></a>

## 🚀 Quick start

With Docker installed, make your first request:

```sh
docker run --rm juanfontes/curlimp -sS -I https://httpbin.org/status/200
```

This sends a HEAD request and prints the response headers. Docker downloads the image if it is missing and selects the matching Linux CPU architecture. Put Curlimp options directly after the image name.

**Chrome 150 impersonation and response decompression are enabled by default.** To select another browser, put its exact profile name before the first URL:

```sh
docker run --rm juanfontes/curlimp firefox147 \
  -sS -i https://httpbin.org/status/418
```

Here, `-i` includes headers and the body. `/status/418` deliberately returns an HTTP error with a small body; `/status/200` has an empty body. `-sS` suppresses routine output while keeping error messages visible. `--impersonate firefox147` is also supported.

The untagged image uses Docker's `latest` tag, which follows promoted stable releases. Docker can reuse an older cached copy; update it with `docker pull juanfontes/curlimp`, or add `--pull=always` before the image name. For fixed deployments, pin `juanfontes/curlimp:0.5.0` or a digest. [Docker setup and updates →](https://juanfontes.github.io/curlimp/docs/docker/)

<a id="http-examples"></a>

## 🧰 Everyday examples

These examples use the native `curlimp` command. To use Docker, replace `curlimp` with `docker run --rm juanfontes/curlimp`. Named output files inside a container need a [host directory mount](#response-exports); shell redirection writes on the host.

### Inspect the response

```sh
# Print only the body.
curlimp -sS https://httpbin.org/status/418

# Make a HEAD request and print only headers.
curlimp -sS -I https://httpbin.org/status/200

# Print response headers followed by the body.
curlimp -sS -i https://httpbin.org/status/418

# Keep GET semantics, print headers, and discard the body.
curlimp -sS -D - -o /dev/null https://httpbin.org/status/200

# Print only the HTTP status code.
curlimp -sS -o /dev/null -w '%{http_code}\n' https://httpbin.org/status/502
```

### Follow redirects and handle errors

```sh
# Follow redirects and print the final status.
curlimp -sS -L -o /dev/null -w '%{http_code}\n' https://httpbin.org/status/301

# Return exit code 22 for this HTTP error while keeping its response body.
curlimp -sS --fail-with-body https://httpbin.org/status/418

# Send JSON with an extra request header.
curlimp -sS -i -H 'X-Request-Source: terminal' \
  --json '{"hello":"world"}' https://httpbin.org/status/201

# Print connection diagnostics to stderr with explicit timeouts.
curlimp -v --connect-timeout 10 --max-time 30 https://httpbin.org/status/200
```

HTTP errors do not make the transfer fail unless you enable `-f` or `--fail-with-body`. `-v` writes diagnostics to stderr; it does not add the response body to a HEAD request. Status endpoints demonstrate response handling; they do not echo request data or verify browser fingerprints.

**More recipes:** [body and headers](https://juanfontes.github.io/curlimp/docs/body-and-headers/) · [redirects and status codes](https://juanfontes.github.io/curlimp/docs/redirects-and-status/) · [request bodies](https://juanfontes.github.io/curlimp/docs/requests/).

<a id="browser-profiles"></a>

## 🎭 Choose a browser

Use a complete profile ID before the first URL, or pass `--impersonate PROFILE`. A profile describes the request's browser settings; its target platform does not have to match your computer.

| Browser           | Example profile     | Target                                     |
| ----------------- | ------------------- | ------------------------------------------ |
| Chrome            | `chrome150`         | Desktop; default profile                   |
| Firefox           | `firefox147`        | Desktop                                    |
| Safari            | `safari2601`        | Desktop                                    |
| Edge              | `edge101`           | Desktop                                    |
| Chrome on Android | `chrome131_android` | Android                                    |
| Safari on iOS     | `safari260_ios`     | iOS                                        |
| Tor Browser       | `tor145`            | Desktop preset; does not route through Tor |

```sh
# Select Safari on iOS.
curlimp safari260_ios -sS -I https://httpbin.org/status/200

# The explicit flag works too, including after other options.
curlimp -sS --impersonate firefox147 -I https://httpbin.org/status/200

# List every profile supported by the installed engine.
curlimp --list-profiles
```

Profiles are versioned presets, not a list that refreshes automatically. `--no-impersonate` disables profiles while keeping the same modified engine. Response decompression is automatic with a profile; `--no-compressed` preserves encoded bytes. With profiles disabled, use `--compressed` to enable decoding.

**[Browse all 38 profiles →](https://juanfontes.github.io/curlimp/docs/profiles/)** The full guide covers environment defaults, header controls, selection precedence, and profile limitations.

<a id="multiple-urls"></a>

## 🔀 Multiple URLs and parallel requests

List several URLs in one invocation. They run **sequentially by default**, using the same profile and request options. Line breaks are optional.

```sh
# First URL goes to test1.txt; second URL goes to test2.txt.
curlimp -sS -i https://httpbin.org/status/200 https://httpbin.org/status/502 \
  -o test1.txt -o test2.txt

# Print the first response and save only the second.
curlimp -sS -i https://httpbin.org/status/200 https://httpbin.org/status/502 \
  -o - -o response-502.txt

# Keep all sequential output in one file using shell redirection.
curlimp -sS -i https://httpbin.org/status/200 https://httpbin.org/status/502 > responses.txt
```

`-o` is optional: the first destination belongs to the first URL, the second to the second, regardless of where the flags appear. Missing destinations use stdout. Reusing the same path does not append responses; use distinct files or shell redirection.

Enable `--parallel` (or `-Z`) to run concurrent transfers. This example limits concurrency to two and prints one ordered JSON array:

```sh
docker run --rm juanfontes/curlimp \
  --parallel --parallel-max 2 --json-output -sS -i \
  https://httpbin.org/status/200 https://httpbin.org/status/418 https://httpbin.org/status/502
```

The default parallel limit is 50. `--parallel-max` alone does not enable parallel execution. Raw parallel stdout can interleave; distinct output files and JSON exports keep responses separate. The JSON array preserves **input URL order**, even when requests finish in a different order.

Sequential exit status follows the last transfer; parallel execution retains the first observed failure. Inspect each JSON result when every outcome matters. [Output pairing, cookies, errors, and concurrency details →](https://juanfontes.github.io/curlimp/docs/multiple-urls/)

<a id="response-exports"></a>

## 💾 Save and inspect responses

Keep a response without choosing a filename each time, or pass a structured result to another tool. These output modes are Curlimp extensions:

| Option          | Where it goes                                                               | With multiple URLs           |
| --------------- | --------------------------------------------------------------------------- | ---------------------------- |
| `--txt`         | Automatically named `.txt` file with the selected raw response bytes        | One file per URL             |
| `--json-file`   | Automatically named `.json` file with response fields and transfer metadata | One file per URL             |
| `--json-output` | A JSON response object on stdout                                            | One array in input URL order |

**Choose what to capture:** body only by default, headers and body with `-i`, or HEAD headers with `-I`. Complete HTML stays in a single `body` string; non-UTF-8 bytes use explicit Base64. JSON includes HTTP `status` and transfer `exit_code`. Multi-URL results also include `transfer_index` and a normalized URL with credentials and fragment removed. `--json DATA` still sends request JSON.

### Print JSON directly in the terminal

```sh
docker run --rm juanfontes/curlimp firefox147 \
  --json-output -sS -i https://httpbin.org/status/418

# Choose a filename with host shell redirection; no mount is needed.
docker run --rm juanfontes/curlimp \
  --json-output -sS -I https://httpbin.org/status/200 > response.json
```

### Save files from Docker

Mount the current directory at `/work` so exports survive `--rm`. On Unix hosts, `--user` creates files using your UID/GID:

```sh
# Save headers and body to a timestamped TXT file.
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" \
  juanfontes/curlimp --txt -sS -i https://httpbin.org/status/418

# Save one JSON file per URL, containing HEAD response headers.
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" \
  juanfontes/curlimp --parallel --json-file -sS -I \
  https://httpbin.org/status/200 https://httpbin.org/status/502
```

With the native executable, run `curlimp --txt -sS -i https://httpbin.org/status/418` in the directory where you want the file. Generated names look like `2026-10-15_14-32-08_httpbin-org-status-418.txt`: local timestamp plus sanitized host/path. Collisions get a suffix; existing files are never overwritten. Automatic files are owner-only on Unix. Response content and URL queries may contain private data; they are not redacted.

Choose one export mode per invocation. Exports reject `-o`, `-D`, and `-w`; JSON modes also reject `-N`. JSON uses private temporary storage and allows up to **64 MiB of selected content per response**. TXT and ordinary output stream without that JSON limit. Read-only Docker runs need writable temporary storage for JSON. [Full formats, encodings, storage requirements, and error behavior →](https://juanfontes.github.io/curlimp/docs/response-exports/)

<a id="platform-support"></a>
<a id="linux-downloads"></a>
<a id="macos-downloads"></a>

## 💻 Native downloads and autocomplete

**[Download the native bundles and SHA256SUMS →](https://github.com/JuanFontes/curlimp/releases/latest)**

| Platform                           | Native download | Validation and availability         |
| ---------------------------------- | :-------------: | ----------------------------------- |
| Linux x86-64 / amd64               |       ✅        | Tested on Ubuntu 24.04              |
| Linux ARM64 / aarch64              |       ✅        | Tested on Ubuntu 24.04 ARM          |
| macOS Apple Silicon (M1 and newer) |       🧪        | Experimental; tested in macOS 15 CI |
| macOS Intel                        |        —        | No native package                   |
| Windows                            |        —        | No native package                   |

Verify the archive against `SHA256SUMS` and **keep the entire extracted bundle together**. Linux packages include their loader and runtime libraries; macOS includes its engine in `lib/`. The [installation guide](https://juanfontes.github.io/curlimp/docs/installation/) covers extraction, checksum verification, and adding `curlimp` to your `PATH`.

macOS packages target macOS 13.0 and are signed ad hoc, not notarized. Validation on an actual macOS 13 system is not claimed. Windows and Intel Mac users can use the Linux Docker image with a suitable Docker installation.

### ⌨️ Enable profile completion in Zsh

With the native `curlimp` executable on your `PATH`, add this to `~/.zshrc`:

```zsh
# Skip these first two lines if your shell already initializes completion.
autoload -Uz compinit
compinit

source <(curlimp --completions zsh)
zstyle ':completion:*:curlimp:*' menu yes select
```

Open a new terminal, type `curlimp `, and press **Tab** to list profiles. Any prefix filters the choices: `c`, `chrome1`, `firefox14`, or `safari26`. Select a profile and press **Enter** to insert it, then finish the request. Executing a command requires an exact profile name.

Completion currently covers browser profiles in Zsh, including after `--impersonate`. It requires the native command on your host. [Setup and troubleshooting →](https://juanfontes.github.io/curlimp/docs/completion/)

<a id="documentation"></a>

## 📚 Go deeper

The website contains the complete usage guides, supported options, examples, and implementation details.

| Looking for…                                     | Read                                                                                                                                                                                                                                  |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Your first request, downloads, or Docker setup   | [Quick start](https://juanfontes.github.io/curlimp/docs/quick-start/) · [Installation](https://juanfontes.github.io/curlimp/docs/installation/) · [Docker](https://juanfontes.github.io/curlimp/docs/docker/)                         |
| Available browsers and completion                | [Profiles](https://juanfontes.github.io/curlimp/docs/profiles/) · [Zsh](https://juanfontes.github.io/curlimp/docs/completion/)                                                                                                        |
| Body, headers, redirects, and status codes       | [Response selection](https://juanfontes.github.io/curlimp/docs/body-and-headers/) · [Redirects and errors](https://juanfontes.github.io/curlimp/docs/redirects-and-status/)                                                           |
| JSON requests, forms, authentication, or cookies | [Requests](https://juanfontes.github.io/curlimp/docs/requests/) · [Authentication and cookies](https://juanfontes.github.io/curlimp/docs/authentication-and-cookies/)                                                                 |
| Batches, output files, or structured exports     | [Multiple URLs](https://juanfontes.github.io/curlimp/docs/multiple-urls/) · [Files and pipelines](https://juanfontes.github.io/curlimp/docs/files/) · [TXT/JSON exports](https://juanfontes.github.io/curlimp/docs/response-exports/) |
| Proxies, certificates, timeouts, or diagnostics  | [Networking](https://juanfontes.github.io/curlimp/docs/networking/)                                                                                                                                                                   |
| Every supported option and known limit           | [CLI reference](https://juanfontes.github.io/curlimp/docs/cli-reference/) · [Compatibility](https://juanfontes.github.io/curlimp/docs/compatibility/)                                                                                 |
| Project purpose and native architecture          | [Why Curlimp](https://juanfontes.github.io/curlimp/docs/why/) · [Architecture](https://juanfontes.github.io/curlimp/docs/architecture/)                                                                                               |

<a id="current-compatibility"></a>

## 🧭 Compatibility and validation

Curlimp supports a **documented subset of curl-style options**. One profile and one request configuration apply to all URLs in an invocation. `--next`, URL globbing, `.curlrc`/`--config`, multipart forms, retries, and progress meters are not implemented. Unsupported options fail explicitly; inspect `curlimp --help` and the [compatibility guide](https://juanfontes.github.io/curlimp/docs/compatibility/) before adapting scripts.

This is an HTTP client: it does not open a browser, render pages, execute JavaScript, or solve browser challenges. Browser fingerprint equivalence and HTTP/3 browser fidelity have not been verified against real browser captures.

Release CI tests Linux amd64, Linux arm64, and macOS Apple Silicon bundles, including functional HTTP/TLS/HTTP2 behavior, profiles, completion, and exports. Linux also checks the minimal filesystem and final container. These checks validate supported behavior; they do not establish fingerprint equivalence. Use `curlimp --version` to inspect your CLI version, native engine, and default profile. [Release changes →](CHANGELOG.md)

<a id="development-and-validation"></a>

## 🤝 Build and contribute

Bug reports, documentation improvements, and reproducible compatibility cases are welcome. [Open an issue](https://github.com/JuanFontes/curlimp/issues) with your platform, Curlimp version, a minimal command, and the expected and actual behavior. Remove credentials and private response data before sharing logs.

For suspected vulnerabilities, use the private reporting channel in [SECURITY.md](SECURITY.md). It also describes dependency monitoring, review checks, and their coverage limits.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development, focused tests, engine maintenance, and release validation. The [source build guide](https://juanfontes.github.io/curlimp/docs/building/) explains how to build the Rust CLI and native engine. The root Dockerfile uses a published runtime; maintainers compile from source with `docker/Dockerfile.build`.

<a id="licenses"></a>

## 📄 License

Original code is MIT licensed under [LICENSE](LICENSE). [NOTICE](NOTICE) identifies incorporated components, and [vendor/engine/LICENSE](vendor/engine/LICENSE) retains the engine's original license. Published images and native bundles include dependency notices. Curlimp is an independent project built around a modified libcurl engine.
