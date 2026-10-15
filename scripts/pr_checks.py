#!/usr/bin/env python3
"""Select downstream PR checks; unknown paths conservatively test the runtime."""
import argparse
from fnmatch import fnmatchcase
import re
import subprocess
import sys

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
    'scripts/pr_checks.py', 'tests/pr_checks.py',
    'scripts/published_release.py', 'tests/published_release.py',
    'scripts/release_policy.py', 'tests/release_policy.py',
    'scripts/release_version.py',
)

PR_WORKFLOW = '.github/workflows/pull-request.yml'
QUALITY_JOB = re.compile(r'^  quality:\n.*?(?=^  [\w-]+:|\Z)', re.MULTILINE | re.DOTALL)
QUALITY_ACTION_PIN = re.compile(
    r'^(      - uses: actions/(?:checkout|setup-node|setup-python)@)'
    r'[0-9a-f]{40}(?:[ \t]+#[^\r\n]*)?$', re.MULTILINE,
)


def quality_action_pins_only(base):
    """Recognize only existing quality-job SHA/comment replacements, not YAML edits."""
    versions = []
    for revision in (base, 'HEAD'):
        try:
            content = subprocess.check_output(
                ['git', 'show', f'{revision}:{PR_WORKFLOW}'], stderr=subprocess.DEVNULL,
            ).decode('utf-8')
        except (subprocess.CalledProcessError, UnicodeDecodeError):
            # Added/deleted or unrecognized workflows retain full validation.
            return False
        jobs = list(QUALITY_JOB.finditer(content))
        if len(jobs) != 1:
            return False
        job = jobs[0]
        normalized, count = QUALITY_ACTION_PIN.subn(r'\1<PIN>', job.group())
        if not count:
            return False
        versions.append((content, content[:job.start()] + normalized + content[job.end():]))
    return versions[0][0] != versions[1][0] and versions[0][1] == versions[1][1]


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
    paths = [path for path in changed if path]
    if PR_WORKFLOW in paths and quality_action_pins_only(args.base):
        paths.remove(PR_WORKFLOW)
        print('Quality-job Action pins only: the required lint gate exercises these updates.',
              file=sys.stderr)
    for name, enabled in select_checks(paths).items():
        print(f'{name}={str(enabled).lower()}')


if __name__ == '__main__':
    main()
