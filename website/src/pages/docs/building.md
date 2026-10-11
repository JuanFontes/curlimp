---
layout: ../../layouts/Doc.astro
title: 'Building from source'
description: 'Build the Curlimp Rust CLI and bundled native engine, derive a Docker image from the ready-made runtime, and find contributor build instructions.'
slug: building
section: Under the hood
lead: 'Pick the build path that matches what you are changing.'
---

## Build a derived distribution image

After building the local runtime below:

```sh
docker build --build-arg RUNTIME_IMAGE=curlimp:local -t curlimp:distribution-local .
docker run --rm curlimp:distribution-local --version
```

The root Dockerfile starts from the runtime selected by `RUNTIME_IMAGE`. For local development it defaults to `curlimp:local`; the release will pin a published image digest. It does not compile your local CLI changes.

## Compile the engine and CLI

Use the separate maintainer Dockerfile. This example targets Linux arm64; choose `linux/amd64` for x86-64:

```sh
docker build -f docker/Dockerfile.build --platform linux/arm64 \
  --target runtime -t curlimp:local .

docker run --rm curlimp:local --version
docker run --rm curlimp:local firefox147 -sS -I https://httpbin.org/status/200
```

The first build needs network access for source archives, packages and compiler images. Subsequent builds can reuse unchanged native layers. It verifies the vendored inputs, builds dependencies and the engine, and compiles the Rust CLI against that engine.

## Validate runtime changes

For changes that affect the CLI, engine or runtime filesystem:

```sh
docker build -f docker/Dockerfile.build --platform linux/arm64 \
  --target test-minimal -t curlimp:test .
```

This validates the assembled runtime in addition to the supported integration behavior. Documentation-only edits do not need a native rebuild.

## Native macOS build

On Apple Silicon, the build helper needs Apple's command-line tools, Rust, CMake, Ninja, Go, Perl, patch and make:

```sh
workspace="$TMPDIR/curlimp-macos-build"
sh scripts/build-macos.sh "$workspace" 4
```

Use a fresh absolute workspace. The helper builds native dependencies and the CLI; packaging and release tests are separate steps. Consult [CONTRIBUTING.md](https://github.com/JuanFontes/curlimp/blob/main/CONTRIBUTING.md#build-on-macos-apple-silicon) for exact prerequisites, packaging commands and validation scope.

## Update an engine or profile

A new profile requires native settings and a compatible engine build. Review the source changes and notices, update the existing checksum manifest and lock, then update the profile catalog as needed. Test every published platform. A real-browser capture comparison is required before asserting improved fingerprint fidelity.

See the [contributor guide](https://github.com/JuanFontes/curlimp/blob/main/CONTRIBUTING.md) for artifact exports, source provenance, dependency updates and release publication.
