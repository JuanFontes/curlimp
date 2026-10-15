# Contributing

For the published image and request examples, start with the [README](README.md#quick-start). Run the commands below from the repository root.

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

`NATIVE_JOBS` defaults to 4; smaller builders can use `--build-arg NATIVE_JOBS=2`. CLI-only changes reuse native compilation layers when cached. Dockerfile-specific ignore rules include only source-build inputs and exclude generated or local files; distribution builds need no local files. Update `docker/Dockerfile.build.dockerignore` when adding a new build input outside the listed paths. The GitHub Actions workflow tests each architecture with an isolated Buildx builder and a persistent cache, exports runtime files into the runner filesystem, and loads the tested runtime into the Docker daemon before deriving the distribution image. It also packages Linux downloads, runs the extracted launcher directly on each native runner, and uploads the tested archives as workflow artifacts. It also retains the tested Docker images for seven days. It does not publish automatically; the separate release workflow consumes a successful run.

### CI cache and validation

Runtime CI runs on pull requests, pushes to `main`, and manual dispatch. Branch pushes do not start a second build alongside their pull request. New validation runs cancel obsolete runs for the same pull request or branch; release publication remains serialized and is never cancelled this way.

Linux uses GitHub Actions BuildKit caches separated by architecture. Input changes invalidate their dependent layers. Intermediate native build trees are removed before the installed engine layer is saved. The `test` and `test-minimal` stages explicitly bypass cache: parser, completion, HTTP/TLS/HTTP2, export and minimal-runtime tests execute on every run. The upstream `make checkbuild` feature assertions run against the installed native executable even on cache hits, on both Linux and macOS. Extracted download tests also always run.

macOS caches only the installed native engine. The exact key includes vendored inputs, build scripts, OS/architecture, deployment target, compiler, SDK and native build-tool versions. Every restore verifies the complete file inventory, hashes, permissions and symlink targets; invalid or incomplete installations are rebuilt. The Rust CLI is compiled from the current checkout and the resulting bundle is tested before saving a new engine cache. `build-macos.sh WORKSPACE JOBS --engine-only` supplies this CI path; the normal command still builds both the engine and CLI.

There are no fallback macOS restore keys. GitHub isolates pull-request caches from the default branch. A cache miss is a normal source build. To refresh cached system packages/certificates or recover from a bad cache, delete the affected Actions caches or bump the cache-generation suffixes in `ci.yml` (`runtime-ARCH-v1` and `macos-native-v1`). Cache reuse does not establish byte-for-byte reproducibility.

The cache and publication helpers have focused, network-free tests:

```sh
python3 tests/native_cache.py
python3 tests/published_release.py
```

### Derive your own image from a ready-made runtime

The root `Dockerfile` defaults to the published runtime. Build a local runtime with the maintainer Dockerfile and override `RUNTIME_IMAGE` to test your changes:

```sh
docker build --build-arg RUNTIME_IMAGE=curlimp:local -t curlimp:distribution-local .
docker run --rm curlimp:distribution-local --version
```

Override `RUNTIME_IMAGE` to select another runtime image. An inaccessible image fails the build without falling back to source compilation. Docker may resolve or download the selected image and Dockerfile frontend.

### Profile parsing and completion

`src/profiles.txt` is the catalog consumed by the parser, completion engine, validated profile listing and website. `src/completion.rs` uses literal prefix matching and the parser's option arities. `completions/_curlimp` only connects Zsh to that Rust logic. No shell script carries a separate profile list. The hidden `--complete-profiles` action is an internal shell integration interface, not a request mode.

After building the CLI, run `cargo test --locked --lib --test cli`, then `CLI=/absolute/path/to/curlimp python3 tests/completion.py` and `CLI=/absolute/path/to/curlimp python3 tests/zsh_completion.py`. The latter opens a clean Zsh PTY to verify actual Tab insertion, menu selection and Enter behavior. These checks need Python 3.11+ and Zsh. Completion does not configure the user's shell or run HTTP requests.

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

The launcher invokes the bundled dynamic loader with an explicit library path and preserves arguments, streams, working directory and exit status. It supplies the bundled CA file through `SSL_CERT_FILE` only when neither `CURL_CA_BUNDLE` nor `SSL_CERT_FILE` is nonempty, so a directory-only `SSL_CERT_DIR` setting combines with the bundled CA file. Explicit `CURL_CA_BUNDLE` and CLI `--cacert` retain their precedence and suppress the environment directory. System DNS/NSS configuration remains host-controlled. Ubuntu 24.04 is the native CI validation target; do not infer support for all Linux distributions.

### Build on macOS Apple Silicon

Use a native ARM64 shell on an Apple Silicon Mac with Apple's Command Line Tools, Rust 1.85 or newer, CMake, Ninja, Go, Perl, patch, and make. The CI runner uses macOS 15 and Rust 1.90.0. Source downloads need network access. Python 3.12 or newer is used for packaging tests; OpenSSL and `nghttpd` from nghttp2 provide the TLS/HTTP2 fixtures.

With Homebrew installed, build/test tools can be installed with `brew install cmake ninja go nghttp2 openssl@3 python`. Install Rust separately if needed. Python 3 generates the native engine's built-in Public Suffix List and runs integration checks. These are developer dependencies; the resulting download does not need Homebrew to run.

```sh
# Use a fresh absolute workspace outside the checkout.
workspace="$TMPDIR/curlimp-macos-build"
sh scripts/build-macos.sh "$workspace" 4

# Test the CLI and the packager's real Mach-O fixtures.
CURL_IMPERSONATE_DIR="$workspace/native" CARGO_TARGET_DIR="$workspace/target" \
  cargo test --release --locked --lib --test cli
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
python3 tests/transfers.py
"$CLI" -sS --fail \
  --connect-timeout 10 --max-time 30 -o /dev/null https://httpbin.org/status/200
```

The helper verifies vendored inputs, builds and checks the native engine, collects dependency licenses and provenance, and compiles the Rust CLI. AppleIDN is used instead of libidn2. `MACOSX_DEPLOYMENT_TARGET` defaults to `13.0`; that compile setting is not a claim that older macOS versions have been tested. Use a workspace without commas and a fresh native installation prefix.

The packager requires thin ARM64 Mach-O inputs and rejects non-system dependencies other than the bundled engine. It copies the CLI and engine, removes build-directory RPATHs, uses `@executable_path/lib`, and signs both copies ad hoc. Originals remain unchanged. Required dependency notices and provenance are included, and existing archives are not overwritten. The package is not Developer ID signed or notarized. CI tests the extracted archive in a path with spaces; it does not test Gatekeeper's downloaded-file approval flow.

### Publish a release

Configure repository secrets `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` using a Docker Hub personal access token with push and repository-metadata access. Keep credentials out of files and logs. The workflow publishes only from `main` and uses the repository's `GITHUB_TOKEN` for release assets.

1. Update `Cargo.toml`, `Cargo.lock`, the root Dockerfile's versioned default, the changelog, versioned examples and `.github/release-notes/VERSION.md`. Run `python3 scripts/check-distribution.py` to verify the Dockerfile and Cargo versions agree. Update `docker/README.md` and the short `docker/description.txt` (maximum 100 characters). Commit and push the release source to `main`.
2. Wait for **Build and package runtime** to pass on that exact revision. All three platforms must pass. CI uploads three native archives plus the two tested Docker image archives; release publication must occur before the image artifacts expire after seven days.
3. Run **Publish tested release** from Actions on `main`, supplying that successful CI run ID. The workflow rejects a different revision, incomplete build, existing release/tag/image version, or mismatched bundle/image metadata. It preserves the tested archive bytes.
4. The workflow pushes architecture staging tags named `build-COMMIT-ARCH`, creates the versioned multiarch image, creates a draft GitHub release, downloads its assets again and checks `SHA256SUMS`. Immediately before publication, the shared `scripts/release_policy.py` queries GitHub's current latest stable release. It publishes the versioned GitHub release with `--latest=false`. Only a newer stable SemVer core promotes Docker `latest`, updates the stable Docker Hub overview and description, and becomes GitHub Latest. Older stable releases and prereleases retain their versioned downloads without changing these stable channels. An explicit HTTP 404 allows the first stable release; authentication, rate-limit, service and malformed-response errors stop publication.
5. Check published downloads, both image platforms and Docker Hub text. The root Dockerfile already selects the same immutable-by-policy versioned image, so no follow-up source commit is required. For a digest-pinned build, override `RUNTIME_IMAGE=juanfontes/curlimp:VERSION@sha256:DIGEST`. Keep the versioned image and release assets unchanged.
6. Verify anonymous image pulls, asset downloads and the documentation website before announcing a public release. Repository visibility and Pages activation are managed separately from the release workflow.

The release workflow intentionally stops if the version already exists. If publication is interrupted, inspect the registry, draft release and logs before recovering; do not delete or overwrite published versioned assets just to rerun it. Use a new version for changed binaries. Stable-channel promotion is sequential across services, not transactional: a failed Docker promotion or Hub update stops subsequent steps, including GitHub Latest. The versioned release remains available; inspect partial channel updates before manual recovery and rerun the shared policy against the current stable release. Refresh only Docker Hub text with `python3 scripts/update-dockerhub.py` and the same two environment variables.

After a successful release workflow, the Pages workflow rebuilds and checks the site. Production deployment requires the current latest stable GitHub release to match `Cargo.toml`, all three native archives and `SHA256SUMS`, and an active Docker version tag for Linux amd64/arm64. Until those downloads exist, the previous public site stays online. The gate runs before building a production deployment and again immediately before deploying it. API failures fail the publication check instead of bypassing it. See [website/README.md](website/README.md#publish).

### Engine inputs and updates

`engine.lock` pins the checksum manifest of the local engine snapshot and the separate libidn2 source archive. The vendored CMake superbuild pins the remaining dependency sources. `scripts/prepare-engine.sh` checks the manifest and imported files before use; `scripts/build-engine.sh` (Linux) and `scripts/build-macos.sh` (Apple Silicon) compile them and run native feature checks. The native API bridge uses matching headers and libraries. Native profile definitions are compiled into the engine; `src/profiles.txt` lists their names and is embedded in the CLI at compile time.

Run `python3 tests/dependency_report.py` for offline reporting-policy checks. To inspect current releases and upstream security advisories, run `python3 scripts/dependency_report.py --output dependency-report`. The Monday/manual dependency-report workflow also runs after relevant changes on `main`. It saves Markdown and JSON evidence without changing repository state or posting issues. Exit code `1` means a source or applicability check failed; `2` means advisories still need triage. Neither is a clean security result. The reporter covers curl's explicit affected-version lists and published GitHub advisories in the native projects' repositories. Empty feeds, libidn2, Git-only applicability, and patch interactions still require manual review. See [SECURITY.md](SECURITY.md#native-advisory-coverage) for exact coverage and interpretation.

nghttp2 remains pinned to 1.63.0 for legacy HTTP/2 priorities, with the official CVE-2026-27135 fix backported. The reporter recognizes that exact patch digest, not arbitrary local fixes. Newer native releases are review candidates, not automatic upgrades. Source updates require verified hashes, reviewed patches, a regenerated vendor manifest and `engine.lock`, fresh native build/checkbuild, and affected protocol or compression tests. Follow the project's patch-approval rule before changing a patch.

### Automated dependency updates

Dependabot proposes weekly updates for website npm packages, SHA-pinned GitHub Actions, and images in `docker/Dockerfile.build`. Compatible npm/action updates are grouped; major updates stay separate. Security update PRs are independent of that weekly schedule. No automatic merge is configured. The root Dockerfile stays aligned with release promotion, and native CMake pins are not edited by Dependabot. Add a Cargo entry if external Rust crates are introduced.

The **Dependency review** check runs on every PR and rejects introduced known high/critical dependency vulnerabilities, including build/development dependencies. **Native reporting policy** runs the offline reporter tests. Reporting-only changes do not trigger native runtime builds; changes to build workflows, native inputs, and builder images retain their platform tests and cache policy. Dependabot PRs use read-only credentials and do not receive publication secrets. Review changes to Actions and Docker images carefully: automatic proposals are not a trust decision. Security alerts, secret scanning, push protection, private reporting, and required checks are repository settings, separate from the committed workflow files.

To update the engine, review and import the required source changes, preserve their notices, and update `vendor/engine/ORIGIN.md`. Regenerate the existing `SHA256SUMS` file list and its hash in `engine.lock`, then update the profile catalog when needed. Build and test all three platform/architecture combinations in CI. Compare network captures with real browsers before claiming a fidelity improvement.

The runtime includes build provenance at `/opt/native/engine-build.txt`, plus `engine-origin.md`, `engine-inputs.sha256`, `runtime-libraries.txt`, and `runtime-packages.txt`. Inspect them in a filesystem export or with `docker cp`; the diagnostic image also supports `--entrypoint cat`.

Source builds download pinned dependency archives and use container registries and Debian package repositories. System package versions and the entire build environment are not locked, so byte-for-byte reproducibility is not guaranteed. CI computes one weekly UTC runtime refresh generation for the entire run and passes it to every runtime build stage. Weekly refresh bounds normal package-cache age while preserving the expensive native compiler cache. The runtime layer explicitly installs the newest available `libc6`, `libgcc-s1`, `libstdc++6`, `gcc-12-base`, and `ca-certificates`, covering all copied Debian runtime packages. `runtime-packages.txt` records their installed versions and `runtime-refresh.txt` records the generation. Use the workflow's `runtime_refresh` input (for example `security-2026-10-14`) for an urgent refresh; use `--build-arg RUNTIME_REFRESH=GENERATION` in local source builds. A refresh builds a new candidate, never overwrites an existing release version. Both Linux architectures must also pass a final Docker-container DNS/HTTPS check that writes and validates a private bind-mounted JSON file as the host nonroot UID/GID, with numeric UID/GID 65532 as the explicit fallback for root callers. Pin published images by digest when immutable selection is required. Signed releases and a complete SBOM remain future work.

### Validation scope

`test-minimal` runs source integrity checks, parser tests, and local HTTP/TLS/HTTP2 integration tests, then repeats the integration tests inside the assembled runtime filesystem with `chroot`. Test tools stay outside the final image. The transfer suite checks sequential order, parallel admission bounds, file pairing, shared cookies, mixed failures, ordered JSON, temporary-storage errors, and bounded export resources. The suite checks all 38 profile names against the compiled engine, the default Chrome profile, explicit/environment precedence, and `--no-impersonate`. Compression checks cover automatic gzip/deflate decoding, explicit overrides, header order and values, binary output, and opt-in decoding without a profile. Curl-default comparisons explicitly disable impersonation; default-browser requests are checked separately, including HTTP2. It does not compare browser fingerprints or establish HTTP/3 fidelity. Compatibility assertions use local fixtures; the download workflow also runs one bounded public HTTPS smoke check.

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
