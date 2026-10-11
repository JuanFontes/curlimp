---
layout: ../../layouts/Doc.astro
title: 'Export responses as TXT or JSON'
description: 'Save curlimp responses as automatically named TXT or JSON files, or print structured JSON. Learn header selection, Docker mounts, encodings and limits.'
slug: response-exports
section: Usage
lead: 'Keep a complete response for later, or pass a structured result to another tool.'
---

## Choose an export mode

These are project extensions introduced in **0.2.0**, not standard curl options. Without them, ordinary response output is unchanged.

| Option          | Destination                                               | Contents                                                             |
| --------------- | --------------------------------------------------------- | -------------------------------------------------------------------- |
| `--txt`         | Automatically named `.txt` file in the current directory  | The selected response bytes, including HTML or binary data           |
| `--json-output` | Standard output                                           | One JSON object containing the selected response and transfer result |
| `--json-file`   | Automatically named `.json` file in the current directory | The same JSON object                                                 |

Choose one mode per invocation. File modes do not also print the response body. A saved-path message goes to stderr unless `-s` is active; `-sS` still shows errors but suppresses that saved-path message.

**`--json DATA` keeps its existing meaning:** it sends JSON in the request body. It can be combined with any export mode.

## Select body, headers, or both

| Response options      | TXT file                       | JSON fields                                            |
| --------------------- | ------------------------------ | ------------------------------------------------------ |
| Neither `-i` nor `-I` | Body only                      | `body`, `body_encoding`                                |
| `-i`                  | Headers followed by body       | `headers`, `headers_encoding`, `body`, `body_encoding` |
| `-I`                  | HEAD response headers, no body | `headers`, `headers_encoding`; body fields omitted     |

Every JSON object also includes `schema_version`, `status`, and `exit_code`. A successful GET with an empty response has `"body": ""`; HEAD omits that field. `-v` remains diagnostic output on stderr and is not included in the export. `-L` follows redirects as usual; with `-i` or `-I`, header lines from the received response blocks stay in order.

## Print JSON in the terminal

Run the image directly to print one JSON object with headers and body:

```sh
docker run --rm juanfontes/curlimp:latest \
  --json-output --impersonate firefox147 -sS -i https://httpbin.org/status/418
```

No alias or directory mount is needed for terminal output. With the optional [curli alias](../docker/), these examples show the other response selections:

```sh
# Headers only, as JSON.
curli --json-output -sS -I https://httpbin.org/status/200

# Body only. This fixture deliberately returns an HTTP 418 with a small body.
curli --json-output -sS https://httpbin.org/status/418

# Headers and body, using Firefox.
curli --json-output --impersonate firefox147 -sS -i \
  https://httpbin.org/status/418

# Follow redirects and include the received header blocks.
curli --json-output -sS -L -i https://httpbin.org/status/301
```

These endpoints demonstrate response handling. They do not verify browser fingerprints. `/status/200` has an empty body, so use `/status/418` when you want to see body content.

## Save files from Docker

Mount a writable host directory at `/work`, the image's working directory. On Unix hosts, `--user` creates files using your UID/GID:

```sh
# Save headers and the complete body to an automatic TXT filename.
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" \
  juanfontes/curlimp:latest \
  --txt -sS -i https://httpbin.org/status/418

# Save the same response as a JSON object.
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" \
  juanfontes/curlimp:latest \
  --json-file -sS -i https://httpbin.org/status/418

# Save only headers from a HEAD request.
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" \
  juanfontes/curlimp:latest \
  --json-file -sS -I https://httpbin.org/status/200
```

The basic `curli` alias does not mount your host directory. A file saved inside an unmounted container disappears when `--rm` removes it. For terminal JSON, no mount is needed. You can also use host shell redirection when you want to choose the filename yourself:

```sh
curli --json-output -sS -i https://httpbin.org/status/418 > response.json
```

Shell redirection can overwrite an existing file; automatic export filenames never overwrite one.

## Save files with a native download

