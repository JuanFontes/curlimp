#!/usr/bin/env python3
"""Create a relocatable Linux bundle from a complete runtime-artifacts export."""
import argparse
import gzip
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tarfile
import tempfile

from release_version import release_version

ARCHES = {
    'amd64': (62, 'x86_64', 'lib64/ld-linux-x86-64.so.2', 'lib/x86_64-linux-gnu'),
    'arm64': (183, 'aarch64', 'lib/ld-linux-aarch64.so.1', 'lib/aarch64-linux-gnu'),
}


def check_elf(path, machine):
    with path.open('rb') as source:
        header = source.read(20)
    if (header[:6] != b'\x7fELF\x02\x01' or len(header) < 20 or
            int.from_bytes(header[18:20], 'little') != machine):
        raise ValueError(f'ELF architecture mismatch: {path.name}')


def prepare_runtime(root, machine, loader, libdir):
    paths = sorted(root.rglob('*'))
    # Convert rootfs-absolute links before resolving any chains. The archive
    # must remain self-contained after extraction, including certificate links.
    for path in paths:
        if path.is_symlink():
            target = path.readlink()
            if target.is_absolute():
                path.unlink()
                path.symlink_to(os.path.relpath(root / str(target).lstrip('/'), path.parent))
        elif not (path.is_dir() or path.is_file()):
            raise ValueError(f'Unsupported runtime file type: {path.relative_to(root)}')
    for path in paths:
        if path.is_symlink():
            try:
                target = path.resolve(strict=True)
                target.relative_to(root)
            except (OSError, RuntimeError, ValueError) as error:
                raise ValueError(f'Invalid runtime link: {path.relative_to(root)}') from error

    required = [
        'usr/local/bin/curlimp', loader, f'{libdir}/libc.so.6',
        'opt/native/lib/libcurl-impersonate.so', 'etc/ssl/certs/ca-certificates.crt',
        'usr/share/licenses/curlimp/LICENSE',
        'usr/share/licenses/curlimp/NOTICE', 'usr/share/doc/libc6/copyright',
        'opt/native/engine-build.txt', 'opt/native/runtime-packages.txt',
        'opt/native/runtime-libraries.txt',
    ]
    for name in required:
        if not (root / name).is_file():
            raise ValueError(f'Missing runtime file: {name}')
    notices = root / 'usr/share/licenses/curlimp/native'
    if not notices.is_dir() or not any(p.is_file() for p in notices.iterdir()):
        raise ValueError('Missing native license notices')
    # The source packager records the complete ldd closure. Check every
    # resolved dependency so the host cannot hide an incomplete export.
    dependencies = []
    for line in (root / 'opt/native/runtime-libraries.txt').read_text().splitlines():
        fields = line.split()
        if not fields or fields[0].startswith(('linux-vdso.', 'linux-gate.')):
            continue
        if len(fields) >= 3 and fields[1] == '=>':
            name = fields[2]
        else:
            name = fields[0]
        if not name.startswith('/') or '..' in Path(name).parts:
            raise ValueError(f'Invalid dependency inventory entry: {line}')
        dependency = root / name.lstrip('/')
        if not dependency.is_file():
            raise ValueError(f'Missing runtime dependency: {name}')
        check_elf(dependency, machine)
        dependencies.append(name)
    if not dependencies:
        raise ValueError('Empty runtime dependency inventory')
    for name in ['usr/local/bin/curlimp', loader,
                 'opt/native/lib/libcurl-impersonate.so', f'{libdir}/libc.so.6']:
        check_elf(root / name, machine)


