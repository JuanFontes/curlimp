# Contributing

For the published image and request examples, start with the [README](README.md#use-the-published-docker-image). Run the commands below from the repository root.

## Documentation website

The static GitHub Pages site lives in `website/`. See [website/README.md](website/README.md) for local development, content structure, SEO and deployment. Run `npm ci`, `npm run build` and `npm run check` from that directory for site changes. Keep public request examples on httpbin status endpoints and preserve accurate notes about empty bodies and intentional errors. Site-only edits do not require rebuilding native engines.

## Propose a change

For a substantial feature, dependency update, or browser-profile change, describe the problem, intended behavior, and validation approach before implementing it. Bug reports should include the image tag or digest, CPU architecture, CLI version, a minimal command, and expected versus actual behavior. Remove credentials, cookies, and private request data from reports and logs.

Keep code, comments, documentation, and commit messages in English. Keep each pull request focused, preserve response bytes and the documented CLI behavior, and report unsupported options explicitly. Preserve third-party license notices and the engine's verified input manifest.

## Build and test locally

Use Docker with Linux container support and BuildKit. Docker supplies the compilers and native dependencies. The initial source build needs network access; this path packages Linux amd64 and arm64 runtimes. For native macOS, use the [Apple Silicon build](#build-on-macos-apple-silicon) below.

The root `Dockerfile` derives an image from a **ready-to-run runtime**, selected with `RUNTIME_IMAGE`. It does not compile code or download source archives. `docker/Dockerfile.build` owns compilation, tests, complete runtime export, and the optional Debian diagnostic image.

Build source changes with the maintainer Dockerfile. These commands target Linux arm64; use `linux/amd64` in both commands for amd64:

```sh
docker build -f docker/Dockerfile.build --platform linux/arm64 \
  --target runtime -t curlimp:runtime .

docker build --platform linux/arm64 \
  --build-arg RUNTIME_IMAGE=curlimp:runtime \
  -t curlimp:local .
docker run --rm curlimp:local --version
```

The runtime is already executable. The second build derives the distribution image; its explicit override makes it use local changes instead of the published release. Use the same Docker daemon builder for both local builds. The initial source build downloads dependencies and compiler images; subsequent builds reuse cached native compilation when available.

```sh
# Compile and run parser, HTTP/TLS/HTTP2, and minimal filesystem tests.
docker build -f docker/Dockerfile.build --platform linux/arm64 \
  --target test-minimal -t curlimp:test-local .

# Optional Debian runtime with a shell for diagnostics.
docker build -f docker/Dockerfile.build --platform linux/arm64 \
  --target runtime-debian -t curlimp:debug .
```

`NATIVE_JOBS` defaults to 4; smaller builders can use `--build-arg NATIVE_JOBS=2`. CLI-only changes reuse native compilation layers when cached. Dockerfile-specific ignore rules include only source-build inputs and exclude generated or local files; distribution builds need no local files. Update `docker/Dockerfile.build.dockerignore` when adding a new build input outside the listed paths. The GitHub Actions workflow is configured to test each architecture, export runtime files into the runner filesystem, and build both runtime and distribution images using the same daemon builder. It also packages Linux downloads, runs the extracted launcher directly on each native runner, and uploads the tested archives as workflow artifacts. It does not publish releases or images automatically.

### Derive your own image from a ready-made runtime

During the local Curlimp migration, the root `Dockerfile` defaults to `curlimp:local`. Build that runtime with the maintainer Dockerfile first. At publication, replace the default with the verified published **multiarch digest**. Build a derived image with:

```sh
docker build --build-arg RUNTIME_IMAGE=curlimp:local -t curlimp:distribution-local .
docker run --rm curlimp:distribution-local --version
```

Override `RUNTIME_IMAGE` to select another runtime image. An inaccessible image fails the build without falling back to source compilation. Docker may resolve or download the selected image and Dockerfile frontend.

### Profile parsing and completion

`src/profiles.txt` is the catalog consumed by the parser, completion engine, validated profile listing and website. `src/completion.rs` uses literal prefix matching and the parser's option arities. `completions/_curlimp` only connects Zsh to that Rust logic. No shell script carries a separate profile list. The hidden `--complete-profiles` action is an internal shell integration interface, not a request mode.

After building the CLI, run `cargo test --locked --test cli`, then `CLI=/absolute/path/to/curlimp python3 tests/completion.py` and `CLI=/absolute/path/to/curlimp python3 tests/zsh_completion.py`. The latter opens a clean Zsh PTY to verify actual Tab insertion, menu selection and Enter behavior. These checks need Python 3.11+ and Zsh. Completion does not configure the user's shell or run HTTP requests.

### Export artifacts

```sh
# Shared engine library, matching headers, licenses, and source provenance.
docker build -f docker/Dockerfile.build --platform linux/arm64 \
  --target engine-artifacts --output type=local,dest=dist/engine-arm64 .

# Complete runtime filesystem, exported under rootfs/.
docker build -f docker/Dockerfile.build --platform linux/arm64 \
  --target runtime-artifacts --output type=local,dest=dist/runtime/arm64 .
```

Use `linux/amd64` and distinct output directories for amd64. Use an empty export directory when replacing artifacts: the exporter does not remove obsolete files. The root Dockerfile consumes a runtime image, not these directories. A local image must be available to the selected Docker daemon builder; an isolated buildx container builder requires a registry image instead.

Engine exports target Linux glibc on Debian bookworm and are not universal Linux binaries. They contain shared libraries, not a merged static library. The Linux CLI bundles below include the glibc loader and runtime libraries. They are not single static executables. macOS uses the separate native build and package path below; Windows packages are not available.

### Package a Linux download

After exporting a complete runtime, use Python 3.11 or newer to create a bundle. Match `--arch` to the exported architecture. The archive version defaults to `package.version` in `Cargo.toml`, the same source used by the CLI and CI:

```sh
python3 scripts/package-release.py \
  --rootfs dist/runtime/arm64/rootfs --arch arm64 \
  --revision "$(git rev-parse HEAD)" --output dist/release
python3 tests/release_package.py
```

An explicit `--version` override remains available for packaging experiments; official releases use the manifest version. CI checks that the extracted CLI reports that same version.

The packager checks key ELF architectures, required runtime files and license notices, converts rootfs-absolute links to relative links, and rejects dangling or escaping links. It refuses to overwrite an archive. Archive timestamps and ownership are normalized; this does not make the underlying source build reproducible. `release.json` records the supplied source revision, so build from a clean checkout of that revision.

The launcher invokes the bundled dynamic loader with an explicit library path and preserves arguments, streams, working directory and exit status. It supplies the bundled CA file only when neither `CURL_CA_BUNDLE` nor `SSL_CERT_FILE` is nonempty (a directory-only `SSL_CERT_DIR` override still uses the bundled CA file); CLI `--cacert` still takes precedence. System DNS/NSS configuration remains host-controlled. Ubuntu 24.04 is the native CI validation target; do not infer support for all Linux distributions.

### Build on macOS Apple Silicon

Use a native ARM64 shell on an Apple Silicon Mac with Apple's Command Line Tools, Rust 1.85 or newer, CMake, Ninja, Go, Perl, patch, and make. The CI runner uses macOS 15 and Rust 1.90.0. Source downloads need network access. Python 3.12 or newer is used for packaging tests; OpenSSL and `nghttpd` from nghttp2 provide the TLS/HTTP2 fixtures.

With Homebrew installed, build/test tools can be installed with `brew install cmake ninja go nghttp2 openssl@3`. Install Rust separately if needed. These are developer dependencies; the resulting download does not need Homebrew to run.

```sh
# Use a fresh absolute workspace outside the checkout.
workspace="$TMPDIR/curlimp-macos-build"
sh scripts/build-macos.sh "$workspace" 4

# Test the CLI and the packager's real Mach-O fixtures.
CURL_IMPERSONATE_DIR="$workspace/native" CARGO_TARGET_DIR="$workspace/target" \
  cargo test --release --locked --test cli
python3 tests/macos_package.py

# Package a clean, committed checkout using its actual source revision.
python3 scripts/package-macos.py \
  --binary "$workspace/target/release/curlimp" \
  --native-prefix "$workspace/native" \
  --revision "$(git rev-parse HEAD)" --output dist/release

# Run the extracted download, including mandatory HTTP2 tests.
bundle="curlimp-$(python3 scripts/release_version.py)-macos-arm64"
tar -xzf "dist/release/$bundle.tar.gz" -C dist/release
export CLI="$PWD/dist/release/$bundle/curlimp"
export PATH="$(brew --prefix openssl@3)/bin:$(brew --prefix nghttp2)/bin:$PATH"
REQUIRE_HTTP2=1 python3 tests/compat.py
python3 tests/release_tls.py
python3 tests/exports.py
"$CLI" -sS --fail \
  --connect-timeout 10 --max-time 30 -o /dev/null https://httpbin.org/status/200
```

The helper verifies vendored inputs, builds and checks the native engine, collects dependency licenses and provenance, and compiles the Rust CLI. AppleIDN is used instead of libidn2. `MACOSX_DEPLOYMENT_TARGET` defaults to `13.0`; that compile setting is not a claim that older macOS versions have been tested. Use a workspace without commas and a fresh native installation prefix.

The packager requires thin ARM64 Mach-O inputs and rejects non-system dependencies other than the bundled engine. It copies the CLI and engine, removes build-directory RPATHs, uses `@executable_path/lib`, and signs both copies ad hoc. Originals remain unchanged. Required dependency notices and provenance are included, and existing archives are not overwritten. The package is not Developer ID signed or notarized. CI tests the extracted archive in a path with spaces; it does not test Gatekeeper's downloaded-file approval flow.

### Publish a release

1. Set `package.version` in `Cargo.toml` and update `Cargo.lock`. CI and both packagers read that version through `scripts/release_version.py`; no separate CI version constant is needed. Update the README, changelog, and `docker/README.md` for the intended release. Select the Docker tag/digest deliberately. Commit the source and run CI on that exact revision.
2. Require successful Linux amd64, Linux arm64, and macOS Apple Silicon jobs. Linux jobs build and test the minimal runtime and packager; macOS builds the engine and CLI and tests real Mach-O packaging. All three run local response-export tests and extract the archive into a path with spaces and run HTTP/TLS/HTTP2 compatibility and certificate tests directly on the native runner. Each also runs a bounded public HTTPS smoke check; public-service failures can require a rerun.
3. Download the `linux-amd64`, `linux-arm64`, and `macos-arm64` artifacts from that run. Check each archive's `release.json` against the tested revision, platform, and release version. Preserve the tested `.tar.gz` bytes.
4. Generate `SHA256SUMS` over all three archives, tag the exact tested commit, and upload the archives and checksum file to a draft release. Download them again and verify the checksums before publishing. Mark release candidates as pre-releases.
5. Include installation instructions, validation scope, macOS signing/notarization status, known limits, and the Docker image tag/digest in the release notes. For each stable release, publish its versioned Docker tag and point `latest` to the same validated multiarch index. Verify matching digests and both `linux/amd64` and `linux/arm64` before announcing the release. Never promote an RC or other pre-release to `latest`. Keep versioned tags and existing assets unchanged. Public usage examples use `latest`; fixed-version examples, native downloads, release metadata and the root Dockerfile's version/digest pin still need updating for each release.
6. Publish `docker/README.md` as the Docker Hub overview and verify it against the repository copy. Verify anonymous downloads and image pulls for public releases.

Packaging changes alone do not require rebuilding an unchanged Docker runtime. If a new release tag should refer to that runtime, copy its existing multiarch index with `docker buildx imagetools create --tag IMAGE:NEW_TAG IMAGE@sha256:DIGEST`, then verify the resulting digest and both architectures. State that promotion explicitly in the notes; do not claim that the image was compiled from the new release commit. Native downloads are built by CI from the tagged source. Release publication does not change repository visibility.

### Engine inputs and updates

`engine.lock` pins the checksum manifest of the local engine snapshot and the separate libidn2 source archive. The vendored CMake superbuild pins the remaining dependency sources. `scripts/prepare-engine.sh` checks the manifest and imported files before use; `scripts/build-engine.sh` (Linux) and `scripts/build-macos.sh` (Apple Silicon) compile them and run native feature checks. The native API bridge uses matching headers and libraries. Native profile definitions are compiled into the engine; `src/profiles.txt` lists their names and is embedded in the CLI at compile time.

To update the engine, review and import the required source changes, preserve their notices, and update `vendor/curl-impersonate/ORIGIN.md`. Regenerate the existing `SHA256SUMS` file list and its hash in `engine.lock`, then update the profile catalog when needed. Build and test all three platform/architecture combinations in CI. Compare network captures with real browsers before claiming a fidelity improvement.

The runtime includes build provenance at `/opt/native/engine-build.txt`, plus `engine-origin.md`, `engine-inputs.sha256`, `runtime-libraries.txt`, and `runtime-packages.txt`. Inspect them in a filesystem export or with `docker cp`; the diagnostic image also supports `--entrypoint cat`.

Source builds download pinned dependency archives and use container registries and Debian package repositories. System package versions and the entire build environment are not locked, so byte-for-byte reproducibility is not guaranteed. Rebuild the runtime to refresh system libraries or certificates. Pin published images by digest when immutable selection is required. Signed releases and a complete SBOM remain future work.

### Validation scope

`test-minimal` runs source integrity checks, parser tests, and local HTTP/TLS/HTTP2 integration tests, then repeats the integration tests inside the assembled runtime filesystem with `chroot`. Test tools stay outside the final image. The suite checks all 39 profile names against the compiled engine, the default Chrome profile, explicit/environment precedence, and `--no-impersonate`. Compression checks cover automatic gzip/deflate decoding, explicit overrides, header order and values, binary output, and opt-in decoding without a profile. Curl-default comparisons explicitly disable impersonation; default-browser requests are checked separately, including HTTP2. It does not compare browser fingerprints or establish HTTP/3 fidelity. Compatibility assertions use local fixtures; the download workflow also runs one bounded public HTTPS smoke check.

## Validate your change

Run checks for the code you changed and its directly affected dependencies. Documentation-only edits need a diff and link review. Do not rebuild the engine or run unrelated application tests for documentation changes.

For source verification helpers, use the focused checks below. They use temporary files and do not download engine sources:

```sh
python3 tests/vendor_engine.py
python3 tests/source_download.py
sh -n scripts/prepare-engine.sh scripts/build-engine.sh scripts/fetch-verified.sh scripts/package-minimal.sh
```

For CLI, native engine, or runtime-packaging changes, select the relevant integration checks. The `test-minimal` target above validates the assembled runtime; engine and packaging changes also need an actual-container DNS/HTTPS smoke check. Validate all published platform/architecture combinations before a release. Distinguish functional compatibility checks from comparisons with real-browser network captures.

## Submit a pull request

Explain the problem, the resulting behavior, affected platforms or profiles, and the checks you ran. Include known limitations or checks you could not run. Keep generated binaries, runtime exports, local configuration, credentials, and session notes out of commits. Check the staged diff before submitting.

The root [LICENSE](LICENSE) covers original project code; [NOTICE](NOTICE) points to incorporated components and their notices. The profile catalog in `src/profiles.txt` is a CLI build input, while the native definitions contain the settings. Keep both synchronized when profiles change. The website generates its profile catalog from `src/profiles.txt`; update the Docker Hub profile table and any profile counts or examples in the README and documentation as needed.
