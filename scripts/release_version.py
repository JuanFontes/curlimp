#!/usr/bin/env python3
"""Read the CLI release version from Cargo.toml (Python 3.11+)."""
from pathlib import Path
import tomllib


def release_version():
    with (Path(__file__).resolve().parents[1] / 'Cargo.toml').open('rb') as source:
        return tomllib.load(source)['package']['version']


if __name__ == '__main__':
    print(release_version())