def package(args):
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?', args.version):
        raise ValueError('Invalid release version')
    if not re.fullmatch(r'[0-9a-f]{40}', args.revision):
        raise ValueError('Source revision must be a full Git commit SHA')
    root = args.rootfs.resolve(strict=True)
    output = args.output.resolve()
    if output == root or root in output.parents:
        raise ValueError('Output must be outside the input rootfs')
    machine, cpu, loader, libdir = ARCHES[args.arch]
    # Check the CLI first so a mismatched architecture gets a useful error.
    check_elf(root / 'usr/local/bin/curlimp', machine)
    name = f'curlimp-{args.version}-linux-{args.arch}'
    output.mkdir(parents=True, exist_ok=True)
    destination = output / f'{name}.tar.gz'
    if destination.exists():
        raise ValueError(f'Refusing to overwrite {destination}')
    with tempfile.TemporaryDirectory(prefix='.package-', dir=output) as temporary:
        temporary = Path(temporary)
        bundle = temporary / name
        runtime = bundle / 'runtime'
        shutil.copytree(root, runtime, symlinks=True)
        prepare_runtime(runtime, machine, loader, libdir)
        template = Path(__file__).with_name('release-launcher.sh').read_text()
        for token, value in {'MACHINE': cpu, 'ARCH': args.arch, 'LOADER': loader, 'LIBDIR': libdir}.items():
            template = template.replace(f'@{token}@', value)
        launcher = bundle / 'curlimp'
        launcher.write_text(template)
        launcher.chmod(0o755)
        (bundle / 'completions/zsh').mkdir(parents=True)
        shutil.copy2(Path(__file__).resolve().parents[1] / 'completions/_curlimp',
                     bundle / 'completions/zsh/_curlimp')
        (bundle / 'release.json').write_text(json.dumps({
            'version': args.version, 'architecture': args.arch, 'system': 'linux',
            'source_revision': args.revision,
        }, indent=2) + '\n')
        (bundle / 'README.md').write_text(f'''# curlimp {args.version} — Linux {args.arch}

Run `./curlimp --version` or:

```sh
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
exports use private temporary storage with a 64 MiB limit per response; TXT streams. --json DATA still sends request JSON.
See https://juanfontes.github.io/curlimp/docs/response-exports/ for details.

Keep this entire directory together. The executable launcher uses the bundled
engine, glibc loader and shared libraries. No Docker, compiler or root access is
required. A Linux shell and standard utilities (uname, dirname, readlink -f) are
required. A symlink to the launcher can be placed in a directory on your PATH.
Paths with spaces work; package paths containing a colon or semicolon are unsupported.
This is not a single static executable and does not promise all Linux systems.
Native CI validates Ubuntu 24.04 on amd64 and arm64; macOS and Windows are not
supported by these bundles.

Bundled CA certificates are the default. Set CURL_CA_BUNDLE, SSL_CERT_FILE or
SSL_CERT_DIR, or use --cacert, to supply custom trust settings. System network
configuration (including DNS and proxies) still applies. Refresh the package
when its libraries or certificates need updating.

This CLI supports multiple URLs with one common request configuration and a
subset of curl flags. Transfers run sequentially unless --parallel is enabled.
Pair -o destinations with URLs by position, or use --json-output for an ordered
array. JSON needs writable temporary storage. Use --help and --list-profiles. Profiles do not establish equivalence to real browsers.
Full usage and limitations: https://github.com/JuanFontes/curlimp#readme

Zsh users: initialize compinit, then source <(curlimp --completions zsh) with
curlimp on PATH. The optional menu style is:
zstyle ':completion:*:curlimp:*' menu yes select
The script is also included at completions/zsh/_curlimp. Tab filters any profile
prefix; executing a command requires an exact profile name before the URL.
Setup: https://juanfontes.github.io/curlimp/docs/completion/

Project and native notices: runtime/usr/share/licenses/curlimp/.
System library notices: runtime/usr/share/doc/ and runtime/usr/share/common-licenses/.
Engine provenance: runtime/opt/native/. Source revision: {args.revision}.
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
                    tar.add(bundle, arcname=name, filter=normalize)
        # Publish only a complete archive, without replacing an existing file.
        os.link(staged, destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rootfs', type=Path, required=True)
    parser.add_argument('--arch', choices=ARCHES, required=True)
    parser.add_argument('--version', default=release_version(),
                        help='Archive version (default: package.version from Cargo.toml)')
    parser.add_argument('--revision', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(package(args))
    except (OSError, ValueError, shutil.Error) as error:
        print(f'package-release: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
