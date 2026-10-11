---
layout: ../../layouts/Doc.astro
title: 'Request methods, headers and JSON'
description: 'Send POST JSON, form data, GET query parameters and custom HTTP headers using the supported curlimp command-line options.'
slug: requests
section: Usage
lead: "Control what you send while keeping a browser profile's transport settings."
---

## Send JSON

`--json` supplies a request body and adds `Content-Type: application/json` and `Accept: application/json` unless you override them. A body selects POST by default.

```sh
curli -sS -i --json '{"message":"hello","enabled":true}' \
  https://httpbin.org/status/201
```

The status endpoint returns the requested code; it does not echo or validate your payload. `--json` does not parse your JSON for correctness either.

## Send form data

Repeat `-d` to combine form fields with `&`:

```sh
curli -sS -i -d 'name=demo' -d 'mode=test' \
  https://httpbin.org/status/200
```

This is not multipart upload. Values requiring URL encoding must be encoded before you pass them; `--data-urlencode` is not implemented.

## Use another HTTP method

`-X` overrides the method string. It does not automatically change the body or response-handling options.

```sh
curli -sS -i -X PUT --json '{"enabled":true}' https://httpbin.org/status/200
curli -sS -i -X PATCH --json '{"name":"updated"}' https://httpbin.org/status/200
curli -sS -i -X DELETE https://httpbin.org/status/204
```

For a bodyless HEAD request, use `-I` instead of `-X HEAD`. When following redirects, a forced method can behave differently from a method inferred from the body; only force it when needed.

## Add query parameters to GET

`-G` moves the supplied data into the query string:

```sh
curli -sS -D - -o /dev/null -G -d 'mode=test' -d 'page=2' \
  https://httpbin.org/status/200
```

The status fixture ignores those parameters. Quote complete URLs when they contain shell-special characters such as `&`; automatic URL globbing is not supported.

## Add or override request headers

Repeat `-H` for multiple headers:

```sh
curli -sS -I \
  -H 'Accept: application/json' \
  -H 'X-Request-ID: local-demo' \
  https://httpbin.org/status/200
```

A custom header can change the profile's header fingerprint. A profile is not a promise that arbitrary modifications remain browser-equivalent.

Use `-A` for a User-Agent override or `-e` for a Referer:

```sh
curli -sS -I -A 'my-http-test/1.0' https://httpbin.org/status/200
curli -sS -I -e 'https://httpbin.org/status/200' https://httpbin.org/status/200
```

Setting only a User-Agent does not select a browser's TLS or HTTP profile. Use `--impersonate` for profile selection.

## Choose the right data flag

| Flag            | Input behavior                                                                               |
| --------------- | -------------------------------------------------------------------------------------------- |
| `-d`, `--data`  | Reads `@file` or `@-`; file input strips CR, LF and NUL bytes. Repeated parts join with `&`. |
| `--data-raw`    | Treats a leading `@` literally.                                                              |
| `--data-binary` | Reads files/stdin without stripping bytes.                                                   |
| `--json`        | Adds JSON headers and reads literal data, a file, or stdin.                                  |

Requests are buffered in memory before transfer. See [files and pipelines](../files/) for file paths and stdin examples.
