# Security

## Reporting a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/JuanFontes/curlimp/security/advisories/new) for suspected security vulnerabilities. Include the Curlimp version, platform, minimal reproduction, relevant options, and expected impact. Remove credentials and private response content. Do not publish exploit details in a public issue before coordination.

Security fixes target the latest stable release. Older versions do not receive a separate maintenance guarantee. A report or automated alert is a starting point for investigation; no response-time guarantee is made.

## Dependency monitoring

- Dependabot alerts and security updates cover dependencies recognized by GitHub. Weekly version updates cover website npm packages, GitHub Actions, Python lint tools, and the Debian/Rust images in `docker/Dockerfile.build`. Major npm/action updates remain separate from grouped minor/patch updates. Updates require review and the applicable CI checks; automatic merge is not configured.
- The root Dockerfile's published Curlimp version stays under release control. Native dependencies pinned in CMake and `engine.lock` require explicit source, hash, patch, and compatibility review. Cargo currently has no external crates; add Cargo monitoring when that changes.
- The **Dependency review** PR check rejects newly introduced known high/critical vulnerabilities in supported dependency changes, including development dependencies. Lower-severity findings remain visible for triage. It does not assess arbitrary native pins or establish the safety of the whole repository.
- Actions remain pinned to commit SHAs. Dependabot can update these pins, but GitHub documents that its Actions vulnerability alerts require semantic version references; SHA pins are not fully covered by those alerts.
- Repository secret scanning and push protection detect supported credential patterns. They do not detect every secret; generated test fixtures are not production credentials.

## Native advisory coverage

The **Native dependency maintenance report** runs weekly, manually, and after relevant changes on `main`. It queries curl's official advisory feed and published GitHub advisories for Brotli, BoringSSL, nghttp2, ngtcp2, nghttp3, zlib, zstd, c-ares, and libpsl. An empty upstream feed does not prove the absence of vulnerabilities. libidn2, Git-only applicability, and interactions with our patches still require manual review.

The report writes Markdown and JSON evidence even when attention is required:

| Exit code | Meaning                                                                                                 |
| --------- | ------------------------------------------------------------------------------------------------------- |
| `0`       | Integrated sources completed without unresolved matching advisories; manual coverage limits still apply |
| `1`       | A source, schema, or applicability check failed; the report is incomplete                               |
| `2`       | Sources completed, but one or more advisories require triage                                            |

Reviewed backports are accepted only for their specific advisory IDs and expected patch digests. The ngtcp2 and c-ares dispositions also require the exact pinned archive, version, build recipe, and affected/patched metadata; changes reopen triage. New advisories are not automatically dismissed because a dependency is patched. Ambiguous ranges and conflicting affected/patched metadata require review. The live report is an alerting workflow, separate from the required PR check; its failures must be investigated, not hidden with `continue-on-error` or broad ignore rules.

To inspect a report locally:

```sh
python3 scripts/dependency_report.py --output dependency-report
```

An optional `GITHUB_TOKEN` increases the GitHub API rate limit. Tokens are sent only to the GitHub API. Reports do not update dependencies, create issues, or publish releases. See [CONTRIBUTING.md](CONTRIBUTING.md#engine-inputs-and-updates) for the native update procedure.

## Reviewed native advisories

These dispositions remain visible in the JSON and Markdown report, with the original affected/patched metadata and review sources. They apply only to the exact inputs checked by `scripts/dependency_report.py`; they do not ignore new advisories or infer safety from a generic minimum version.

### ngtcp2: CVE-2026-40170 / GHSA-f523-465f-8c8f

Curlimp 0.5.1 adds the [official qlog fix](https://github.com/ngtcp2/ngtcp2/commit/708a7640c1f48fb8ffb540c4b8ea5b4c1dfb8ee5) to `vendor/engine/patches/ngtcp2.patch`, while retaining ngtcp2 1.20.0 and the existing browser-related changes. The [advisory](https://github.com/ngtcp2/ngtcp2/security/advisories/GHSA-f523-465f-8c8f) covers a stack buffer overflow when qlog serializes peer transport parameters; upstream fixes it in 1.22.1. The backport enlarges the parameter-event buffer as upstream prescribes.

`python3 tests/native_security.py` downloads and verifies the pinned archive, applies the complete vendored ngtcp2 patch, and compiles its core with AddressSanitizer in a temporary directory. It checks complete serialized events with long transport parameters, optional fields, both endpoint roles, and disabled logging. The regression reproduced the overflow before the fix and passes with it. CI runs it on Linux amd64/arm64 and macOS arm64. Sanitizer instrumentation is confined to the test build and is not shipped in runtime images or native downloads.

### c-ares: CVE-2026-33630 / GHSA-6wfj-rwm7-3542

The [advisory](https://github.com/c-ares/c-ares/security/advisories/GHSA-6wfj-rwm7-3542) lists an unbounded affected range, `> 1.32.3`, but identifies 1.34.7 as patched. Its description and the [official changelog](https://c-ares.org/changelog.html) say the query-completion fix shipped in 1.34.7. Version 1.34.8 reverts a callback signature change; it retains the security fix.

The reviewed disposition is **fixed-in-pinned-source**, restricted to c-ares 1.34.8 and archive SHA-256 `c222b6d681096f9444d2c4863d2c1174019e27cacca0a4a5c114d36dd7d7bf78`. Evidence checked on 2026-10-15:

- The [v1.34 fix commit](https://github.com/c-ares/c-ares/commit/d823199b688052dcdc1646f2ab4cb8c16b1c644a) consolidates deferred query completion and fixes reentrant double-free handling.
- [The 1.34.8 tag descends from that commit](https://github.com/c-ares/c-ares/compare/d823199b688052dcdc1646f2ab4cb8c16b1c644a...v1.34.8); the later changes do not revert the affected implementation.
- `src/lib/ares_process.c` and `test/ares-test-mock.cc` in the verified release archive match the Git blobs at the fix commit. Their SHA-256 values are `8d3ea0ef9f3334733b73e9a0b51ed112ba9be98c58af236e0b283b7d9186f68f` and `a8d36fadd2dfdaf789bb7699e211158714addc5f50ee506cd140448d72a32a4f`, respectively.
- The reviewed build recipe applies no local c-ares patch. The reporter checks its digest, the source version/hash, and the exact conflicting metadata before applying this disposition.

This is a review of one advisory against one source archive, not a claim that every c-ares version after 1.34.7 is unaffected by every vulnerability. Older pins, modified sources or recipes, different IDs, and changed affected/patched metadata remain actionable.

## Validation limits

Dependency monitoring does not establish browser fingerprint equivalence or detect every vulnerability in Rust, C, native libraries, or packaged system components. CodeQL integration, a complete release SBOM, and artifact vulnerability scanning remain separate work. Keep credentials out of commands and logs shared publicly; exported responses may contain sensitive data.
