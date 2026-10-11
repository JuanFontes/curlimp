<div align="center">

<h1>🦎 Curlimp</h1>

<p><strong>Browser profiles. curl-style commands. Docker, Linux, and Apple Silicon downloads.</strong></p>

<p>Explore HTTP responses with browser-specific TLS and HTTP settings,<br>right from your terminal and scripts.</p>

<p>
  <a href="Cargo.toml"><img src="https://img.shields.io/badge/Rust-CLI-E57324?style=for-the-badge&amp;logo=rust&amp;logoColor=white" alt="Rust CLI"></a>
  <a href="native/bridge.c"><img src="https://img.shields.io/badge/C-Native_bridge-526D82?style=for-the-badge&amp;logo=c&amp;logoColor=white" alt="C native bridge"></a>
  <a href="vendor/engine/"><img src="https://img.shields.io/badge/libcurl-Native_engine-073551?style=for-the-badge&amp;logo=curl&amp;logoColor=white" alt="libcurl native engine"></a>
  <a href="https://hub.docker.com/r/juanfontes/curlimp"><img src="https://img.shields.io/badge/Docker-Ready_to_run-2496ED?style=for-the-badge&amp;logo=docker&amp;logoColor=white" alt="Ready-to-run Docker image"></a>
</p>

<p>
  <a href="https://hub.docker.com/r/juanfontes/curlimp/tags?name=0.3.0"><img src="https://img.shields.io/badge/Release-0.3.0-0F766E?style=flat-square" alt="Release 0.3.0"></a>
  <img src="https://img.shields.io/badge/Profiles-39-0F766E?style=flat-square" alt="39 browser and client profiles">
  <img src="https://img.shields.io/badge/Linux-amd64_%7C_arm64-334155?style=flat-square&amp;logo=linux&amp;logoColor=white" alt="Linux amd64 and arm64">
  <a href="#platform-support"><img src="https://img.shields.io/badge/macOS-Apple_Silicon-334155?style=flat-square&amp;logo=apple&amp;logoColor=white" alt="macOS Apple Silicon"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-0F766E?style=flat-square" alt="MIT license"></a>
</p>

<p>
  <a href="https://juanfontes.github.io/curlimp/">🌐 Website & docs</a> ·
  <a href="https://hub.docker.com/r/juanfontes/curlimp">🐳 Docker Hub</a> ·
  <a href="https://github.com/JuanFontes/curlimp/releases">📦 Downloads</a> ·
  <a href="#use-the-published-docker-image">🚀 Quick start</a> ·
  <a href="CONTRIBUTING.md">🛠️ Contributing</a>
</p>

</div>

---

**curlimp brings browser impersonation to your terminal.** It applies browser-specific TLS and HTTP settings through a patched libcurl engine, with a Rust CLI and familiar curl-style options. The goal is to make those profiles easy to use through ready-to-run images, native downloads, and practical documentation.

<a id="use-the-published-docker-image"></a>

> **Local development preview:** Curlimp 0.3.0 is in development. The release, documentation site and Docker Hub image are not published yet. To test this checkout now, build and run the local image:

```sh
docker build -f docker/Dockerfile.build --target runtime -t curlimp:local .
docker run --rm curlimp:local firefox147 -sS -I https://httpbin.org/status/200
```

The published-image and download examples below describe the upcoming release.

## 🚀 Quick start

With Docker installed, make your first request:

```sh
docker run --rm juanfontes/curlimp:latest \
  -sS -I https://httpbin.org/status/200
```

This sends a HEAD request and prints the response headers. Docker downloads the image if needed and selects Linux amd64 or arm64 automatically. No source build is required.

**Chrome 150 is the default profile.** Compressed responses are decoded automatically while a profile is active. Put an exact profile name before the URL, or use `--impersonate <profile>`, to choose another browser. `--no-impersonate` disables profiles; `--no-compressed` retains encoded response bytes.

```sh
docker run --rm juanfontes/curlimp:latest firefox147 \
  -sS -I https://httpbin.org/status/200

# With a native installation:
curlimp firefox147 --json-output -sS -i https://httpbin.org/status/418
```

### Tab-complete browser profiles in Zsh

