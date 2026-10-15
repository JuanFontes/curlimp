#!/usr/bin/env python3
"""Select downstream PR checks; unknown paths conservatively test the runtime."""
import argparse
from fnmatch import fnmatchcase
import subprocess

RUNTIME_EXCLUSIONS = (
    'website/**', 'README.md', 'docker/README.md', 'CONTRIBUTING.md',
    'SECURITY.md', 'CHANGELOG.md', '.github/release-notes/**', '.gitignore',
    '.github/dependabot.yml', '.github/workflows/pages.yml',
    '.github/workflows/site-build.yml', '.github/workflows/dependency-review.yml',
    '.github/workflows/dependency-report.yml', 'scripts/dependency_report.py',
    'tests/dependency_report.py', 'scripts/published_release.py',
    'tests/published_release.py', '.prettierrc.json', '.prettierignore',
    'ruff.toml', '.shellcheckrc', '.github/requirements.txt',
    'scripts/check-quality.py',
)
SITE_INPUTS = (
    'website/**', 'README.md', 'docker/README.md', 'Cargo.toml',
    'src/help.txt', 'src/profiles.txt', '.github/workflows/pages.yml',
    '.github/workflows/site-build.yml', '.github/workflows/pull-request.yml',
    '.github/workflows/ci.yml', 'scripts/pr_checks.py', 'tests/pr_checks.py',
    'scripts/published_release.py', 'tests/published_release.py',
    'scripts/release_policy.py', 'tests/release_policy.py',
    'scripts/release_version.py',
)


def select_checks(paths):
    paths = tuple(paths)
    return {
        'runtime': any(not any(fnmatchcase(path, pattern) for pattern in RUNTIME_EXCLUSIONS)
                       for path in paths),
        'site': any(fnmatchcase(path, pattern) for path in paths for pattern in SITE_INPUTS),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, help='PR base commit available locally')
    args = parser.parse_args()
    # Compare the checked-out merge result with its base. Disable rename detection
    # so moving a native input into documentation still validates its removal.
    changed = subprocess.check_output([
        'git', 'diff', '--name-only', '--no-renames', '-z', args.base, 'HEAD', '--',
    ]).decode('utf-8', errors='surrogateescape').split('\0')
    for name, enabled in select_checks(path for path in changed if path).items():
        print(f'{name}={str(enabled).lower()}')


if __name__ == '__main__':
    main()
