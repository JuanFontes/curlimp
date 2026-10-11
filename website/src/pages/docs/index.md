---
layout: ../../layouts/Doc.astro
title: 'Browser impersonation, explained'
description: 'Learn what curlimp does, how browser profiles affect TLS and HTTP, and how to use its Rust CLI with the native libcurl engine.'
slug: ''
lead: 'Browser-specific network settings, ready-to-run releases, and a familiar command line. Start here to understand what the tool does.'
---

## What is curlimp?

curlimp is an HTTP client that applies browser and client profiles to a patched libcurl engine. A profile configures aspects of the TLS handshake, HTTP behavior and request headers. You use it from a terminal or a script, without opening a browser.

The Rust CLI handles arguments, inputs and outputs. A small C bridge calls the native engine, which performs the network transfer. The engine is built from source and distributed with the CLI.

## Your first request

Follow the [quick start](./quick-start/) to use Docker or a native download. The guides use a `curli` Docker alias so the examples stay short:

```sh
curli -sS -I https://httpbin.org/status/200
```

Chrome 150 is the default profile. Responses are decompressed automatically while a profile is active. Select another profile with `--impersonate`; disable profiles with `--no-impersonate`.

## Find the guide you need

| I want to…                                 | Read                                                              |
| ------------------------------------------ | ----------------------------------------------------------------- |
| Run the published image or binary          | [Quick start](./quick-start/) and [installation](./installation/) |
| Print a body, headers, or both             | [Body and headers](./body-and-headers/)                           |
| Follow a redirect or check a response code | [Redirects and status codes](./redirects-and-status/)             |
| Send JSON, form data or custom headers     | [Requests and JSON](./requests/)                                  |
| Use authentication or cookies              | [Authentication and cookies](./authentication-and-cookies/)       |
| Save a response or pipe request data       | [Files and pipelines](./files/)                                   |
| Set a timeout, proxy or CA bundle          | [Networking and diagnostics](./networking/)                       |
| Understand the native engine               | [Architecture](./architecture/)                                   |

## Read the boundaries first

This is a **documented subset of curl**, currently accepting one HTTP(S) URL per invocation. It does not render HTML, execute JavaScript, manage a browser session, or solve browser challenges.

Functional HTTP/TLS tests demonstrate supported client behavior. They do **not** establish fingerprint equivalence to a real browser. See [compatibility and limits](./compatibility/) before replacing existing scripts.

## About the examples

Examples target `https://httpbin.org/status/200` and other `/status/…` endpoints. They return a chosen HTTP status; many deliberately have an empty body. They do not echo JSON, validate the sample credentials, or act as a cookie-based application. The guides explain what each command sends or displays without implying otherwise.

Unless stated otherwise, examples use Bash or Zsh. For a native installation on your `PATH`, replace `curli` with `curlimp`.
