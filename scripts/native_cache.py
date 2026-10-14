#!/usr/bin/env python3
"""Fingerprint and verify the installed macOS engine, never the Rust CLI or tests."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

MANIFEST = '.native-cache.json'
INPUTS = ['engine.lock', 'vendor/engine', 'scripts/prepare-engine.sh',
          'scripts/build-macos.sh', 'scripts/native_cache.py']
REQUIRED = ['include/curl/curl.h', 'lib/libcurl-impersonate.dylib',
            'engine-build.txt', 'engine-origin.md', 'engine-inputs.sha256']


def inventory(root, paths):
    entries = {}
    for path in sorted(set(paths)):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            if not path.resolve().is_relative_to(root.resolve()) or not path.exists():
                raise ValueError(f'Invalid cache symlink: {name}')
            entries[name] = {'link': os.readlink(path)}
        elif path.is_file():
            with path.open('rb') as source:
                digest = hashlib.file_digest(source, 'sha256').hexdigest()
            entries[name] = {'sha256': digest,
                             'mode': path.stat().st_mode & 0o777}
        elif not path.is_dir():
            raise ValueError(f'Missing or unsupported cache input: {name}')
    return entries


def fingerprint(repo, inputs, identity):
    paths = []
    for name in inputs:
        path = repo / name
        paths.extend(path.rglob('*') if path.is_dir() else [path])
    data = dict(schema=1, identity=identity, inputs=inventory(repo, paths))
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def snapshot(prefix):
    if not all((prefix / name).is_file() for name in REQUIRED) \
            or not any(path.is_file() for path in prefix.glob('LICENSE*')):
        raise ValueError('Incomplete native installation')
    return inventory(prefix, [path for path in prefix.rglob('*') if path.name != MANIFEST])


def seal(prefix, key):
    data = dict(key=key, files=snapshot(prefix))
    (prefix / MANIFEST).write_text(json.dumps(data, sort_keys=True) + '\n')


def verify(prefix, key):
    try:
        data = json.loads((prefix / MANIFEST).read_text())
        if data != dict(key=key, files=snapshot(prefix)):
            raise ValueError('Native cache key or installed files changed')
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f'Invalid native cache: {error}') from error


def toolchain_identity():
    commands = [['sw_vers', '-buildVersion'], ['xcrun', 'clang', '--version'],
                ['xcrun', '--show-sdk-version'], ['xcrun', '--show-sdk-path'],
                ['cmake', '--version'], ['ninja', '--version'], ['go', 'version'],
                ['make', '--version'], ['perl', '-V'], ['patch', '--version']]
    return dict(platform=platform.system(), architecture=platform.machine(),
                deployment_target=os.environ.get('MACOSX_DEPLOYMENT_TARGET', '13.0'),
                tools=[subprocess.check_output(command, text=True).strip() for command in commands])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['key', 'seal', 'verify'])
    parser.add_argument('--prefix', type=Path)
    parser.add_argument('--key')
    args = parser.parse_args()
    if args.action == 'key':
        repo = Path(__file__).resolve().parents[1]
        print(fingerprint(repo, INPUTS, toolchain_identity()))
    else:
        if not args.prefix or not args.key:
            parser.error('--prefix and --key are required')
        (seal if args.action == 'seal' else verify)(args.prefix, args.key)
        print(f'Native cache {args.action}: verified')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
