#!/usr/bin/env python3
"""Exercise native dependency tracking with real, offline Cargo builds."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform in ('darwin', 'linux'), 'requires macOS or Linux')
class BuildTrackingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='curlimp-build-tracking-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cc = shutil.which('cc')
        self.ar = shutil.which('ar')
        self.cargo = shutil.which('cargo')
        self.assertTrue(self.cc and self.ar and self.cargo, 'cc, ar and cargo are required')

    def run_command(self, *args, **kwargs):
        result = subprocess.run(args, text=True, capture_output=True, **kwargs)
        self.assertEqual(result.returncode, 0,
                         f'Command failed: {args}\n{result.stdout}{result.stderr}')
        return result.stdout.strip()

    def create_fixture(self, layout):
        package = self.root / layout
        package.mkdir()
        (package / 'src').mkdir()
        (package / 'native').mkdir()
        shutil.copyfile(REPO / 'build.rs', package / 'build.rs')
        (package / 'Cargo.toml').write_text('''[package]
name = "build-tracking-fixture"
version = "0.0.0"
edition = "2021"

[workspace]
''')
        (package / 'src/main.rs').write_text('''extern "C" {
    fn fixture_value() -> i32;
}
fn main() {
    println!("{}", unsafe { fixture_value() });
}
''')
        (package / 'native/bridge.c').write_text('''#include <curl/curl.h>
int fixture_value(void) {
    return FIXTURE_HEADER_VALUE + fixture_engine_value();
}
''')
        prefix = package / 'engine'
        headers = prefix / 'include/curl'
        headers.mkdir(parents=True)
        (headers / 'curl.h').write_text('''#include "detail/options.h"
int fixture_engine_value(void);
''')
        (headers / 'detail').mkdir()
        header = headers / 'detail/options.h'
        header.write_text('#define FIXTURE_HEADER_VALUE 1\n')
        provenance = prefix / 'engine-build.txt'
        provenance.write_text('engine_revision=first\n')
        libs = prefix / 'lib' if layout == 'lib' else prefix
        libs.mkdir(exist_ok=True)
        self.write_library(libs, version=1, value=10)
        env = dict(os.environ, CURL_IMPERSONATE_DIR=str(prefix),
                   CARGO_TARGET_DIR=str(package / 'target'), CC=self.cc, AR=self.ar)
        return package, header, provenance, libs, env

    def write_library(self, libs, version, value):
        if sys.platform == 'darwin':
            name = f'libcurl-impersonate.{version}.dylib'
            link = libs / 'libcurl-impersonate.dylib'
            flags = ['-dynamiclib', f'-Wl,-install_name,@rpath/{name}']
        else:
            name = f'libcurl-impersonate.so.{version}'
            link = libs / 'libcurl-impersonate.so'
            flags = ['-shared', f'-Wl,-soname,{name}']
        self.run_command(self.cc, '-fPIC', *flags, '-x', 'c', '-', '-o', str(libs / name),
                         input=f'int fixture_engine_value(void) {{ return {value}; }}\n')
        if link.is_symlink():
            previous = link.resolve()
            link.unlink()
            previous.unlink()
        link.symlink_to(name)

    def build(self, package, env):
        self.run_command(self.cargo, 'build', '--offline', '--quiet', cwd=package, env=env)
        return package / 'target/debug/build-tracking-fixture'

    def test_transitive_header_changes_recompile_bridge_at_same_prefix(self):
        for layout in ('lib', 'flat'):
            with self.subTest(layout=layout):
                package, header, _, _, env = self.create_fixture(layout)
                binary = self.build(package, env)
                self.assertEqual(self.run_command(str(binary)), '11')
                original_mtime = binary.stat().st_mtime_ns
                self.build(package, env)
                self.assertEqual(binary.stat().st_mtime_ns, original_mtime,
                                 'unchanged native inputs must not trigger a rebuild')
                header.write_text('#define FIXTURE_HEADER_VALUE 2\n')
                self.build(package, env)
                self.assertEqual(self.run_command(str(binary)), '12',
                                 'changing a transitive engine header must recompile the bridge')

    def test_replacing_native_library_relinks_at_same_prefix(self):
        for layout in ('lib', 'flat'):
            with self.subTest(layout=layout):
                package, _, _, libs, env = self.create_fixture(layout)
                binary = self.build(package, env)
                self.assertEqual(self.run_command(str(binary)), '11')
                self.write_library(libs, version=2, value=20)
                self.build(package, env)
                self.assertEqual(self.run_command(str(binary)), '21')

    def test_engine_provenance_change_rebuilds_at_same_prefix(self):
        for layout in ('lib', 'flat'):
            with self.subTest(layout=layout):
                package, _, provenance, _, env = self.create_fixture(layout)
                binary = self.build(package, env)
                original_mtime = binary.stat().st_mtime_ns
                provenance.write_text('engine_revision=second\n')
                self.build(package, env)
                self.assertGreater(binary.stat().st_mtime_ns, original_mtime,
                                   'changing engine provenance must invalidate the native build')
                self.assertEqual(self.run_command(str(binary)), '11')


if __name__ == '__main__':
    unittest.main()
