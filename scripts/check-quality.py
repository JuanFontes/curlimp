#!/usr/bin/env python3
"""Run fast source checks without building or downloading the native engine."""
import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def run(command, cwd=ROOT):
    print('+ ' + ' '.join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--format', action='store_true', help='Apply rustfmt and Prettier before linting')
    args = parser.parse_args()
    # Include new local files, but never ignored notes, generated output, or
    # imported engine sources and notices. CI checks the entire owned source set.
    paths = subprocess.check_output([
        'git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z',
    ], cwd=ROOT).decode('utf-8', errors='surrogateescape').split('\0')
    paths = sorted({p for p in paths if p and (ROOT / p).is_file()
                    and not p.startswith(('vendor/', 'licenses/'))})
    run(['cargo', 'fmt', '--all', *([] if args.format else ['--', '--check'])])
    prettier = [f'../{p}' for p in paths if Path(p).suffix in {
        '.md', '.yml', '.yaml', '.json', '.js', '.mjs', '.ts', '.css', '.astro',
    }]
    run(['node_modules/.bin/prettier', '--write' if args.format else '--check',
         '--ignore-path', '../.prettierignore', *prettier], cwd=ROOT / 'website')
    run(['ruff', 'check', *[p for p in paths if p.endswith('.py')]])
    run(['shellcheck', '--severity=warning', '--external-sources',
         '--source-path=SCRIPTDIR', *[p for p in paths if p.endswith('.sh')]])
    run(['actionlint', '-pyflakes='])


if __name__ == '__main__':
    main()
