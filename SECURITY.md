# Security

## Reporting a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/JuanFontes/curlimp/security/advisories/new) for suspected security vulnerabilities. Include the Curlimp version, platform, minimal reproduction, relevant options, and expected impact. Remove credentials and private response content. Do not publish exploit details in a public issue before coordination.

Security fixes target the latest stable release. Older versions do not receive a separate maintenance guarantee. A report or automated alert is a starting point for investigation; no response-time guarantee is made.

## Dependency monitoring

- Dependabot alerts and security updates cover dependencies recognized by GitHub. Weekly version updates cover website npm packages, GitHub Actions, and the Debian/Rust images in `docker/Dockerfile.build`. Major npm/action updates remain separate from grouped minor/patch updates. Updates require review and the applicable CI checks; automatic merge is not configured.
- The root Dockerfile's published Curlimp version stays under release control. Native dependencies pinned in CMake and `engine.lock` require explicit source, hash, patch, and compatibility review. Cargo currently has no external crates; add Cargo monitoring when that changes.
- The **Dependency review** PR check rejects newly introduced known high/critical vulnerabilities in supported dependency changes, including development dependencies. Lower-severity findings remain visible for triage. It does not assess arbitrary native pins or establish the safety of the whole repository.
- Actions remain pinned to commit SHAs. Dependabot can update these pins, but GitHub documents that its Actions vulnerability alerts require semantic version references; SHA pins are not fully covered by those alerts.
- Repository secret scanning and push protection detect supported credential patterns. They do not detect every secret; generated test fixtures are not production credentials.

## Native advisory coverage

The **Native dependency maintenance report** runs weekly, manually, and after relevant changes on `main`. It queries curl's official advisory feed and published GitHub advisories for Brotli, BoringSSL, nghttp2, ngtcp2, nghttp3, zlib, zstd, c-ares, and libpsl. An empty upstream feed does not prove the absence of vulnerabilities. libidn2, Git-only applicability, and interactions with our patches still require manual review.

The report writes Markdown and JSON evidence even when attention is required:

| Exit code | Meaning |
| --- | --- |
| `0` | Integrated sources completed without unresolved matching advisories; manual coverage limits still apply |
| `1` | A source, schema, or applicability check failed; the report is incomplete |
| `2` | Sources completed, but one or more advisories require triage |

The known nghttp2 backport is accepted only for its exact advisory ID and the expected patch digest. New advisories are not automatically dismissed because a dependency is patched. Ambiguous ranges and conflicting affected/patched metadata require review. The live report is an alerting workflow, separate from the required PR check; its failures must be investigated, not hidden with `continue-on-error` or broad ignore rules.

To inspect a report locally:

```sh
python3 scripts/dependency_report.py --output dependency-report
```

An optional `GITHUB_TOKEN` increases the GitHub API rate limit. Tokens are sent only to the GitHub API. Reports do not update dependencies, create issues, or publish releases. See [CONTRIBUTING.md](CONTRIBUTING.md#engine-inputs-and-updates) for the native update procedure.

## Validation limits

Dependency monitoring does not establish browser fingerprint equivalence or detect every vulnerability in Rust, C, native libraries, or packaged system components. CodeQL integration, a complete release SBOM, and artifact vulnerability scanning remain separate work. Keep credentials out of commands and logs shared publicly; exported responses may contain sensitive data.
