#!/usr/bin/env python3
"""Reject a root Dockerfile whose default runtime differs from the release version."""
import argparse
from pathlib import Path
import re
import sys

from release_version import release_version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default=release_version())
    parser.add_argument('--dockerfile', type=Path, default=Path(__file__).resolve().parents[1] / 'Dockerfile')
    args = parser.parse_args()
    match = re.search(r'^ARG RUNTIME_IMAGE=juanfontes/curlimp:([^\s@]+)(?:@sha256:[0-9a-f]{64})?$',
                      args.dockerfile.read_text(), re.MULTILINE)
    if not match or match[1] != args.version:
        print(f'Dockerfile default runtime must match release {args.version}', file=sys.stderr)
        return 1
    print(f'Dockerfile runtime matches release {args.version}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
