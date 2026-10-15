#!/usr/bin/env python3
"""Build the pinned, patched ngtcp2 core with ASan and check qlog output.

Requires CMake, a C compiler with AddressSanitizer, patch, and curl. Only this
throwaway test build is instrumented; release libraries remain unchanged.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, help='Reuse an archive after verifying its pinned hash')
    args = parser.parse_args()
    cmake = (ROOT / 'vendor/engine/CMakeLists.txt').read_text()
    version = re.search(r'^set\(NGTCP2_VERSION "([\d.]+)"\)', cmake, re.M)[1]
    digest = re.search(r'^set\(NGTCP2_URL_HASH "SHA256=([a-f0-9]{64})"\)', cmake, re.M)[1]
    with tempfile.TemporaryDirectory(prefix='curlimp-native-security-') as temp:
        temp = Path(temp)
        archive = args.archive or temp / 'ngtcp2.tar.bz2'
        if not args.archive:
            subprocess.run(['sh', str(ROOT / 'scripts/fetch-verified.sh'),
                            f'https://github.com/ngtcp2/ngtcp2/releases/download/v{version}/ngtcp2-{version}.tar.bz2',
                            digest, str(archive)], check=True)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
            raise SystemExit('ngtcp2 source hash mismatch')
        with tarfile.open(archive) as source:
            source.extractall(temp, filter='data')
        source = temp / f'ngtcp2-{version}'
        build = temp / 'build'
        subprocess.run(['patch', '-p1', '-F', '0', '-i',
                        str(ROOT / 'vendor/engine/patches/ngtcp2.patch')], cwd=source, check=True)
        flags = ['-fsanitize=address', '-fno-omit-frame-pointer', '-O1', '-g']
        subprocess.run(['cmake', '-S', str(source), '-B', str(build),
                        '-DENABLE_LIB_ONLY=ON', '-DENABLE_SHARED_LIB=OFF',
                        '-DENABLE_STATIC_LIB=ON', '-DBUILD_TESTING=OFF',
                        '-DENABLE_OPENSSL=OFF', '-DENABLE_GNUTLS=OFF',
                        '-DENABLE_BORINGSSL=OFF', '-DENABLE_PICOTLS=OFF',
                        '-DENABLE_WOLFSSL=OFF', '-DCMAKE_C_FLAGS=' + ' '.join(flags)], check=True)
        subprocess.run(['cmake', '--build', str(build), '--parallel', '2'], check=True)
        binary = temp / 'qlog-test'
        compiler = shlex.split(os.environ.get('CC', 'cc'))
        includes = [source / 'lib', source / 'lib/includes', build, build / 'lib/includes']
        subprocess.run([*compiler, *flags, '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-DHAVE_CONFIG_H', '-DNGTCP2_STATICLIB',
                        *[f'-I{path}' for path in includes], str(ROOT / 'tests/ngtcp2_qlog.c'),
                        str(build / 'lib/libngtcp2.a'), '-o', str(binary)], check=True)
        result = subprocess.run([str(binary)], capture_output=True,
                                env={**os.environ, 'ASAN_OPTIONS': 'halt_on_error=1:abort_on_error=0'})
        if result.returncode:
            print(result.stderr.decode('utf-8', errors='replace'))
            result.check_returncode()
        records = result.stdout.split(b'\x1e')[1:]
        assert len(records) == 8, 'Expected exactly eight qlog events (disabled qlog emits none)'
        assert max(map(len, records)) > 1024, 'Regression must exceed the original stack buffer'
        for index, raw in enumerate(records):
            event = json.loads(raw)
            data = event['data']
            assert event['name'] == 'transport:parameters_set'
            assert data['owner'] == ('remote' if index % 2 else 'local')
            assert data['initial_source_connection_id'] == 'ab' * 20
            assert data['initial_max_data'] == 4611686018427387903
            assert data['max_datagram_frame_size'] == 4611686018427387903
            assert ('original_destination_connection_id' in data) == (index % 4 in (1, 2))
            assert ('preferred_address' in data) == (index >= 4)
            if index >= 4:
                assert data['preferred_address']['connection_id'] == 'ab' * 20
                assert data['preferred_address']['stateless_reset_token']['data'] == 'ef' * 16
                assert data['stateless_reset_token']['data'] == 'cd' * 16
                assert data['preferred_address']['port_v6'] == 65535
        print(f'ngtcp2 qlog ASan regression passed: {len(records)} events, largest {max(map(len, records))} bytes')


if __name__ == '__main__':
    main()
