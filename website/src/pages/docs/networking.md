---
layout: ../../layouts/Doc.astro
title: 'Timeouts, proxies and diagnostics'
description: 'Set connection and overall timeouts, configure HTTP or SOCKS proxies, inspect TLS errors, select HTTP versions and debug curlimp requests.'
slug: networking
section: Usage
lead: 'Bound your requests and inspect the transport when something does not behave as expected.'
---

## Set connection and total time limits

```sh
curli -sS --connect-timeout 5 --max-time 20 \
  -o /dev/null -w '%{http_code}\n' https://httpbin.org/status/200
```

`--connect-timeout` limits the connection phase. `--max-time` (or `-m`) limits the overall transfer, including redirects. Fractional seconds are accepted. These are limits, not a minimum request duration.

```sh
curli -sS --connect-timeout 2.5 -m 10 https://httpbin.org/status/200
```

Automatic retries are not implemented. A `503` response is returned to your script for it to handle.

## Use an HTTP or SOCKS proxy

These examples assume a proxy that you already run; they do not start one:

```sh
curlimp -sS -x http://127.0.0.1:8080 \
  https://httpbin.org/status/200

curlimp -sS -x socks5h://127.0.0.1:1080 \
  https://httpbin.org/status/200
```

These are **native** commands. In Docker, `127.0.0.1` is the container itself. Use an address reachable from that container; the host route depends on your Docker setup. `socks5h` delegates destination hostname resolution to the proxy.

Use `-U` for proxy credentials and `--noproxy` for an explicit bypass list:

```sh
curlimp -sS -x http://127.0.0.1:8080 -U 'demo:demo-password' \
  --noproxy localhost,127.0.0.1 https://httpbin.org/status/200
```

Standard libcurl proxy environment variables can also affect requests. When diagnosing unexpected proxy behavior, inspect your environment and pass it explicitly into Docker only when needed.

## Trust a custom certificate authority

TLS verification is enabled. Point `--cacert` at an existing PEM CA bundle:

```sh
curlimp -sS --cacert /path/to/ca-bundle.pem \
  https://httpbin.org/status/200
```

The bundle must trust the destination certificate chain. The sample path is intentionally a placeholder, not a file shipped by this project. In Docker, mount your bundle and use its container path.

Trust selection supports `--cacert`, `CURL_CA_BUNDLE`, `SSL_CERT_FILE` and `SSL_CERT_DIR`. The explicit CLI bundle takes precedence over the bundle environment variables. See the [installation guide](../installation/) for platform defaults.

`-k` / `--insecure` disables certificate verification. It is an explicit diagnostic opt-out, not a solution to a missing or incorrect trust bundle.

## Inspect the negotiated HTTP version

```sh
curli -sS --http2 -o /dev/null \
  -w 'status=%{http_code} http=%{http_version}\n' \
  https://httpbin.org/status/200

curli -sS --http1.1 -I https://httpbin.org/status/200
```

Negotiation depends on the server and engine. Selecting a protocol can also change a profile's behavior. The CLI accepts HTTP/3 selectors, but real-browser HTTP/3 fidelity is not verified by the current release tests.

## Collect a useful diagnostic

```sh
curli --version
curli --list-profiles
curli -sS -v --connect-timeout 5 --max-time 20 \
  -o /dev/null https://httpbin.org/status/200
```

Record your version, host platform, chosen profile, minimal command, exit code and relevant stderr. Remove credentials and private data before reporting a problem. `-v` emits native diagnostics; it does not compare your request to a real browser capture.
