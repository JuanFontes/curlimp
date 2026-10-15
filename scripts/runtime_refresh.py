#!/usr/bin/env python3
"""One weekly UTC runtime-package cache generation, with an urgent-refresh override."""
import argparse
from datetime import datetime, timezone
import re


def generation(override='', now=None):
    if override:
        if not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]{0,63}', override):
            raise ValueError('Refresh override must be 1-64 letters, digits, dots, underscores or hyphens')
        return override
    date = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isocalendar()
    return f'{date.year}-W{date.week:02d}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--override', default='')
    args = parser.parse_args()
    try:
        print(generation(args.override))
    except ValueError as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
