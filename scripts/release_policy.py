#!/usr/bin/env python3
"""Shared stable-channel policy for release, Docker Hub, and Pages publishers."""
import argparse
from datetime import datetime
import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SEMVER = re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)'
                    r'(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?'
                    r'(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?')


def parse_version(version):
    """Return (numeric core tuple, is_prerelease); reject invalid SemVer."""
    match = SEMVER.fullmatch(version) if isinstance(version, str) else None
    if not match or (match[4] and any(part.isdigit() and len(part) > 1 and part[0] == '0'
                                     for part in match[4].split('.'))):
        raise ValueError(f'Invalid SemVer: {version!r}')
    return tuple(int(match[i]) for i in (1, 2, 3)), match[4] is not None


def fetch_json(url, token=None):
    """Return a JSON object, or None only for an explicit HTTP 404; fail otherwise."""
    headers = {'Accept': 'application/json', 'User-Agent': 'curlimp-publication-check'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    try:
        with urlopen(Request(url, headers=headers), timeout=30) as response:
            result = json.load(response)
    except HTTPError as error:
        error.close()
        if error.code == 404:
            return None
        raise
    if not isinstance(result, dict):
        raise ValueError('Expected an API JSON object')
    return result


def latest_stable_version(latest):
    """Validate GitHub /releases/latest metadata, retaining explicit absence."""
    if latest is None:
        return None
    if not isinstance(latest, dict) or latest.get('draft') is not False \
            or latest.get('prerelease') is not False \
            or not isinstance(latest.get('published_at'), str) or not latest['published_at'] \
            or not isinstance(latest.get('tag_name'), str) or not latest['tag_name'].startswith('v'):
        raise ValueError('Invalid current stable release metadata')
    published = datetime.fromisoformat(latest['published_at'].replace('Z', '+00:00'))
    if published.tzinfo is None:
        raise ValueError('Current stable publication timestamp lacks a timezone')
    version = latest['tag_name'][1:]
    _, prerelease = parse_version(version)
    if prerelease:
        raise ValueError('Current stable release is a prerelease')
    return version


def should_promote(version, latest):
    """Promote only a newer stable core; equal/build-only versions are immutable."""
    core, prerelease = parse_version(version)
    current = latest_stable_version(latest)
    return not prerelease and (current is None or core > parse_version(current)[0])


def is_latest_stable(version, latest):
    """Pages must match the exact published latest stable version, including metadata."""
    _, prerelease = parse_version(version)
    current = latest_stable_version(latest)
    return not prerelease and current == version


def fetch_latest(repository, token=None):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Invalid GitHub repository')
    return fetch_json(f'https://api.github.com/repos/{repository}/releases/latest', token)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--repository', default='JuanFontes/curlimp')
    args = parser.parse_args()
    # Call immediately before mutating stable channels; never cache this result across a build.
    latest = fetch_latest(args.repository, os.environ.get('GH_TOKEN'))
    promote = should_promote(args.version, latest)
    prerelease = parse_version(args.version)[1]
    values = f'promote={str(promote).lower()}\nprerelease={str(prerelease).lower()}\n'
    print(values, end='')
    if output := os.environ.get('GITHUB_OUTPUT'):
        with open(output, 'a') as destination:
            destination.write(values)


if __name__ == '__main__':
    try:
        main()
    except (URLError, ValueError, OSError) as error:
        print(f'Cannot determine stable promotion: {error}', file=sys.stderr)
        sys.exit(1)
