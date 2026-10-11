# 🦎 Curlimp

> **Publication draft:** Curlimp 0.3.0 is currently a local development preview. The new image and addresses below are not published yet. Build this checkout with `docker build -f docker/Dockerfile.build --target runtime -t curlimp:local .` and use `curlimp:local` to test locally.

**Browser impersonation from your terminal. Ready to run with Docker.**

![Release 0.3.0](https://img.shields.io/badge/Release-0.3.0-0F766E?style=flat-square)
![Rust CLI](https://img.shields.io/badge/Rust-CLI-E57324?style=flat-square&logo=rust&logoColor=white)
![libcurl engine](https://img.shields.io/badge/libcurl-Engine-073551?style=flat-square&logo=curl&logoColor=white)
![Linux amd64 and arm64](https://img.shields.io/badge/Linux-amd64_%7C_arm64-334155?style=flat-square&logo=linux&logoColor=white)

Send HTTP requests with browser-specific TLS and HTTP settings using familiar curl-style options. **Chrome 150 impersonation and response decompression are enabled by default.** Select Firefox, Safari, Edge, mobile browser profiles, and more with `--impersonate`.

The Rust CLI calls the bundled libcurl-impersonate engine directly. The image includes its runtime libraries and CA certificates. You only need Docker with Linux container support.

[Website & documentation](https://juanfontes.github.io/curlimp/) · [Source & full guide](https://github.com/JuanFontes/curlimp) · [Native downloads](https://github.com/JuanFontes/curlimp/releases/tag/v0.3.0) · [Changelog](https://github.com/JuanFontes/curlimp/blob/main/CHANGELOG.md) · [Report an issue](https://github.com/JuanFontes/curlimp/issues)

## 🚀 Your first request

```sh
docker run --rm juanfontes/curlimp:latest \
  -sS -I https://httpbin.org/status/200
```

Docker downloads the image automatically if needed and selects the matching CPU architecture. The image starts `curlimp`: put its flags directly after the image name.

Choose another browser by putting its exact profile name before the URL:

```sh
docker run --rm juanfontes/curlimp:latest firefox147 \
  -sS -I https://httpbin.org/status/200

docker run --rm juanfontes/curlimp:latest safari2601 \
  --json-output -sS -i https://httpbin.org/status/418
```

Flags may appear before or after the profile. `--impersonate PROFILE` still works; the last profile selection wins. Use a complete profile ID, not a prefix. Zsh profile autocomplete is available for native `curlimp` installations through `--completions zsh`; running Docker does not configure your host shell or aliases. [Autocomplete guide](https://juanfontes.github.io/curlimp/docs/completion/).

- **`latest`** is used in the examples and follows the newest validated stable release. Release candidates never replace it.
- **`0.3.0`** is the versioned tag for this release; versioned tags remain unchanged.
- Both tags support **`linux/amd64` and `linux/arm64`**.

This is an HTTP client, so it does not open a browser, render pages, or execute JavaScript. Version 0.3.0 supports **one URL per invocation and a documented subset of curl flags**.

## ⌨️ A shorter command: `curli`

In Bash or Zsh, define an alias and pass options and a URL after it:

```sh
alias curli='docker run --rm -i juanfontes/curlimp:latest'

curli -sS -I https://httpbin.org/status/200
curli --impersonate firefox147 -sS -I https://httpbin.org/status/200
```

Add the alias line to `~/.zshrc` for Zsh or `~/.bashrc` for Bash to keep it across terminal sessions. Bash login shells must source `~/.bashrc` from `~/.bash_profile`. Use the full Docker command in scripts. Docker's `-i` forwards stdin; host files passed with CLI options require an explicit volume mount, while shell redirection and pipes work normally.

## 🔄 Updates and fixed versions

Docker uses an image already stored locally unless you ask it to pull. The `latest` tag does not automatically refresh on every run. Update the image used by the alias with:

```sh
docker pull juanfontes/curlimp:latest
```

To check the registry on every invocation, add `--pull=always` before the image name. Each invocation then needs registry access:

```sh
docker run --rm --pull=always juanfontes/curlimp:latest \
  -sS -I https://httpbin.org/status/200
```

For scripts or CI, pin the release so that upgrades are deliberate:

```sh
docker run --rm juanfontes/curlimp:0.3.0 \
  -sS -o /dev/null -w '%{http_code}\n' https://httpbin.org/status/200
```

Use a digest when immutable selection is required. During the local migration, the root Dockerfile uses `curlimp:local`; it will be pinned to the published multiarch digest at release time. Review the [release notes](https://github.com/JuanFontes/curlimp/releases) before upgrading; default profiles and supported options may change.

## 💾 Export TXT or JSON responses

Introduced in **0.2.0**: `--txt` saves a response to an automatic `.txt` file, `--json-file` saves a structured `.json` file, and `--json-output` prints that JSON object to stdout. These are project extensions; `--json DATA` still sends JSON in a request.

```sh
# JSON in the terminal: headers and complete body.
docker run --rm juanfontes/curlimp:latest \
  --json-output --impersonate firefox147 -sS -i https://httpbin.org/status/418

# TXT on the host: mount the current directory and use your Unix UID/GID.
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" \
  juanfontes/curlimp:latest \
  --txt -sS -i https://httpbin.org/status/418

# JSON file on the host: HEAD response headers only.
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" \
  juanfontes/curlimp:latest \
  --json-file -sS -I https://httpbin.org/status/200
```

| Response options | TXT | JSON |
| --- | --- | --- |
| Default | Body bytes | `body` and `body_encoding` |
| `-i` | Headers + body | Headers and body in separate fields |
| `-I` | Headers only | Header fields; body omitted |

JSON also includes `schema_version`, HTTP `status`, and transfer `exit_code`. The complete HTML stays in one body string, including scripts. Non-UTF-8 bytes use explicit Base64; headers retain duplicate names and line order. `-v` remains on stderr. Exported content is not redacted.

Files look like `2026-10-11_14-32-08_httpbin-org-status-418.json`: process-local timestamp (usually UTC in Docker), sanitized original host/path, no URL credentials/query/fragment. Collisions get a numeric suffix. Files are owner-only on Unix. Without a volume mount, files disappear with `--rm`; file modes keep stdout empty. `-sS` suppresses the saved-path message, while still showing errors.

Choose one export mode. Exports reject `-o`, `-D`, and `-w`; JSON also rejects `-N` and buffers at most **64 MiB** of selected content. Larger JSON responses fail with exit 23 without silently truncating; TXT streams without this limit. Transfers keep their usual exit codes, including 22 with fail options. Failed transfers or output writes may leave partial content.

See the **[full export guide](https://juanfontes.github.io/curlimp/docs/response-exports/)** for the JSON schema, encoding, redirects, native commands, and error examples.

## 🎭 Choose your browser

```sh
# Chrome 150 is the default: no profile flag needed.
docker run --rm juanfontes/curlimp:latest \
  -sS -I https://httpbin.org/status/200

# Firefox desktop.
docker run --rm juanfontes/curlimp:latest \
  --impersonate firefox147 -sS -I https://httpbin.org/status/200

# Safari desktop.
docker run --rm juanfontes/curlimp:latest \
  --impersonate safari2601 -sS -I https://httpbin.org/status/200

# Chrome on Android.
docker run --rm juanfontes/curlimp:latest \
  --impersonate chrome131_android -sS -I https://httpbin.org/status/200

# Safari on iOS.
docker run --rm juanfontes/curlimp:latest \
  --impersonate safari260_ios -sS -I https://httpbin.org/status/200
```

A profile configures TLS ClientHello characteristics, protocol negotiation, HTTP/2 settings and pseudo-header ordering, and default HTTP headers. Its target platform describes the client being impersonated, independently of your host OS.

**Available profiles — 39 presets**

| Browser or client | Target | Profile IDs |
| --- | --- | --- |
| Chrome | 🖥️ Desktop | `chrome99`, `chrome100`, `chrome101`, `chrome104`, `chrome107`, `chrome110`, `chrome116`, `chrome119`, `chrome120`, `chrome123`, `chrome124`, `chrome131`, `chrome133a`, `chrome136`, `chrome142`, `chrome145`, `chrome146`, `chrome150` |
| Chrome | 🤖 Android | `chrome99_android`, `chrome131_android` |
| Edge | 🖥️ Desktop | `edge99`, `edge101` |
| Firefox | 🖥️ Desktop | `firefox133`, `firefox135`, `firefox144`, `firefox147` |
| Safari | 🖥️ Desktop | `safari153`, `safari155`, `safari170`, `safari180`, `safari184`, `safari260`, `safari2601` |
| Safari | 📱 iOS | `safari172_ios`, `safari180_ios`, `safari184_ios`, `safari260_ios` |
| Tor Browser | 🖥️ Desktop | `tor145` |
| OkHttp | 🤖 Android client | `okhttp4_android` |

Profiles are versioned presets, not an automatically refreshed browser list. Selecting a Tor Browser profile does not route requests through Tor. `okhttp4_android` is a client preset whose bundled default headers include a desktop Safari User-Agent; inspect or override those headers before use.

```sh
docker run --rm juanfontes/curlimp:latest --list-profiles
```

The command validates the catalog against the installed engine. See the [catalog](https://github.com/JuanFontes/curlimp/blob/v0.3.0/src/profiles.txt) and [native profile settings](https://github.com/JuanFontes/curlimp/blob/v0.3.0/vendor/curl-impersonate/patches/curl.patch).

### Profile selection and environment variables

Priority: **last `--impersonate` / `--no-impersonate` flag → `CURL_IMPERSONATE` → `chrome150`**. The default is fixed per release and shown by `--version`.

```sh
# Supply an environment default to the container.
docker run --rm -e CURL_IMPERSONATE=firefox147 \
  juanfontes/curlimp:latest -sS -I https://httpbin.org/status/200

# Disable browser profiles, including any environment default.
docker run --rm juanfontes/curlimp:latest \
  --no-impersonate -sS -I https://httpbin.org/status/200
```

`CURL_IMPERSONATE_HEADERS=no` suppresses browser headers for environment/default selection. Explicit `--impersonate chrome150:no` keeps the profile's TLS/HTTP settings while disabling its browser headers; `chrome150:yes` enables them. An explicit profile without a suffix enables headers.

**Response decompression is automatic whenever a profile is active**, including the default and environment-selected profiles. `--no-compressed` returns the encoded response bytes; `--compressed` remains accepted for existing scripts. The last compression flag wins. With `--no-impersonate`, decoding is opt-in via `--compressed`. Disabling browser headers with `:no` or `CURL_IMPERSONATE_HEADERS=no` does not disable decoding.

```sh
# Profile decoding is enabled; this particular response has an empty body.
docker run --rm juanfontes/curlimp:latest -sS -I https://httpbin.org/status/200

# Disable content decoding (this status fixture has no compressed body).
docker run --rm juanfontes/curlimp:latest \
  --no-compressed -sS https://httpbin.org/status/200 > response.body
```

The status URL above demonstrates option syntax; it is not a compressed-payload fixture. HTTP content encoding is decoded without converting the payload to text. Unencoded bodies pass through unchanged. Headers printed with `-i` or `-D` retain their original values, including `Content-Encoding` and `Content-Length`.

## 🧰 Everyday commands

### Print only the status code

```sh
docker run --rm juanfontes/curlimp:latest \
  -sS -o /dev/null -w '%{http_code}\n' https://httpbin.org/status/200
```

Replace the URL with `https://httpbin.org/status/301` or `https://httpbin.org/status/502` to inspect those responses. HTTP errors return a normal transfer status unless you request `--fail` or `--fail-with-body`.

### Headers only

```sh
# Make a HEAD request.
docker run --rm juanfontes/curlimp:latest \
  -sS -I https://httpbin.org/status/200

# Keep GET semantics, print headers, and discard the body.
docker run --rm juanfontes/curlimp:latest \
  -sS -D - -o /dev/null https://httpbin.org/status/200
```

### Body, or headers and body

`/status/418` intentionally returns an HTTP error with a small body. `/status/200` is successful but has an empty body.

```sh
# Body only.
docker run --rm juanfontes/curlimp:latest \
  -sS https://httpbin.org/status/418

# Include response headers before the body.
docker run --rm juanfontes/curlimp:latest \
  -sS -i https://httpbin.org/status/418
```

### Redirects and HTTP errors

```sh
# Follow redirects and show the final status.
docker run --rm juanfontes/curlimp:latest \
  -sS -L -o /dev/null -w '%{http_code}\n' \
  https://httpbin.org/status/301

# Return exit code 22 for this HTTP 502 while retaining its response body.
docker run --rm juanfontes/curlimp:latest \
  -sS --fail-with-body https://httpbin.org/status/502
```

### Authentication, headers, and JSON

These examples demonstrate request syntax. The status fixture does not validate the demo credentials or echo the JSON body.

```sh
# Demonstrate Basic auth syntax; this fixture does not validate credentials.
docker run --rm juanfontes/curlimp:latest \
  -sS -u demo:password https://httpbin.org/status/200

# Add a header and send JSON; --json selects POST.
docker run --rm juanfontes/curlimp:latest \
  -sS -H 'X-Request-Source: terminal' \
  --json '{"hello":"world"}' https://httpbin.org/status/201
```

### Save files and read stdin

```sh
# Mount the current directory so the response survives --rm.
docker run --rm -v "$PWD:/work" juanfontes/curlimp:latest \
  -sS -o /work/response.body https://httpbin.org/status/418

# Keep stdin open with Docker's -i; send the bytes unchanged.
printf '{"hello":"world"}' | docker run --rm -i \
  juanfontes/curlimp:latest -sS \
  -H 'Content-Type: application/json' --data-binary @- https://httpbin.org/status/201
```

### Diagnose a request

```sh
docker run --rm juanfontes/curlimp:latest \
  -v --connect-timeout 10 --max-time 30 https://httpbin.org/status/200

docker run --rm juanfontes/curlimp:latest --help
docker run --rm juanfontes/curlimp:latest --version
```

Verbose output goes to stderr; response bodies go to stdout or `-o`. The runtime image is minimal and has no shell. Use CLI flags directly instead of overriding the entrypoint with `sh`.


### More everyday recipes

With the `curli` alias above:

```sh
# Success, no-content, not-found, rate-limit, and unavailable responses.
curli -sS -o /dev/null -w '%{http_code}\n' https://httpbin.org/status/201
curli -sS -o /dev/null -w '%{http_code}\n' https://httpbin.org/status/204
curli -sS -o /dev/null -w '%{http_code}\n' https://httpbin.org/status/404
curli -sS -o /dev/null -w '%{http_code}\n' https://httpbin.org/status/429
curli -sS -o /dev/null -w '%{http_code}\n' https://httpbin.org/status/503

# Follow redirects, print the header chain, and discard the body.
curli -sS -L --max-redirs 5 -D - -o /dev/null https://httpbin.org/status/302

# Distinguish HTTP status from the transfer exit status.
curli -sS -o /dev/null -w 'http=%{http_code} exit=%{exitcode}\n' https://httpbin.org/status/404

# Send JSON with an explicit method (the fixture does not echo it).
curli -sS -i -X PUT --json '{"enabled":true}' https://httpbin.org/status/200

# Send form fields or a cookie.
curli -sS -i -d 'name=demo' -d 'mode=test' https://httpbin.org/status/201
curli -sS -I -b 'theme=dark' https://httpbin.org/status/200

# Inspect the negotiated protocol and total duration.
curli -sS -o /dev/null -w 'http=%{http_version} seconds=%{time_total}\n' https://httpbin.org/status/200
```

Status endpoints select the response code; they do not echo request data, validate the sample credentials or emulate a login flow. `/status/200` has an empty body, while `/status/418` deliberately returns an error with a small body. HTTP errors only cause a failed transfer result when a fail flag is enabled.

Read the [body/header guide](https://juanfontes.github.io/curlimp/docs/body-and-headers/), [redirect/error guide](https://juanfontes.github.io/curlimp/docs/redirects-and-status/), and [file/pipeline guide](https://juanfontes.github.io/curlimp/docs/files/) for the reasoning behind each flag. Consult the [CLI reference](https://juanfontes.github.io/curlimp/docs/cli-reference/) before migrating scripts.

## 💻 Prefer a native download?

| Platform | CPU | Native package |
| --- | --- | --- |
| Linux | amd64 | ✅ Available |
| Linux | arm64 | ✅ Available |
| macOS Apple Silicon | arm64 | ✅ Experimental |
| macOS Intel | amd64 | Not available |
| Windows | amd64 / arm64 | Not available |

[Download version 0.3.0 and SHA256SUMS](https://github.com/JuanFontes/curlimp/releases/tag/v0.3.0). Keep the entire extracted folder together. Linux includes its loader and runtime libraries; macOS includes its engine in `lib/`. macOS downloads are signed ad hoc and are not notarized. Windows and Intel Mac users can run the Linux image with a suitable Docker installation.

## 🧭 Scope and validation

The published platforms have native CI coverage for packaged HTTP/TLS/HTTP2 transfers, profile selection, output handling, and certificate overrides. Linux also tests the assembled minimal filesystem. These are functional checks; **successful requests and echoed headers do not prove fingerprint equivalence to a real browser**.

Current limits include one HTTP(S) URL per process, a subset of curl flags, no `.curlrc`/`--config`, `--next`, multipart, retries, parallel transfers, or progress meter. HTTP/3 is exposed by the engine but has not been validated end to end. See the [full compatibility contract](https://juanfontes.github.io/curlimp/docs/compatibility/).

**Upgrading from RC1/RC2:** impersonation now defaults to Chrome 150. Add `--no-impersonate` to retain the earlier unprofiled behavior. RC3 already uses this default. Since 0.1.1, active profiles also decode compressed responses automatically; use `--no-compressed` if you need the earlier encoded output. Existing `--compressed` commands remain valid.

## 🛠️ Source, maintenance, and license

[Build and contribute](https://github.com/JuanFontes/curlimp/blob/main/CONTRIBUTING.md) · [Release changes](https://github.com/JuanFontes/curlimp/blob/main/CHANGELOG.md) · [Issues](https://github.com/JuanFontes/curlimp/issues)

Original code is MIT licensed. Incorporated components retain their licenses and notices, included in the image under `/usr/share/licenses/curlimp/`. See [LICENSE](https://github.com/JuanFontes/curlimp/blob/main/LICENSE) and [NOTICE](https://github.com/JuanFontes/curlimp/blob/main/NOTICE). This is an independent project, not an official curl release.
