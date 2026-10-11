---
layout: ../../layouts/Doc.astro
title: 'Response body and headers'
description: 'curl-style examples for printing only the body, requesting HEAD, inspecting GET headers, including headers, and saving response headers separately.'
slug: body-and-headers
section: Usage
lead: 'Choose exactly what goes to your terminal, a file, or the next command in a pipeline.'
---

## Show only the body

The body is the default output. `-s` enables silent mode, and `-S` keeps error messages visible. This CLI has no progress meter.

```sh
curli -sS https://httpbin.org/status/418
```

The `418` endpoint deliberately returns an HTTP error and a small response body. Without `-f` or `--fail-with-body`, a successfully transferred HTTP error can still have process exit code `0`.

```sh
curli -sS https://httpbin.org/status/200
```

The `200` endpoint has an empty body. No printed text is expected; use `-I` or `-w` to inspect it.

## Request only headers with HEAD

`-I` (uppercase i) sends a **HEAD request** and prints response headers:

```sh
curli -sS -I https://httpbin.org/status/200
```

A server may handle HEAD differently from GET. Avoid `-X HEAD` as a replacement: changing the method string does not enable HEAD's body-handling behavior.

## Inspect headers from a GET request

To keep the GET method, dump headers to stdout with `-D -` and discard the body with `-o /dev/null`:

```sh
curli -sS -D - -o /dev/null https://httpbin.org/status/200
```

This still downloads and discards any body. It is useful when HEAD is unsupported or you need the headers of the actual GET response.

## Print headers and body together

`-i` (lowercase i) includes headers before the body:

```sh
curli -sS -i https://httpbin.org/status/418
```

With redirects, output can contain multiple header blocks. Avoid piping this combined output into a parser that expects only a body.

## Save headers and body separately

For Docker, mount a host directory when using file options:

```sh
docker run --rm -v "$PWD:/work" juanfontes/curlimp:latest \
  -sS -D /work/response.headers -o /work/response.body \
  https://httpbin.org/status/418
```

For a native binary, use local paths directly:

```sh
curlimp -sS -D response.headers -o response.body \
  https://httpbin.org/status/418
```

## Understand decompression

An active profile enables HTTP content decoding automatically. `--no-compressed` retains encoded bytes; `--compressed` explicitly enables decoding. The last of these flags wins.

```sh
# Retain the response bytes without content decoding
curli --no-compressed -sS https://httpbin.org/status/200 > response.body

# Disable profiles, but explicitly enable decoding
curli --no-impersonate --compressed -sS https://httpbin.org/status/200
```

The status endpoint is a command-syntax example, not a compressed-payload fixture. On a response that is compressed, the decoded body and received headers may describe different byte lengths: `Content-Encoding` and `Content-Length` retain their original values.

Decoding never converts a binary payload to text. Save binary responses to a file instead of assuming every body is readable.
