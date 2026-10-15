# 🦎 Curlimp

**Browser impersonation from your terminal. Ready to run with Docker.**

![Release 0.5.1](https://img.shields.io/badge/Release-0.5.1-0F766E?style=flat-square)
![Rust CLI](https://img.shields.io/badge/Rust-CLI-E57324?style=flat-square&logo=rust&logoColor=white)
![libcurl engine](https://img.shields.io/badge/libcurl-Engine-073551?style=flat-square&logo=curl&logoColor=white)
![Linux amd64 and arm64](https://img.shields.io/badge/Linux-amd64_%7C_arm64-334155?style=flat-square&logo=linux&logoColor=white)

Send HTTP requests with browser-specific TLS and HTTP settings using familiar curl-style options. **Chrome 150 impersonation and response decompression are enabled by default.** Select Firefox, Safari, Edge, mobile browser profiles, and more with `--impersonate`.

The Rust CLI calls the bundled libcurl-impersonate engine directly. The image includes its runtime libraries and CA certificates. You only need Docker with Linux container support.

**New in 0.5.1:** an official ngtcp2 security fix, a native regression check with AddressSanitizer, and evidence-backed dependency advisory reporting. Multiple URLs, bounded parallel transfers, response exports, and the 38 browser profiles remain available; Chrome 150 is still the default.

[Website & documentation](https://juanfontes.github.io/curlimp/) · [Source & full guide](https://github.com/JuanFontes/curlimp) · [Native downloads](https://github.com/JuanFontes/curlimp/releases/tag/v0.5.1) · [Changelog](https://github.com/JuanFontes/curlimp/blob/main/CHANGELOG.md) · [Report an issue](https://github.com/JuanFontes/curlimp/issues)

## 🚀 Your first request

```sh
docker run --rm juanfontes/curlimp \
  -sS -I https://httpbin.org/status/200
```

Docker downloads the image automatically if needed and selects the matching CPU architecture. The image starts `curlimp`: put its flags directly after the image name.

Choose another browser by putting its exact profile name before the URL:

```sh
docker run --rm juanfontes/curlimp firefox147 \
  -sS -I https://httpbin.org/status/200

docker run --rm juanfontes/curlimp safari2601 \
  --json-output -sS -i https://httpbin.org/status/418
```

Flags may appear before or after the profile. `--impersonate PROFILE` still works; the last profile selection wins. Use a complete profile ID, not a prefix.

- **`juanfontes/curlimp`** is all you need for everyday use. With no tag, Docker defaults to **`latest`**, which follows the newest validated stable release. Release candidates never replace it.
- **`0.5.1`** is the versioned tag for this release; versioned tags remain unchanged.
- Both tags support **`linux/amd64` and `linux/arm64`**.

This is an HTTP client, so it does not open a browser, render pages, or execute JavaScript. Version 0.5.1 supports **multiple URLs with one common request configuration and a documented subset of curl flags**.

## ⌨️ Native `curlimp` and Zsh autocomplete

Prefer a command without Docker? [Install the native bundle](https://juanfontes.github.io/curlimp/docs/installation/) and put `curlimp` on your `PATH`:

```sh
curlimp firefox147 -sS -I https://httpbin.org/status/200
```

For profile autocomplete, add this to `~/.zshrc`:

```zsh
# Skip these first two lines if your shell already initializes completion.
autoload -Uz compinit
compinit

source <(curlimp --completions zsh)
zstyle ':completion:*:curlimp:*' menu yes select
```

Open a new terminal, type `curlimp ` and press Tab to list profiles. Any prefix filters the list; Enter accepts the selected name so you can finish the request. This setup requires the native executable on your host. [Autocomplete guide](https://juanfontes.github.io/curlimp/docs/completion/).

## 🔄 Updates and fixed versions

Omitting the tag does not automatically refresh an image already stored locally. Docker reuses its cached image unless you ask it to pull. Update your local image with:

```sh
docker pull juanfontes/curlimp
```

To check the registry on every invocation, add `--pull=always` before the image name. Each invocation then needs registry access:

```sh
docker run --rm --pull=always juanfontes/curlimp \
  -sS -I https://httpbin.org/status/200
```

For scripts or CI, pin the release so that upgrades are deliberate:

```sh
docker run --rm juanfontes/curlimp:0.5.1 \
  -sS -o /dev/null -w '%{http_code}\n' https://httpbin.org/status/200
```

Use a digest when immutable selection is required. The root Dockerfile defaults to the versioned `juanfontes/curlimp:0.5.1` runtime tag, which release policy keeps unchanged. Override `RUNTIME_IMAGE` with a digest or, for local development, `--build-arg RUNTIME_IMAGE=curlimp:local`. Review the [release notes](https://github.com/JuanFontes/curlimp/releases) before upgrading; default profiles and supported options may change.

## 💾 Export TXT or JSON responses

`--txt` saves each response to an automatic `.txt` file, `--json-file` saves each to a structured `.json` file, and `--json-output` prints one object for one URL or an input-ordered array for several URLs to stdout. These are project extensions; `--json DATA` still sends JSON in a request.

```sh
# JSON in the terminal: headers and complete body.
docker run --rm juanfontes/curlimp \
  --json-output --impersonate firefox147 -sS -i https://httpbin.org/status/418

# TXT on the host: mount the current directory and use your Unix UID/GID.
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" \
  juanfontes/curlimp \
  --txt -sS -i https://httpbin.org/status/418

# JSON file on the host: HEAD response headers only.
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" \
  juanfontes/curlimp \
  --json-file -sS -I https://httpbin.org/status/200
```

| Response options | TXT            | JSON                                |
| ---------------- | -------------- | ----------------------------------- |
| Default          | Body bytes     | `body` and `body_encoding`          |
| `-i`             | Headers + body | Headers and body in separate fields |
| `-I`             | Headers only   | Header fields; body omitted         |

JSON also includes `schema_version`, HTTP `status`, and transfer `exit_code`. The complete HTML stays in one body string, including scripts. Non-UTF-8 bytes use explicit Base64; headers retain duplicate names and line order. `-v` remains on stderr. Exported content is not redacted.

Files look like `2026-10-11_14-32-08_httpbin-org-status-418.json`: process-local timestamp (usually UTC in Docker), sanitized original host/path, no URL credentials/query/fragment. Collisions get a numeric suffix. Files are owner-only on Unix. Without a volume mount, files disappear with `--rm`; file exports do not print response bytes to stdout. An explicitly requested `-c -` cookie jar can still write there for TXT and JSON-file exports; `--json-output` rejects that combination to keep stdout as one JSON document. `-sS` suppresses the saved-path message, while still showing errors.

Choose one export mode. Exports reject `-o`, `-D`, and `-w`; JSON also rejects `-N` and accepts at most **64 MiB per response** of selected content. JSON payloads use private temporary files, requiring writable temporary storage; data is read in bounded chunks. Larger JSON responses or storage failures return 23 without silently truncating and suppress a multi-response aggregate; TXT streams without this limit. Transfers keep their usual exit codes, including 22 with fail options. Failed transfers or output writes may leave partial content.

See the **[full export guide](https://juanfontes.github.io/curlimp/docs/response-exports/)** for the JSON schema, encoding, redirects, native commands, and error examples.

## 🔀 Multiple URLs and parallel requests

Requests run sequentially by default. The first `-o` belongs to the first URL, the second to the second URL; missing destinations use stdout. Use `-o -` to skip saving a response. Line breaks are optional.

```sh
# Save the first response to a file on the host; print the second.
docker run --rm -v "$PWD:/work" juanfontes/curlimp -sS -i \
  https://httpbin.org/status/200 https://httpbin.org/status/502 \
  -o /work/response-200.txt

# Save all sequential output to one file with host redirection.
docker run --rm juanfontes/curlimp -sS -i \
  https://httpbin.org/status/200 https://httpbin.org/status/502 > responses.txt

# Print an ordered JSON array with up to two active transfers.
docker run --rm juanfontes/curlimp \
  --parallel --parallel-max 2 --json-output -sS -i \
  https://httpbin.org/status/200 https://httpbin.org/status/418 \
  https://httpbin.org/status/502
```

`-Z` is short for `--parallel`; its default maximum is 50. `--parallel-max` alone does not enable parallelism. Ordinary parallel stdout and shared header output can interleave. Use distinct files or JSON exports to keep responses separate. `--txt` and `--json-file` create one file per URL. Multi-URL JSON includes a zero-based `transfer_index` and a normalized `url` with credentials and fragment removed; query strings remain.

All URLs share request options, the selected profile, and cookies. Sequential exit status follows the last transfer; parallel execution retains the first observed failure. JSON records each transfer's own result. Add a fail flag to treat HTTP errors as failures. Export storage failures return 23. See the **[multiple-URL guide](https://juanfontes.github.io/curlimp/docs/multiple-urls/)** for output pairing, cookies, limits, and error handling.

## 🎭 Choose your browser

```sh
# Chrome 150 is the default: no profile flag needed.
docker run --rm juanfontes/curlimp \
  -sS -I https://httpbin.org/status/200

# Firefox desktop.
docker run --rm juanfontes/curlimp \
  --impersonate firefox147 -sS -I https://httpbin.org/status/200

# Safari desktop.
docker run --rm juanfontes/curlimp \
  --impersonate safari2601 -sS -I https://httpbin.org/status/200

# Chrome on Android.
docker run --rm juanfontes/curlimp \
  --impersonate chrome131_android -sS -I https://httpbin.org/status/200

# Safari on iOS.
docker run --rm juanfontes/curlimp \
  --impersonate safari260_ios -sS -I https://httpbin.org/status/200
```

A profile configures TLS ClientHello characteristics, protocol negotiation, HTTP/2 settings and pseudo-header ordering, and default HTTP headers. Its target platform describes the client being impersonated, independently of your host OS.

**Available profiles — 38 presets**

| Browser     | Target     | Profile IDs                                                                                                                                                                                                                              |
| ----------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Chrome      | 🖥️ Desktop | `chrome99`, `chrome100`, `chrome101`, `chrome104`, `chrome107`, `chrome110`, `chrome116`, `chrome119`, `chrome120`, `chrome123`, `chrome124`, `chrome131`, `chrome133a`, `chrome136`, `chrome142`, `chrome145`, `chrome146`, `chrome150` |
| Chrome      | 🤖 Android | `chrome99_android`, `chrome131_android`                                                                                                                                                                                                  |
| Edge        | 🖥️ Desktop | `edge99`, `edge101`                                                                                                                                                                                                                      |
| Firefox     | 🖥️ Desktop | `firefox133`, `firefox135`, `firefox144`, `firefox147`                                                                                                                                                                                   |
| Safari      | 🖥️ Desktop | `safari153`, `safari155`, `safari170`, `safari180`, `safari184`, `safari260`, `safari2601`                                                                                                                                               |
| Safari      | 📱 iOS     | `safari172_ios`, `safari180_ios`, `safari184_ios`, `safari260_ios`                                                                                                                                                                       |
| Tor Browser | 🖥️ Desktop | `tor145`                                                                                                                                                                                                                                 |

Profiles are versioned presets, not an automatically refreshed browser list. Selecting a Tor Browser profile does not route requests through Tor. Version 0.4.0 removed `okhttp4_android` and its native `okhttp4` alias; requests selecting either name now fail before output files are opened.

```sh
docker run --rm juanfontes/curlimp --list-profiles
```

The command validates the catalog against the installed engine. See the [catalog](https://github.com/JuanFontes/curlimp/blob/v0.5.1/src/profiles.txt) and [native profile settings](https://github.com/JuanFontes/curlimp/blob/v0.5.1/vendor/engine/patches/curl.patch).

### Profile selection and environment variables

Priority: **last positional profile / `--impersonate` / `--no-impersonate` selection → `CURL_IMPERSONATE` → `chrome150`**. The default is fixed per release and shown by `--version`.

```sh
# Supply an environment default to the container.
docker run --rm -e CURL_IMPERSONATE=firefox147 \
  juanfontes/curlimp -sS -I https://httpbin.org/status/200

# Disable browser profiles, including any environment default.
docker run --rm juanfontes/curlimp \
  --no-impersonate -sS -I https://httpbin.org/status/200
```

`CURL_IMPERSONATE_HEADERS=no` suppresses browser headers for environment/default selection. Explicit `--impersonate chrome150:no` keeps the profile's TLS/HTTP settings while disabling its browser headers; `chrome150:yes` enables them. An explicit profile without a suffix enables headers.

**Response decompression is automatic whenever a profile is active**, including the default and environment-selected profiles. `--no-compressed` returns the encoded response bytes; `--compressed` remains accepted for existing scripts. The last compression flag wins. With `--no-impersonate`, decoding is opt-in via `--compressed`. Disabling browser headers with `:no` or `CURL_IMPERSONATE_HEADERS=no` does not disable decoding.

```sh
# Profile decoding is enabled; this particular response has an empty body.
docker run --rm juanfontes/curlimp -sS -I https://httpbin.org/status/200

# Disable content decoding (this status fixture has no compressed body).
docker run --rm juanfontes/curlimp \
  --no-compressed -sS https://httpbin.org/status/200 > response.body
```

The status URL above demonstrates option syntax; it is not a compressed-payload fixture. HTTP content encoding is decoded without converting the payload to text. Unencoded bodies pass through unchanged. Headers printed with `-i` or `-D` retain their original values, including `Content-Encoding` and `Content-Length`.

## 🧰 Everyday commands

### Print only the status code

```sh
docker run --rm juanfontes/curlimp \
  -sS -o /dev/null -w '%{http_code}\n' https://httpbin.org/status/200
```

Replace the URL with `https://httpbin.org/status/301` or `https://httpbin.org/status/502` to inspect those responses. HTTP errors return a normal transfer status unless you request `--fail` or `--fail-with-body`.

### Headers only

```sh
# Make a HEAD request.
docker run --rm juanfontes/curlimp \
  -sS -I https://httpbin.org/status/200

# Keep GET semantics, print headers, and discard the body.
docker run --rm juanfontes/curlimp \
  -sS -D - -o /dev/null https://httpbin.org/status/200
```

### Body, or headers and body

`/status/418` intentionally returns an HTTP error with a small body. `/status/200` is successful but has an empty body.

```sh
# Body only.
docker run --rm juanfontes/curlimp \
  -sS https://httpbin.org/status/418

# Include response headers before the body.
docker run --rm juanfontes/curlimp \
  -sS -i https://httpbin.org/status/418
```

### Redirects and HTTP errors

```sh
# Follow redirects and show the final status.
docker run --rm juanfontes/curlimp \
  -sS -L -o /dev/null -w '%{http_code}\n' \
  https://httpbin.org/status/301

# Return exit code 22 for this HTTP 502 while retaining its response body.
docker run --rm juanfontes/curlimp \
  -sS --fail-with-body https://httpbin.org/status/502
```

### Authentication, headers, and JSON

These examples demonstrate request syntax. The status fixture does not validate the demo credentials or echo the JSON body.

```sh
# Demonstrate Basic auth syntax; this fixture does not validate credentials.
docker run --rm juanfontes/curlimp \
  -sS -u demo:password https://httpbin.org/status/200

# Add a header and send JSON; --json selects POST.
docker run --rm juanfontes/curlimp \
  -sS -H 'X-Request-Source: terminal' \
  --json '{"hello":"world"}' https://httpbin.org/status/201
```

### Save files and read stdin

```sh
# Mount the current directory so the response survives --rm.
docker run --rm -v "$PWD:/work" juanfontes/curlimp \
  -sS -o /work/response.body https://httpbin.org/status/418

# Keep stdin open with Docker's -i; send the bytes unchanged.
printf '{"hello":"world"}' | docker run --rm -i \
  juanfontes/curlimp -sS \
  -H 'Content-Type: application/json' --data-binary @- https://httpbin.org/status/201
```

### Diagnose a request

```sh
docker run --rm juanfontes/curlimp \
  -v --connect-timeout 10 --max-time 30 https://httpbin.org/status/200

docker run --rm juanfontes/curlimp --help
docker run --rm juanfontes/curlimp --version
```

Verbose output goes to stderr; response bodies go to stdout or `-o`. The runtime image is minimal and has no shell. Use CLI flags directly instead of overriding the entrypoint with `sh`.

### More everyday recipes

Pass the request options directly after the image name:

```sh
# Success, no-content, not-found, rate-limit, and unavailable responses.
docker run --rm juanfontes/curlimp \
  -sS -o /dev/null -w '%{http_code}\n' https://httpbin.org/status/201
docker run --rm juanfontes/curlimp \
  -sS -o /dev/null -w '%{http_code}\n' https://httpbin.org/status/204
docker run --rm juanfontes/curlimp \
  -sS -o /dev/null -w '%{http_code}\n' https://httpbin.org/status/404
docker run --rm juanfontes/curlimp \
  -sS -o /dev/null -w '%{http_code}\n' https://httpbin.org/status/429
docker run --rm juanfontes/curlimp \
  -sS -o /dev/null -w '%{http_code}\n' https://httpbin.org/status/503

# Follow redirects, print the header chain, and discard the body.
docker run --rm juanfontes/curlimp \
  -sS -L --max-redirs 5 -D - -o /dev/null https://httpbin.org/status/302

# Distinguish HTTP status from the transfer exit status.
docker run --rm juanfontes/curlimp \
  -sS -o /dev/null -w 'http=%{http_code} exit=%{exitcode}\n' https://httpbin.org/status/404

# Send JSON with an explicit method (the fixture does not echo it).
docker run --rm juanfontes/curlimp \
  -sS -i -X PUT --json '{"enabled":true}' https://httpbin.org/status/200

# Send form fields or a cookie.
docker run --rm juanfontes/curlimp \
  -sS -i -d 'name=demo' -d 'mode=test' https://httpbin.org/status/201
docker run --rm juanfontes/curlimp \
  -sS -I -b 'theme=dark' https://httpbin.org/status/200

# Inspect the negotiated protocol and total duration.
docker run --rm juanfontes/curlimp \
  -sS -o /dev/null -w 'http=%{http_version} seconds=%{time_total}\n' https://httpbin.org/status/200
```

Status endpoints select the response code; they do not echo request data, validate the sample credentials or emulate a login flow. `/status/200` has an empty body, while `/status/418` deliberately returns an error with a small body. HTTP errors only cause a failed transfer result when a fail flag is enabled.

Read the [body/header guide](https://juanfontes.github.io/curlimp/docs/body-and-headers/), [redirect/error guide](https://juanfontes.github.io/curlimp/docs/redirects-and-status/), and [file/pipeline guide](https://juanfontes.github.io/curlimp/docs/files/) for the reasoning behind each flag. Consult the [CLI reference](https://juanfontes.github.io/curlimp/docs/cli-reference/) when using Curlimp in scripts.

## 💻 Prefer a native download?

| Platform            | CPU           | Native package  |
| ------------------- | ------------- | --------------- |
| Linux               | amd64         | ✅ Available    |
| Linux               | arm64         | ✅ Available    |
| macOS Apple Silicon | arm64         | ✅ Experimental |
| macOS Intel         | amd64         | Not available   |
| Windows             | amd64 / arm64 | Not available   |

[Download version 0.5.1 and SHA256SUMS](https://github.com/JuanFontes/curlimp/releases/tag/v0.5.1). Keep the entire extracted folder together. Linux includes its loader and runtime libraries; macOS includes its engine in `lib/`. macOS downloads are signed ad hoc and are not notarized. Windows and Intel Mac users can run the Linux image with a suitable Docker installation.

## 🧭 Scope and validation

The release checks require packaged HTTP/TLS/HTTP2 transfers, profile selection, output handling, and certificate overrides on each published platform. Linux also tests the assembled minimal filesystem and a final container DNS/HTTPS request with a mounted nonroot JSON export. These are functional checks; **successful requests and echoed headers do not prove fingerprint equivalence to a real browser**.

Current limits include a subset of curl flags, one common request configuration per invocation, and no `.curlrc`/`--config`, `--next`, URL globbing, multipart, retries, or progress meter. HTTP/3 is exposed by the engine but has not been validated end to end. See the [full compatibility contract](https://juanfontes.github.io/curlimp/docs/compatibility/).

## 🛠️ Source, maintenance, and license

[Build and contribute](https://github.com/JuanFontes/curlimp/blob/main/CONTRIBUTING.md) · [Release changes](https://github.com/JuanFontes/curlimp/blob/main/CHANGELOG.md) · [Issues](https://github.com/JuanFontes/curlimp/issues)

Original code is MIT licensed. Incorporated components retain their licenses and notices, included in the image under `/usr/share/licenses/curlimp/`. See [LICENSE](https://github.com/JuanFontes/curlimp/blob/main/LICENSE) and [NOTICE](https://github.com/JuanFontes/curlimp/blob/main/NOTICE). This is an independent project, not an official curl release.
