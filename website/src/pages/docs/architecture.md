---
layout: ../../layouts/Doc.astro
title: 'How curlimp works'
description: 'Understand the Rust CLI, C bridge and source-built patched libcurl engine, including profile application, response streaming and release packaging.'
slug: architecture
section: Under the hood
lead: 'A focused Rust interface around a native HTTP and browser-profile engine.'
---

## The request path

```text
Command-line arguments and environment
                |
             Rust CLI
                |
           Small C bridge
                |
    Patched libcurl + native dependencies
                |
         TLS / HTTP transfer
                |
       Response bytes and metadata
```

The CLI calls libcurl directly through the bridge. It does not launch a browser, shell out to a downloaded curl executable, or delegate requests to a remote service.

## Rust: the command-line contract

`src/cli.rs` parses supported flags and rejects unsupported input. `src/main.rs` resolves the selected profile and environment defaults. `src/body.rs` prepares request bodies and header files. `src/engine.rs` connects those settings to native calls and controls output; `src/writeout.rs` validates write-out formats.

Request inputs and output formats are validated before output files are opened. Request bodies are buffered. Ordinary response output and TXT exports stream raw bytes. JSON export modes buffer up to 64 MiB, preserve UTF-8 in strings and use explicit Base64 for binary data. `src/export.rs` owns file naming and serialization; see [response exports](../response-exports/).

## C: a narrow native boundary

`native/bridge.c` exposes the subset of native operations the Rust client needs. It owns libcurl handles and header lists, invokes transfers and passes body/header callbacks across the boundary.

The native library remains C code with its own dependencies. Rust on the CLI side does not make the entire networking stack memory-safe.

## libcurl: transport and profiles

The patched engine provides HTTP transport and profile-specific settings. Profiles can affect TLS parameters, HTTP behavior and request headers. The selected profile is applied before explicit CLI settings, so user options can override parts of its behavior.

The compiled definitions live in the native patch set. `src/profiles.txt` is a catalog of supported names, not a standalone definition format. `--list-profiles` validates those names against the installed engine.

## Builds and dependencies

The repository carries the native build inputs and patches under `vendor/engine/`. `engine.lock` and the vendored superbuild record verified source inputs. Builds still download pinned dependency archives and use package/container registries; retaining local build inputs does not eliminate every external build dependency.

The native engine was incorporated from existing open-source work. Its notices and source provenance remain in the repository and runtime bundles. The Rust CLI, bridge and release workflow build on that foundation.

## Distribution

- The maintainer Dockerfile compiles the native engine and Rust CLI, then assembles a minimal runtime with libraries and CA files.
- The root Dockerfile derives from a ready-made runtime selected by `RUNTIME_IMAGE`. It defaults to the published release; local builds can override it with `curlimp:local`.
- Linux downloads include a launcher, dynamic loader, libraries and certificates.
- Apple Silicon downloads include the native executable and its adjacent engine library.

Source checksums and provenance make inputs inspectable. The entire build environment is not locked, so byte-for-byte reproducibility is not guaranteed.

## What validation proves

The project tests parsing, profile application, HTTP/TLS/HTTP2 transfers, output bytes, compression behavior, trust settings and packaged execution. Comparing those requests against real browser captures is a separate validation task.

Read [building from source](../building/) to reproduce a build, and [compatibility and limits](../compatibility/) for what the current tests do not establish.