With the native `curlimp` executable on your `PATH`, add this to `~/.zshrc` after your existing completion setup:

```zsh
# Run these two lines only if your shell setup does not already initialize completion.
autoload -Uz compinit
compinit

source <(curlimp --completions zsh)

# Optional: choose a profile in a menu; Enter accepts it without running the command.
zstyle ':completion:*:curlimp:*' menu yes select
```

Type `curlimp ` and press Tab for all profiles. Type any prefix before Tab: `chrome1`, `chrome15`, `firefox14`, and `safari26` narrow the matches using the full text you typed. One match completes the name; several matches offer a choice. Use the complete profile name when executing a command. Chrome remains the default when no profile is selected.

This first version completes **profile names only, in Zsh**, including after `--impersonate`. Bash, Fish, other flags and file completion are not included yet. Docker commands and aliases need integration in the host shell; running the image alone does not install autocomplete. [Completion setup and matching rules →](https://juanfontes.github.io/curlimp/docs/completion/)

### Make it shorter: `curli`

In Bash or Zsh:

```sh
alias curli='docker run --rm -i juanfontes/curlimp:latest'

curli -sS -I https://httpbin.org/status/200
```

Add the alias to `~/.zshrc` or `~/.bashrc` to keep it across sessions. Docker's `-i` forwards stdin. For scripts, use the full Docker command or a native executable. See the [Docker guide](https://juanfontes.github.io/curlimp/docs/docker/) for shell setup and mounting host files.

`latest` follows stable releases, but Docker reuses a locally cached image. Run `docker pull juanfontes/curlimp:latest` to update it. For scripts and CI, pin a version such as `0.3.0`, or a digest. [Updates and fixed versions →](https://juanfontes.github.io/curlimp/docs/docker/#updates-and-fixed-versions)

<a id="http-examples"></a>

## 🧰 Everyday examples

Using the `curli` alias above:

```sh
# Only the response body (this endpoint deliberately returns HTTP 418).
curli -sS https://httpbin.org/status/418

# Response headers followed by the body.
curli -sS -i https://httpbin.org/status/418

# Only the HTTP status code.
curli -sS -o /dev/null -w '%{http_code}\n' https://httpbin.org/status/200

# Follow redirects and print the final status.
curli -sS -L -o /dev/null -w '%{http_code}\n' https://httpbin.org/status/301

# Return exit code 22 on this HTTP error, keeping any response body.
curli -sS --fail-with-body https://httpbin.org/status/502
```

The examples use `-sS` to keep error messages visible. HTTP errors only cause a nonzero exit code when a fail option is enabled. `/status/200` has an empty body; `/status/418` includes a small body. These endpoints demonstrate HTTP behavior, not browser fingerprint fidelity.

**More examples:** [headers and bodies](https://juanfontes.github.io/curlimp/docs/body-and-headers/) · [redirects and errors](https://juanfontes.github.io/curlimp/docs/redirects-and-status/) · [files and pipelines](https://juanfontes.github.io/curlimp/docs/files/).

## 💾 Export a response

Use `--txt` for an automatically named TXT file, `--json-file` for a JSON file, or `--json-output` for JSON in the terminal. These project extensions preserve complete response content, including HTML.

```sh
# Print a JSON object with response headers and body.
docker run --rm juanfontes/curlimp:latest \
  --json-output -sS -i https://httpbin.org/status/418

# Save a TXT file in the current host directory.
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" \
  juanfontes/curlimp:latest \
  --txt -sS -i https://httpbin.org/status/418

# Save a JSON file containing HEAD response headers only.
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" \
  juanfontes/curlimp:latest \
  --json-file -sS -I https://httpbin.org/status/200
```

Without `-i` or `-I`, exports contain the body only. `-i` adds headers; `-I` selects headers only. Files use timestamp/URL names and never overwrite existing files. Docker file exports need a mounted directory, as above.

`--json DATA` still sends request JSON. Choose one export mode; combining exports with `-o`, `-D`, or `-w` is an error. JSON modes buffer at most **64 MiB**, retain binary data as explicit Base64, and reject `-N`; TXT streams raw bytes. **[Export formats, examples, and error behavior →](https://juanfontes.github.io/curlimp/docs/response-exports/)**

<a id="browser-profiles"></a>

## 🎭 Choose a browser

Release `0.3.0` includes **39 browser and client profiles**, covering Chrome, Firefox, Safari, Edge, Tor Browser, and OkHttp.

```sh
# Firefox desktop.
curli --impersonate firefox147 -sS -I https://httpbin.org/status/200

# Safari on iOS.
curli --impersonate safari260_ios -sS -I https://httpbin.org/status/200

# List the profiles supported by your installed engine.
curli --list-profiles
```

The profile's target platform is independent of your host OS. Profiles are versioned presets; selecting a Tor Browser profile does not route traffic through Tor.

**[Browse the full profile catalog →](https://juanfontes.github.io/curlimp/docs/profiles/)** Includes profile IDs, header controls, selection rules, and preset-specific caveats.

<a id="platform-support"></a>
<a id="linux-downloads"></a>
<a id="macos-downloads"></a>

## 💻 Platforms & downloads

| Platform | Native bundle | Status |
| --- | :---: | --- |
| Linux x86-64 / amd64 | ✅ | Tested on Ubuntu 24.04 |
| Linux ARM64 / aarch64 | ✅ | Tested on Ubuntu 24.04 ARM |
| macOS Apple Silicon (M1 and newer) | ✅ | Experimental; macOS 15 CI |
| macOS Intel | ⬜ | No native package yet |
| Windows | ⬜ | No native package yet |

**[Download native bundles](https://github.com/JuanFontes/curlimp/releases/latest)** or **[follow the installation guide](https://juanfontes.github.io/curlimp/docs/installation/)** for checksums, extraction, and PATH setup. Keep the complete extracted bundle together. The macOS package is signed ad hoc and is **not notarized**.

The [Docker image](https://hub.docker.com/r/juanfontes/curlimp) supports Linux amd64 and arm64. macOS and Windows users can run it with Docker configured for Linux containers.

<a id="current-compatibility"></a>

## 🧭 Scope & limitations

- Supports **one HTTP(S) URL per invocation** and a documented subset of curl flags. Multiple URLs, `--next`, `.curlrc`, multipart forms, retries, and parallel transfers are not implemented.
- An HTTP client: it does not open a browser, render pages, or execute JavaScript.
- Browser fingerprint equivalence has not yet been verified against real browser captures. HTTP/3 is exposed by the engine but has not been validated end to end.
- `--no-impersonate` disables browser presets while keeping the same modified engine; it does not switch to your system curl.

See the **[compatibility guide](https://juanfontes.github.io/curlimp/docs/compatibility/)** when using Curlimp in scripts. Run `curli --help` for supported flags and `curli --version` for the installed release and default profile.

## 📚 Go deeper

| Looking for… | Read |
| --- | --- |
| JSON, forms, and custom headers | [Requests](https://juanfontes.github.io/curlimp/docs/requests/) |
| Basic authentication and cookie jars | [Authentication & cookies](https://juanfontes.github.io/curlimp/docs/authentication-and-cookies/) |
| Proxies, certificates, timeouts, and diagnostics | [Networking](https://juanfontes.github.io/curlimp/docs/networking/) |
| Every supported flag and write-out variable | [CLI reference](https://juanfontes.github.io/curlimp/docs/cli-reference/) |
| Why this project exists and how it works | [Purpose](https://juanfontes.github.io/curlimp/docs/why/) · [Architecture](https://juanfontes.github.io/curlimp/docs/architecture/) |

<a id="development-and-validation"></a>

## 🛠️ Build & contribute

Start with [building from source](https://juanfontes.github.io/curlimp/docs/building/) and [CONTRIBUTING.md](CONTRIBUTING.md) for development, tests, engine updates, and releases. Read the [changelog](CHANGELOG.md) for release changes, or [open an issue](https://github.com/JuanFontes/curlimp/issues) with a reproducible example.

<a id="licenses"></a>

## 📄 License

Original code is MIT licensed under [LICENSE](LICENSE). [NOTICE](NOTICE) describes incorporated components; the engine's original license remains in [vendor/engine/LICENSE](vendor/engine/LICENSE). Published images and native bundles retain dependency license notices. Curlimp is an independent project built around a modified libcurl engine.
