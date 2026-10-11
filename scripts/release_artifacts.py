#!/usr/bin/env python3
"""Verify CI bundle provenance and preserve the tested archive bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tarfile

from release_version import release_version


def validate_run(run, revision, main_revision, repository):
    if main_revision != revision:
        raise ValueError('main has moved since this publication started')
    expected = dict(status='completed', conclusion='success', path='.github/workflows/ci.yml',
                    head_sha=revision, head_branch='main')
    for key, value in expected.items():
        if run.get(key) != value:
            raise ValueError(f'CI {key} does not match the release source')
    if run.get('head_repository', {}).get('full_name') != repository:
        raise ValueError('Wrong CI repository')
    if run.get('event') not in ('push', 'workflow_dispatch'):
        raise ValueError('Pull request runs cannot publish')


def prepare(artifacts, output, revision):
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Invalid source_revision')
    if output.exists():
        raise ValueError('Release output already exists')
    version = release_version()
    verified = []
    for system, architecture in [('linux', 'amd64'), ('linux', 'arm64'), ('macos', 'arm64')]:
        platform = f'{system}-{architecture}'
        name = f'curlimp-{version}-{platform}'
        archive = artifacts / platform / f'{name}.tar.gz'
        if not archive.is_file() or archive.is_symlink():
            raise ValueError(f'Missing regular bundle for {platform}')
        with tarfile.open(archive, 'r:gz') as bundle:
            matches = [m for m in bundle.getmembers() if m.name == f'{name}/release.json']
            if len(matches) != 1 or not matches[0].isfile() or matches[0].size > 16384:
                raise ValueError(f'Expected one regular release.json in {platform}')
            metadata = json.load(bundle.extractfile(matches[0]))
        expected = dict(version=version, system=system, architecture=architecture, source_revision=revision)
        for key, value in expected.items():
            if metadata.get(key) != value:
                raise ValueError(f'{platform}: {key} does not match the tested release')
        verified.append(archive)
    output.mkdir(parents=True)
    checksums = []
    for archive in verified:
        destination = output / archive.name
        shutil.copyfile(archive, destination)
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        checksums.append(f'{digest}  {archive.name}\n')
    (output / 'SHA256SUMS').write_text(''.join(sorted(checksums)))
    print(f'Verified all three {version} bundles from {revision}; archive bytes preserved.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    args = parser.parse_args()
    try:
        prepare(args.artifacts, args.output, args.revision)
    except (ValueError, OSError, tarfile.TarError, KeyError, TypeError) as error:
        print(f'Release verification failed: {error}', file=sys.stderr)
        sys.exit(1)
