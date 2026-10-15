#!/usr/bin/env python3
"""Runtime refresh generation and observable container smoke contract."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import runtime_refresh


class RuntimeDistribution(unittest.TestCase):
    def test_weekly_utc_generation_and_manual_override(self):
        self.assertEqual(runtime_refresh.generation('', datetime(2026, 1, 1, tzinfo=timezone.utc)), '2026-W01')
        self.assertEqual(runtime_refresh.generation('', datetime(2026, 10, 14, tzinfo=timezone.utc)), '2026-W42')
        self.assertEqual(runtime_refresh.generation('security-2026-10-14'), 'security-2026-10-14')
        for invalid in ['spaces here', 'line\nbreak', 'a' * 65, '../bad']:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                runtime_refresh.generation(invalid)

    def test_container_smoke_checks_mounted_json_and_cleans_failed_container(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = root / 'docker'
            # Emulate only Docker's external boundary: the script still constructs
            # the invocation, validates the exported file, and performs cleanup.
            fake.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
with open(os.environ['DOCKER_LOG'], 'a') as output:
    output.write(json.dumps(sys.argv[1:]) + '\\n')
if sys.argv[1] == 'run':
    if os.environ.get('DOCKER_FAIL'): sys.exit(7)
    if sys.argv[sys.argv.index('--json-file') + 1] != 'https://httpbin.org/status/200': sys.exit(8)
    mount = sys.argv[sys.argv.index('--mount') + 1]
    source = mount.split('src=', 1)[1].split(',')[0]
    pathlib.Path(source, 'response.json').write_text(os.environ['REPORT_JSON'])
''')
            fake.chmod(0o755)
            log = root / 'commands.jsonl'
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ['PATH'],
                       DOCKER_LOG=str(log), REPORT_JSON=json.dumps({'schema_version': 1, 'status': 200, 'exit_code': 0}))
            for report, failure, expected in [(env['REPORT_JSON'], '', 0), ('not json', '', 1),
                                               ('{}', '', 1), ('[]', '', 1), (env['REPORT_JSON'], 'yes', 1)]:
                log.unlink(missing_ok=True)
                result = subprocess.run([sys.executable, str(ROOT / 'scripts/check-runtime-container.py'),
                                         '--image', 'curlimp:test'], env=dict(env, REPORT_JSON=report,
                                                                          DOCKER_FAIL=failure), capture_output=True)
                self.assertEqual(result.returncode, expected, result.stderr)
                commands = [json.loads(line) for line in log.read_text().splitlines()]
                run = commands[0]
                self.assertIn('--user', run)
                self.assertEqual(run[run.index('--user') + 1], '65532:65532')
                self.assertEqual(run[run.index('--network') + 1], 'bridge')
                self.assertIn('--max-time', run)
                self.assertIn('--json-file', run)
                self.assertEqual(run[run.index('--workdir') + 1], '/exports')
                self.assertEqual(commands[-1][:2], ['rm', '-f'])
                self.assertEqual(commands[-1][2], run[run.index('--name') + 1])


if __name__ == '__main__':
    unittest.main()
