---
layout: ../../layouts/Doc.astro
title: 'Why this project exists'
description: 'The purpose of curlimp: practical browser profiles, familiar command-line workflows, source-built releases and explicit compatibility limits.'
slug: why
lead: 'Make browser-profile HTTP requests easier to run, understand and maintain.'
---

## The problem we wanted to solve

A useful browser-impersonation client needs more than a collection of profile names. It needs an understandable command line, binaries people can download, consistent behavior across distribution formats, and documentation that tells users exactly what is supported.

This project brings those pieces together: a Rust command-line layer, an existing native impersonation engine built from source, and ready-to-run Docker and native packages.

## Familiar commands, deliberate defaults

Browser impersonation is the normal path. Running a request selects the release's default Chrome profile. The `--impersonate` option chooses another browser or client; it is not required to turn impersonation on.

```sh
# Default Chrome profile
curli -sS -I https://httpbin.org/status/200

# Select Safari
curli --impersonate safari2601 -sS -I https://httpbin.org/status/200
```

The default also enables response decompression. Explicit options remain available when a script needs different behavior.

## Why keep libcurl?

The native engine already implements HTTP transport, TLS integration, redirects, proxies and browser-profile settings. Replacing it with a new networking stack would introduce another large compatibility and maintenance task.

Rust owns the interface around that engine: parsing arguments, preparing inputs, routing outputs and packaging a focused CLI. The C bridge keeps the native boundary small. This is not a rewrite of libcurl in Rust, and the native engine was not created from scratch here.

## What we prioritize

- **Usable releases:** Docker for Linux amd64/arm64 and native Linux and Apple Silicon bundles.
- **Clear behavior:** supported flags are documented, unknown options fail explicitly, and response bytes are preserved.
- **Maintainable sources:** local engine build inputs, pinned source checksums, dependency notices and build provenance.
- **Honest validation:** distinguish a passing HTTP test from a comparison with a real browser's network traffic.

## What comes next

Broader curl compatibility, additional platforms and repeatable browser fingerprint comparisons are possible directions. They are not features of the current release or commitments to a delivery date.

Read the [architecture](../architecture/) for the implementation, or [current limits](../compatibility/) to decide whether it fits your workload.