Run the [native executable](../installation/) from the directory where you want to keep the files:

```sh
curlimp --txt -sS -i https://httpbin.org/status/418
curlimp --json-file -sS -I https://httpbin.org/status/200
```

A filename looks like this:

```text
2026-10-11_14-32-08_httpbin-org-status-418.txt
2026-10-11_14-32-08_httpbin-org-status-418.json
```

The timestamp uses the process's local timezone at request start, usually UTC inside the minimal Docker image. The rest comes from the original URL's host and path. Scheme, credentials, query, and fragment are omitted; unsafe filename characters are replaced and the URL portion is limited to 96 characters. An invalid URL uses `response` instead of a URL-derived name. On collision, a numeric suffix is added. Existing files and symlinks are not overwritten.

## JSON structure and complete HTML

An illustrative response from a small local HTML fixture:

```json
{
  "schema_version": 1,
  "status": 200,
  "exit_code": 0,
  "headers_encoding": "utf-8",
  "headers": [
    "HTTP/1.1 200 OK\r\n",
    "Content-Type: text/html; charset=utf-8\r\n",
    "\r\n"
  ],
  "body_encoding": "utf-8",
  "body": "<!doctype html>\n<html><body><script>const data={\"message\":\"hello\"};</script></body></html>"
}
```

**The entire HTML document is one string in `body`.** Scripts and embedded data stay inside it; the CLI does not execute JavaScript, extract article text, parse the DOM, or convert a JSON response into nested fields. JSON escaping preserves quotes, backslashes, newlines, and control characters. Parsing the exported object recovers the original UTF-8 response content.

`headers` is an array of received lines, including status lines, blank lines, and line endings. It preserves duplicate header names and the ordering of response blocks instead of collapsing them into a dictionary.

For bytes that are not valid UTF-8, the corresponding encoding is `base64`. Decode `body` when `body_encoding` is `base64`. If the header block is not valid UTF-8, `headers_encoding` is `base64` and each array entry is an individually encoded line. There is no lossy text replacement.

Profile decompression still applies before export. `--no-compressed` retains encoded response bytes, which will generally need Base64 in JSON. Response headers remain as received; `Content-Encoding` and `Content-Length` may therefore describe the encoded body rather than the decoded exported bytes. TXT preserves the selected bytes regardless of its extension.

## Errors and compatibility

Export modes reject these combinations before making a request or opening output files:

- More than one distinct export mode.
- Any export mode with `-o`/`--output`, `-D`/`--dump-header`, or `-w`/`--write-out`.
- Either JSON mode with `-N`/`--no-buffer`, because JSON is serialized after the transfer. TXT supports `-N`.

The ordinary meanings of those curl-style flags are unchanged when export modes are absent. `--json DATA`, `-i`, `-I`, `-L`, `-v`, profile flags, and failure options can be combined with exports.

HTTP status and process exit code are separate. To keep an error body while returning exit code 22:

```sh
curli --json-output -sS --fail-with-body https://httpbin.org/status/502
```

This intentionally exits with 22. The JSON also records `"status": 502` and `"exit_code": 22`. `-f` suppresses the error body; without a fail option, a completed HTTP error response does not itself produce a nonzero exit code.

After a network failure, JSON can contain the received portion of the response and a nonzero `exit_code`; TXT can be partial. If no response is received, JSON reports status `0`. Always check the process result when completeness matters. Invalid options or profile settings fail before a report is produced.

**JSON modes buffer up to 64 MiB of combined selected body and header bytes.** Exceeding that limit aborts with exit code 23 and produces no JSON report; it never silently truncates the payload. Use TXT or ordinary `-o` for larger transfers. TXT streams without this limit. Filesystem or output-stream errors also return 23 and may leave partial output.

Exported response content is not redacted: headers can contain cookies, and bodies can contain private information. Automatically created files are owner-readable/writable on Unix systems. The report does not collect outgoing request headers, credentials, or the command line. Review a file before sharing it.
