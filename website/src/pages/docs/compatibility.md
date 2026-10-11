---
layout: ../../layouts/Doc.astro
title: 'Compatibility and known limits'
description: "Understand curlimp's curl option subset, single-URL scope, supported operating systems and unverified browser fingerprint and HTTP/3 fidelity."
slug: compatibility
section: Under the hood
lead: 'Know what is implemented, what is tested and what still needs evidence.'
---

## A curl-style interface, with a defined scope

The CLI accepts a documented subset of familiar curl flags. It is not a complete drop-in replacement for every curl script. Unknown flags and write-out variables fail explicitly.

| Supported                                              | Not implemented                                  |
| ------------------------------------------------------ | ------------------------------------------------ |
| One HTTP(S) URL per invocation                         | Multiple URLs, `--next`, URL globbing            |
| Methods, headers, JSON, form and binary request bodies | Multipart forms, streaming uploads               |
| Redirects, timeouts, explicit proxy and CA options     | Automatic retry and parallel transfers           |
| Basic authentication, cookies and cookie jars          | Interactive password prompts and `.netrc`        |
| Body/header output and listed write-out variables      | Every curl output variable, `-O`, progress meter |
| CLI flags and documented environment defaults          | `.curlrc` and `--config` files                   |

Use separate invocations when processing multiple URLs. Do not append two URLs to a single command.

## Defaults differ from ordinary curl

The release selects Chrome 150 by default and automatically decodes compressed responses while a profile is active. `--impersonate` selects a browser; `--no-impersonate` disables profiles. Without a profile, decoding is opt-in with `--compressed`.

`--no-impersonate` still uses the project's modified engine. It does not promise the same TLS fingerprint as your system curl.

## Platform support

Docker images support Linux amd64 and arm64. Native bundles are tested on Ubuntu 24.04 for both architectures. Native macOS Apple Silicon support is experimental, tested in macOS 15 CI; binaries are signed ad hoc and not notarized.

There are no native Windows or Intel Mac packages. The minimum macOS deployment target and the availability of a Linux loader are not proof of compatibility with every older OS or distribution.

## What is tested

- Argument parsing and explicit unsupported-option errors.
- The catalog against the compiled engine and profile/default precedence.
- Local HTTP, TLS and HTTP2 transfers, redirects and output behavior.
- Compression defaults and overrides, request headers and binary response preservation.
- CA overrides and execution of extracted native bundles.
- Linux runtime filesystem packaging and bounded public HTTPS checks.

## What is not yet verified

The project does not currently establish equivalent fingerprints against real browser captures. HTTP/3 selectors exist, but HTTP/3 browser fidelity is unverified. A successful request or a matching User-Agent is not sufficient evidence for either claim.

No claim of undetectability, bot-protection bypass, universal site compatibility or improved performance is made.

## It is not a browser runtime

The client does not render pages, execute JavaScript, manage DOM state or local storage, complete interactive login flows, or solve browser challenges. A browser profile changes network settings; it does not add those capabilities.

## Packaging boundaries

Native downloads contain multiple files and must stay together. Request bodies are buffered; ordinary response output and TXT exports stream. [JSON exports](../response-exports/) buffer up to 64 MiB and have explicit output-option conflicts. Release checksum files detect corruption but are not signed. Dependency source hashes are recorded, but the full build environment is not locked for byte-identical builds.

For a reproducible bug report, include a sanitized command, release version, OS/architecture, profile, expected result and actual stderr/exit code. See [networking and diagnostics](../networking/).
