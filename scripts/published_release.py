#!/usr/bin/env python3
"""Allow production documentation only after its downloads are published."""
import argparse
import os
import re
import sys
from urllib.error import URLError

from release_version import release_version
from release_policy import fetch_json, fetch_latest, is_latest_stable


def eligible(version, release, image, latest):
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        return False, 'Only stable versions can update production documentation'
    if not release or release.get('tag_name') != f'v{version}' or release.get('draft') \
            or release.get('prerelease') or not release.get('published_at'):
        return False, f'Stable release v{version} is not published'
    required = {'SHA256SUMS'} | {
        f'curlimp-{version}-{platform}.tar.gz'
        for platform in ['linux-amd64', 'linux-arm64', 'macos-arm64']}
    uploaded = {asset['name'] for asset in release.get('assets', [])
                if asset.get('state') == 'uploaded' and asset.get('size', 0) > 0}
    if required - uploaded:
        return False, 'Missing release assets: ' + ', '.join(sorted(required - uploaded))
    if not image or image.get('name') != version or image.get('tag_status') != 'active':
        return False, f'Docker tag {version} is not published'
    platforms = {(entry.get('os'), entry.get('architecture')) for entry in image.get('images', [])
                 if entry.get('status') == 'active'
                 and re.fullmatch(r'sha256:[0-9a-f]{64}', entry.get('digest', ''))}
    if not {('linux', 'amd64'), ('linux', 'arm64')} <= platforms:
        return False, 'Docker tag must include linux/amd64 and linux/arm64'
    if not is_latest_stable(version, latest):
        return False, f'v{version} is not the current latest stable release'
    return True, f'All downloads for latest stable v{version} are published'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default=release_version())
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9A-Za-z.+-]+', args.version):
        parser.error('Invalid release version')
    release = fetch_json(f'https://api.github.com/repos/JuanFontes/curlimp/releases/tags/v{args.version}',
                         os.environ.get('GH_TOKEN'))
    # Never send the GitHub token to Docker Hub.
    image = fetch_json(f'https://hub.docker.com/v2/repositories/juanfontes/curlimp/tags/{args.version}/') \
        if release and not release.get('draft') and not release.get('prerelease') else None
    latest = fetch_latest('JuanFontes/curlimp', os.environ.get('GH_TOKEN'))
    published, reason = eligible(args.version, release, image, latest)
    print(reason)
    if output := os.environ.get('GITHUB_OUTPUT'):
        with open(output, 'a') as destination:
            destination.write(f'published={str(published).lower()}\n')


if __name__ == '__main__':
    try:
        main()
    except (URLError, ValueError, OSError) as error:
        print(f'Cannot verify publication: {error}', file=sys.stderr)
        sys.exit(1)
