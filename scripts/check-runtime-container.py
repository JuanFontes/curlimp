#!/usr/bin/env python3
"""Exercise Docker DNS, trusted HTTPS, and a mounted JSON export as a nonroot user."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

URL = 'https://httpbin.org/status/200'


def check(image):
    name = 'curlimp-smoke-' + uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix='curlimp-container-') as directory:
        # The runtime deliberately has no passwd database; use a numeric nonroot UID.
        Path(directory).chmod(0o777)
        try:
            subprocess.run(['docker', 'run', '--rm', '--name', name, '--network', 'bridge',
                            '--user', '65532:65532', '--workdir', '/exports', '--mount', f'type=bind,src={directory},dst=/exports',
                            image, '-sS', '--fail', '--connect-timeout', '10', '--max-time', '30',
                            '--json-file', URL], check=True, timeout=45)
            files = list(Path(directory).glob('*.json'))
            if len(files) != 1:
                raise ValueError('Expected exactly one mounted JSON export')
            report = json.loads(files[0].read_text())
            if not isinstance(report, dict) or report.get('schema_version') != 1 \
                    or report.get('status') != 200 or report.get('exit_code') != 0:
                raise ValueError('Container HTTPS export has an unexpected schema, status or exit code')
            print('Container DNS/HTTPS and mounted nonroot JSON export passed')
        finally:
            # Also remove a still-running container after timeout or a failed check.
            subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=15)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='curlimp:local')
    args = parser.parse_args()
    try:
        check(args.image)
    except (subprocess.SubprocessError, OSError, ValueError) as error:
        print(f'Container runtime check failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
