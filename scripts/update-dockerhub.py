#!/usr/bin/env python3
"""Publish the repository's Docker Hub overview and short description."""
import argparse
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request

BASE = 'https://hub.docker.com'
REPOSITORY = '/v2/repositories/juanfontes/curlimp/'


def request(path, method='GET', data=None, token=None):
    headers = {'Accept': 'application/json'}
    if data is not None:
        headers['Content-Type'] = 'application/json'
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(BASE + path, method=method, headers=headers,
                                 data=json.dumps(data).encode() if data is not None else None)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Validate content and metadata access without writing')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    content = (root / 'docker/README.md').read_text()
    description = (root / 'docker/description.txt').read_text().strip()
    if not description or len(description) > 100:
        raise ValueError('Docker Hub description must contain 1–100 characters')
    before = request(REPOSITORY)
    if before['namespace'] != 'juanfontes' or before['name'] != 'curlimp':
        raise ValueError('Unexpected Docker Hub repository')
    token = request('/v2/auth/token', 'POST', {
        'identifier': os.environ['DOCKERHUB_USERNAME'],
        'secret': os.environ['DOCKERHUB_TOKEN'],
    })['access_token']
    access = request(REPOSITORY, token=token)
    if not access.get('permissions', {}).get('admin'):
        raise ValueError('Repository administration access is required to update Docker Hub text')
    if args.check:
        print('Docker Hub content and metadata access verified; nothing changed.')
        return
    request(REPOSITORY, 'PATCH', {'full_description': content, 'description': description}, token)
    after = request(REPOSITORY)
    if after.get('full_description') != content or after.get('description') != description:
        raise ValueError('Docker Hub read-back does not match repository documentation')
    if after['is_private'] != before['is_private']:
        raise ValueError('Unexpected visibility change')
    print('Docker Hub overview and description updated and verified.')


if __name__ == '__main__':
    try:
        main()
    except urllib.error.HTTPError as error:
        print(f'Docker Hub returned HTTP {error.code}', file=sys.stderr)
        sys.exit(1)
    except (ValueError, KeyError, OSError) as error:
        print(f'Docker Hub update failed: {error}', file=sys.stderr)
        sys.exit(1)
