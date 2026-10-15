---
layout: ../../layouts/Doc.astro
title: 'Files, stdin and pipelines'
description: 'Save response bodies, upload JSON or binary data, pipe stdin through Docker, and separate curlimp response output from diagnostic stderr.'
slug: files
section: Usage
lead: 'Keep paths, streams and bytes predictable in both Docker and native scripts.'
---

## Save a response with shell redirection

The host shell creates the destination file:

```sh
curlimp -sS https://httpbin.org/status/418 > response.body
```

Redirection also works with a full Docker command because the host shell handles it outside the container. Unlike the CLI's deferred `-o` handling, the shell can create or truncate the file before a request starts.

## Save with the output option

`-o` is interpreted by the CLI. In Docker, that path is inside the container:

```sh
docker run --rm -v "$PWD:/work" juanfontes/curlimp \
  -sS -o /work/response.body https://httpbin.org/status/418
```

`--rm` removes the container after it exits. A file written to an unmounted container path disappears with it. `-O` / remote-name output is not implemented.

## Pipe JSON into a request

The native CLI reads stdin with `@-`:

```sh
printf '{"message":"hello"}' | curlimp -sS -i --json @- \
  https://httpbin.org/status/201
```

The JSON is sent as the request body; the status fixture does not echo it. With Docker, add `-i` **before the image name** to forward stdin:

```sh
printf '{"message":"hello"}' | docker run --rm -i \
  juanfontes/curlimp -sS -i --json @- https://httpbin.org/status/201
```

The CLI's `-i` after the image name means “include response headers.” Avoid Docker's `-t` in pipelines.

## Send an existing file

Create a small payload, then mount the current directory read-only:

```sh
printf '{"message":"hello"}\n' > payload.json

docker run --rm -v "$PWD:/work:ro" juanfontes/curlimp \
  -sS -i --json @/work/payload.json https://httpbin.org/status/201
```

For exact bytes, use `--data-binary`:

```sh
printf 'first line\nsecond line\n' | curlimp -sS -i \
  -H 'Content-Type: application/octet-stream' --data-binary @- \
  https://httpbin.org/status/200
```

Avoid `-d @file` when line endings or NUL bytes matter. Request bodies are fully buffered, so this is not a streaming upload interface.

If a command has multiple `@-` readers, Curlimp consumes them in their argument order. This includes an earlier `-w @-` later replaced by another `-w`: the earlier reader still consumes its stdin content before a later body or header reader.

## Automatic TXT and JSON exports

Use `--txt` or `--json-file` for automatically named files, or `--json-output` for a structured result on stdout. Docker file modes still require a volume mount. File exports themselves do not print the response on stdout; an explicitly requested `-c -` cookie jar may write there for TXT and JSON-file exports. See [response exports](../response-exports/) for examples, field selection with `-i`/`-I`, binary encoding and limits.

## Keep response and diagnostics separate

The response body goes to stdout by default. Errors and verbose diagnostics go to stderr:

```sh
curlimp -sS -v https://httpbin.org/status/200 \
  > response.body 2> request.log
```

Verbose logs can contain request headers and credentials. Review them before sharing.

## Use Curlimp in scripts

Call the native command directly, or pin the Docker image version:

```sh
curlimp -sS -o /dev/null -w '%{http_code}\n' https://httpbin.org/status/200

docker run --rm juanfontes/curlimp:0.4.0 \
  -sS -o /dev/null -w '%{http_code}\n' https://httpbin.org/status/200
```
