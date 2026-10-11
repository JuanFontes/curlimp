#!/usr/bin/env python3
"""Package an arm64 macOS CLI with its native engine, notices and provenance."""
import argparse
import gzip
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

from release_version import release_version

REPO = Path(__file__).resolve().parents[1]


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def dependencies(path):
    lines = run('otool', '-L', str(path)).splitlines()[1:]
    return [line.strip().split(' (compatibility version', 1)[0] for line in lines]


def rpaths(path):
    result = []
    lines = run('otool', '-l', str(path)).splitlines()
    for index, line in enumerate(lines):
        if line.strip() == 'cmd LC_RPATH':
            value = lines[index + 2].strip()
            if not value.startswith('path ') or ' (offset ' not in value:
                raise ValueError(f'Cannot parse Mach-O RPATH: {path.name}')
            result.append(value[5:].rsplit(' (offset ', 1)[0])
    return result


def audit(path, engine):
    if run('lipo', '-archs', str(path)).strip() != 'arm64':
        raise ValueError(f'Expected a thin arm64 Mach-O file: {path.name}')
    for dependency in dependencies(path):
        if dependency != engine and not dependency.startswith(('/usr/lib/', '/System/Library/')):
            raise ValueError(f'Unsupported runtime dependency in {path.name}: {dependency}')


