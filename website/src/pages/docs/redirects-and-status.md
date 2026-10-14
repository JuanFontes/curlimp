---
layout: ../../layouts/Doc.astro
title: 'Redirects, status codes and errors'
description: 'Follow HTTP redirects, print only the response code, distinguish HTTP errors from transfer failures, and use curl-style write-out variables in scripts.'
slug: redirects-and-status
section: Usage
lead: 'Inspect redirects and HTTP errors without confusing response status with process exit status.'
---

## Automatic Referer on redirects

Append `;auto` to `-e` / `--referer` to use the previous URL as the Referer when following a redirect:

```sh
curlimp -sS -L --referer ';auto' https://httpbin.org/status/301
curlimp -sS -L --referer 'https://httpbin.org/status/200;auto' \
  https://httpbin.org/status/301
```

The first form sends no initial Referer. The second starts with the supplied URL. After a redirect, libcurl generates the Referer from the previous URL, excluding its credentials and fragment. Without `-L`, no redirects are followed. If the option is repeated, the last value wins; a value without `;auto` disables automatic updates. The status endpoint must provide a `Location` header for a redirect to occur.

## Print only the HTTP status

Discard the body with `-o /dev/null`, then print the response code with `-w`:

```sh
curlimp -sS -o /dev/null -w '%{http_code}\n' https://httpbin.org/status/200
curlimp -sS -o /dev/null -w '%{http_code}\n' https://httpbin.org/status/404
curlimp -sS -o /dev/null -w '%{http_code}\n' https://httpbin.org/status/502
```

These deliberately request `200`, `404` and `502`. The final newline keeps your next shell prompt on its own line.

## Inspect a redirect without following it

Following redirects is opt-in. Inspect the redirect response and its `Location` header:

```sh
curlimp -sS -D - -o /dev/null https://httpbin.org/status/301
```

A 3xx code alone is not enough to follow a redirect; the response needs a usable redirect location.

## Follow redirects

Add `-L` and report the final status:

```sh
curlimp -sS -L -o /dev/null -w '%{http_code}\n' \
  https://httpbin.org/status/301
```

See the entire header chain, or bound how many redirects are allowed:

```sh
curlimp -sS -L -D - -o /dev/null https://httpbin.org/status/302

curlimp -sS -L --max-redirs 3 -o /dev/null \
  -w 'status=%{http_code} redirects=%{num_redirects}\n' \
  https://httpbin.org/status/301
```

The default limit is 50 when following redirects. `--max-redirs -1` removes the limit; a finite limit and `--max-time` are usually more useful in scripts.

## HTTP status is not the exit code

A completed transfer that receives an HTTP `404` is not the same as a failed DNS lookup or TLS handshake. By default, HTTP errors do not cause a nonzero exit code.

```sh
curlimp -sS -o /dev/null \
  -w 'http=%{http_code} exit=%{exitcode}\n' \
  https://httpbin.org/status/404
```

For a successfully received response, this reports `http=404 exit=0`. If no HTTP response was received, the HTTP code can be `000`; that is a diagnostic placeholder, not a server response code.

## Fail a script on HTTP errors

`-f` returns exit code `22` for HTTP status 400 or above and suppresses the body:

```sh
curlimp -sS -f -o /dev/null https://httpbin.org/status/502
printf 'exit=%s\n' "$?"
```

Use `--fail-with-body` to keep a useful error payload while still returning exit `22`:

```sh
curlimp -sS --fail-with-body https://httpbin.org/status/418
```

Both options intentionally make these examples fail. In a shell script, handle that branch explicitly:

```sh
if curlimp -sS -f -o /dev/null https://httpbin.org/status/503; then
  printf 'Request succeeded\n'
else
  result=$?
  printf 'Request failed: exit %s\n' "$result" >&2
fi
```

In saved scripts, call the native `curlimp` command or use the full Docker command.

## Add useful transfer metadata

```sh
curlimp -sS -L -o /dev/null \
  -w 'status=%{http_code}\nurl=%{url_effective}\nredirects=%{num_redirects}\nhttp=%{http_version}\nseconds=%{time_total}\n' \
  https://httpbin.org/status/301
```

`-w` writes to stdout after the transfer. Redirect the body to a file or `/dev/null` when you need clean, machine-readable metadata. Supported variables are listed in the [CLI reference](../cli-reference/).
