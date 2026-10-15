#!/usr/bin/env python3
"""Run the CLI inside the minimal filesystem for the existing HTTP/TLS tests.

Fixtures live under /runtime-rootfs/tmp. Translate their absolute paths before
entering the root so the client sees the same files as the external test server.
Test servers, Python, openssl, and reference curl stay outside the minimal root.
"""
import os
import sys

ROOT = '/runtime-rootfs'


def inside(argument):
    for prefix in (ROOT + '/', '@' + ROOT + '/'):
        if argument.startswith(prefix):
            return argument.replace(ROOT, '', 1)
    return argument


# Preserve a fixture cwd inside the root for automatically named export files.
cwd = os.getcwd()
arguments = [inside(arg) for arg in sys.argv[1:]]
# CA fixtures may also arrive through environment overrides, not just argv.
for name in ('CURL_CA_BUNDLE', 'SSL_CERT_FILE', 'SSL_CERT_DIR'):
    if name in os.environ:
        os.environ[name] = os.pathsep.join(inside(path) for path in os.environ[name].split(os.pathsep))
os.chroot(ROOT)
os.chdir(inside(cwd) if cwd.startswith(ROOT + '/') else '/work')
os.execv('/usr/local/bin/curlimp', ['curlimp', *arguments])
