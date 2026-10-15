# 🦎 Curlimp

Browser profiles and curl-style requests from a Rust CLI backed by a modified libcurl engine. Run it with Docker or download a native bundle for Linux amd64, Linux arm64, or experimental macOS Apple Silicon.

[Website and documentation](https://juanfontes.github.io/curlimp/) · [Docker Hub](https://hub.docker.com/r/juanfontes/curlimp) · [Native downloads](https://github.com/JuanFontes/curlimp/releases/tag/v0.5.0) · [Changelog](CHANGELOG.md)

## Quick start

```sh
docker run --rm juanfontes/curlimp -sS -I https://httpbin.org/status/200
```

This makes a HEAD request and prints the headers. Docker selects Linux amd64 or arm64. Chrome 150 is the default profile; select another of the 38 supported browser profiles by exact name:

```sh
docker run --rm juanfontes/curlimp firefox147 \
  -sS -I https://httpbin.org/status/200

docker run --rm juanfontes/curlimp \
  --json-output -sS -i https://httpbin.org/status/418
```

`/status/200` has an empty body; `/status/418` has a small body. These examples show request and output behavior, not equivalence to a real browser capture. The image name without a tag uses Docker `latest`, which follows the newest promoted stable release. Pull it to refresh a cached copy: `docker pull juanfontes/curlimp`. Pin `juanfontes/curlimp:0.5.0` or a digest for a fixed deployment. See the [Docker guide](https://juanfontes.github.io/curlimp/docs/docker/) for mounts, updates, and platform details.

## Native use

Download the matching archive and `SHA256SUMS` from the [0.5.0 release](https://github.com/JuanFontes/curlimp/releases/tag/v0.5.0). Verify the checksum and keep the extracted directory together. The [installation guide](https://juanfontes.github.io/curlimp/docs/installation/) has exact commands. There are no native Windows or Intel Mac packages. The macOS bundle is signed ad hoc, not notarized; CI targets macOS 15, while its compiled minimum is macOS 13.0.

With `curlimp` on your `PATH`:

```sh
curlimp firefox147 -sS -I https://httpbin.org/status/200
curlimp -sS -o /dev/null -w '%{http_code}\n' https://httpbin.org/status/200
curlimp --list-profiles
```

`--txt` and `--json-file` save automatically named response files; `--json-output` writes one JSON object for one URL, or an ordered array for multiple URLs. For example, mount the current directory when exporting from Docker:

```sh
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" \
  juanfontes/curlimp --txt -sS -i https://httpbin.org/status/418
```

See [profiles](https://juanfontes.github.io/curlimp/docs/profiles/), [requests](https://juanfontes.github.io/curlimp/docs/requests/), [exports](https://juanfontes.github.io/curlimp/docs/response-exports/), [Zsh completion](https://juanfontes.github.io/curlimp/docs/completion/), and the [CLI reference](https://juanfontes.github.io/curlimp/docs/cli-reference/).

## Multiple URLs

```sh
# Two concurrent requests; print one ordered JSON array in the terminal.
docker run --rm juanfontes/curlimp --parallel --parallel-max 2 \
  --json-output -sS -i https://httpbin.org/status/200 https://httpbin.org/status/502

# Native CLI: first URL goes to test1.txt, second goes to test2.txt.
curlimp -sS -i https://httpbin.org/status/200 https://httpbin.org/status/502 \
  -o test1.txt -o test2.txt
```

Without `--parallel`, requests run in URL order. `-o` is optional: the first destination belongs to the first URL, wherever the options appear. Use `-o -` for stdout. Raw parallel stdout can interleave; use separate files or JSON exports to keep responses distinct. See [multiple URLs and parallel transfers](https://juanfontes.github.io/curlimp/docs/multiple-urls/) for combined files, Docker mounts, limits, and error handling.

<a id="platform-support"></a>

## Platforms

| Platform | Native bundle |
| --- | --- |
| Linux amd64 and arm64 | Ubuntu 24.04 CI targets |
| macOS Apple Silicon | Experimental; macOS 15 CI target |
| Windows and Intel Mac | No native package |

<a id="current-compatibility"></a>

## Scope

Curlimp supports multiple HTTP(S) URLs, sequential or parallel transfers, and a documented subset of curl flags. One profile and one set of request options apply to the invocation; `--next` and URL globbing are not implemented. It does not render pages or execute JavaScript. Browser fingerprint equivalence and HTTP/3 browser fidelity have not been verified against real browser captures. Read the [compatibility guide](https://juanfontes.github.io/curlimp/docs/compatibility/) for limits and the [changelog](CHANGELOG.md) for changes.

For development, see [CONTRIBUTING.md](CONTRIBUTING.md) and the [source build guide](https://juanfontes.github.io/curlimp/docs/building/). Original code is MIT licensed under [LICENSE](LICENSE). [NOTICE](NOTICE) identifies incorporated components; [vendor/engine/LICENSE](vendor/engine/LICENSE) retains the engine's original license. Published images and bundles include dependency notices.