def package(args):
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise ValueError('Packaging requires native macOS arm64 and Apple command-line tools')
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?', args.version):
        raise ValueError('Invalid release version')
    if not re.fullmatch(r'[0-9a-f]{40}', args.revision):
        raise ValueError('Source revision must be a full Git commit SHA')
    binary = args.binary.resolve(strict=True)
    prefix = args.native_prefix.resolve(strict=True)
    output = args.output.resolve()
    engines = [name for name in dependencies(binary)
               if re.fullmatch(r'@rpath/libcurl-impersonate(?:\.[0-9]+)*\.dylib', name)]
    if len(engines) != 1:
        raise ValueError('Expected exactly one @rpath libcurl-impersonate dependency')
    engine = engines[0]
    library = prefix / 'lib' / Path(engine).name
    if not library.is_file():
        raise ValueError(f'Missing native library: {library.name}')
    for artifact in (binary, library):
        audit(artifact, engine)
    for name in ['LICENSE', 'LICENSE_CURL', 'LICENSE_BORINGSSL', 'LICENSE_BROTLI',
                 'LICENSE_CARES', 'LICENSE_NGHTTP2', 'LICENSE_NGHTTP3', 'LICENSE_NGTCP2',
                 'LICENSE_ZLIB', 'LICENSE_ZSTD', 'engine-origin.md',
                 'engine-inputs.sha256', 'engine-build.txt']:
        if not (prefix / name).is_file():
            raise ValueError(f'Missing native notice or provenance: {name}')
    bundle_name = f'curlimp-{args.version}-macos-arm64'
    output.mkdir(parents=True, exist_ok=True)
    destination = output / f'{bundle_name}.tar.gz'
    if destination.exists():
        raise ValueError(f'Refusing to overwrite {destination}')
    with tempfile.TemporaryDirectory(prefix='.package-macos-', dir=output) as temporary:
        temporary = Path(temporary)
        bundle = temporary / bundle_name
        (bundle / 'lib').mkdir(parents=True)
        (bundle / 'licenses/native').mkdir(parents=True)
        (bundle / 'provenance').mkdir()
        (bundle / 'completions/zsh').mkdir(parents=True)
        shutil.copy2(REPO / 'completions/_curlimp', bundle / 'completions/zsh/_curlimp')
        cli = bundle / 'curlimp'
        dylib = bundle / 'lib' / library.name
        shutil.copy2(binary, cli)
        shutil.copy2(library, dylib)
        cli.chmod(0o755)
        for artifact in (cli, dylib):
            for path in rpaths(artifact):
                run('install_name_tool', '-delete_rpath', path, str(artifact))
        run('install_name_tool', '-add_rpath', '@executable_path/lib', str(cli))
        run('install_name_tool', '-id', engine, str(dylib))
        for artifact in (dylib, cli):
            run('codesign', '--force', '--sign', '-', '--timestamp=none', str(artifact))
            run('codesign', '--verify', '--strict', str(artifact))
            audit(artifact, engine)
        for path in sorted(prefix.glob('LICENSE*')):
            if path.is_file():
                shutil.copy2(path, bundle / 'licenses/native' / path.name)
        for name in ['engine-origin.md', 'engine-inputs.sha256', 'engine-build.txt']:
            shutil.copy2(prefix / name, bundle / 'provenance' / name)
        for name in ['LICENSE', 'NOTICE']:
            shutil.copy2(REPO / name, bundle / name)
        (bundle / 'release.json').write_text(json.dumps({
            'version': args.version, 'system': 'macos', 'architecture': 'arm64',
            'source_revision': args.revision, 'signature': 'ad-hoc', 'notarized': False,
        }, indent=2) + '\n')
        (bundle / 'README.md').write_text(f'''# curlimp {args.version} — macOS Apple Silicon

```sh
./curlimp --version
./curlimp -sS -I https://httpbin.org/status/200
./curlimp firefox147 -sS -I https://httpbin.org/status/301
./curlimp --json-output -sS -i https://httpbin.org/status/418
```

Browser impersonation defaults to chrome150. --impersonate PROFILE selects
another browser; --no-impersonate disables profiles. Explicit CLI selection wins
over CURL_IMPERSONATE, then the release default. Responses are decompressed
automatically while a profile is active. Use --no-compressed for encoded bytes.
--compressed remains supported; the last compression flag wins. Without a
profile (--no-impersonate), decoding is opt-in via --compressed.

Export files with --txt or --json-file in the current directory. Without -i/-I,
exports contain the body; -i adds headers and -I selects headers only. JSON
exports buffer at most 64 MiB; TXT streams. --json DATA still sends request JSON.
See https://juanfontes.github.io/curlimp/docs/response-exports/ for details.

Keep the entire folder together: the executable loads the engine from lib/.
No Docker, Homebrew, compiler or global engine installation is needed to run it.

Zsh users: initialize compinit, then source <(curlimp --completions zsh) with
curlimp on PATH. The optional menu style is:
zstyle ':completion:*:curlimp:*' menu yes select
The script is also included at completions/zsh/_curlimp. Tab filters any profile
prefix; executing a command requires an exact profile name before the URL.
Setup: https://juanfontes.github.io/curlimp/docs/completion/
This is a native arm64 package; it does not support Intel Macs or Linux.

This experimental macOS package is signed ad hoc and not notarized. macOS can block
internet downloads. After verifying SHA256SUMS and trusting the release, use
System Settings > Privacy & Security to approve this specific executable if
macOS offers Open Anyway. Rebuilding from source is another option.
The macOS runner and validation scope are documented
in the project README; a deployment target alone is not a compatibility test.

TLS verification is enabled. The engine uses Apple SecTrust and is configured
with /etc/ssl/cert.pem. --cacert, CURL_CA_BUNDLE, SSL_CERT_FILE and SSL_CERT_DIR
support custom trust settings. Profiles and supported options match the Linux
CLI; use --help and --list-profiles. This CLI accepts one URL and a subset of
curl flags. HTTP/3 and equivalence to real browser fingerprints are unverified.

Notices: LICENSE, NOTICE and licenses/native/. Engine inputs: provenance/.
Source revision: {args.revision}.
Usage: https://github.com/JuanFontes/curlimp#readme
''')

        def normalize(info):
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            info.mtime = 0
            info.pax_headers = {}
            return info

        staged = temporary / 'archive.tar.gz'
        with staged.open('wb') as raw:
            with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode='w', format=tarfile.PAX_FORMAT) as tar:
                    tar.add(bundle, arcname=bundle_name, filter=normalize)
        os.link(staged, destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--native-prefix', type=Path, required=True)
    parser.add_argument('--version', default=release_version(),
                        help='Archive version (default: package.version from Cargo.toml)')
    parser.add_argument('--revision', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(package(args))
    except (OSError, ValueError, subprocess.CalledProcessError, shutil.Error) as error:
        message = error.stderr if isinstance(error, subprocess.CalledProcessError) else str(error)
        print(f'package-macos: {message}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
