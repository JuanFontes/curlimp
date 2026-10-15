#!/usr/bin/env python3
"""Read-only native dependency inventory and upstream security triage.

Release discovery covers every native pin. Security feeds cover curl's official
feed and published GitHub advisories in the native projects' repositories. Empty
feeds do not establish safety; libidn2 and Git-only applicability need manual review. Version updates
are triage candidates, never instructions to upgrade a fingerprint-sensitive pin.
Curl applicability uses the official feed's explicit affected-version lists,
including all affected entries; ranges are recorded but are not inferred. Missing
or empty lists fail as unknown. Git-only advisories cannot establish applicability
of this patched source tree. GitHub ranges support numeric comparators, exact
versions, and inclusive hyphen ranges. Unknown input fails closed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPOS = {'brotli': 'google/brotli', 'boringssl': 'google/boringssl',
         'nghttp2': 'nghttp2/nghttp2', 'ngtcp2': 'ngtcp2/ngtcp2',
         'nghttp3': 'ngtcp2/nghttp3', 'zlib': 'madler/zlib',
         'zstd': 'facebook/zstd', 'cares': 'c-ares/c-ares',
         'curl': 'curl/curl', 'libpsl': 'rockdaboot/libpsl'}
BACKPORT_ID = 'GHSA-6933-cjhr-5qg6'
BACKPORT_COMMIT = '5c7df8fa815ac1004d9ecb9d1f7595c4d37f46e1'
BACKPORT_SHA256 = '615c6fa8389de372f4dcdd943ae18a7e29c0757e5fbe0445759989c6a07728d3'
# Reviewed dispositions are bound to source identity and the exact evidence
# reviewed in SECURITY.md. They are not general patched-version heuristics.
REVIEWED_ADVISORIES = {
    ('ngtcp2', 'GHSA-f523-465f-8c8f'): {
        'pin': '1.20.0',
        'source_sha256': '871ec97ad86803cf312901b0c393b0ee70163e25a87c9b2894d1234341ce4e97',
        'ranges': ['<= 1.22.0'], 'patched_versions': ['1.22.1'],
        'files': {
            'patches/ngtcp2.patch': '8d5faf52a036587b81606fe0607743d9b4d167e2c50d6f2b91085a93f04bb35b',
            'CMakeLists.txt': 'c6004653cebc2cde5aa058eb767ebc4a1ae3afed9320b6354e849d26a6734d0c',
        },
        'resolution': {
            'status': 'backported',
            'backport_commit': '708a7640c1f48fb8ffb540c4b8ea5b4c1dfb8ee5',
            'review_note': 'Official qlog buffer fix backported to the pinned ngtcp2 source; ASan regression tested.',
            'review_sources': ['https://github.com/ngtcp2/ngtcp2/commit/708a7640c1f48fb8ffb540c4b8ea5b4c1dfb8ee5'],
        },
    },
    ('cares', 'GHSA-6wfj-rwm7-3542'): {
        'pin': '1.34.8',
        'source_sha256': 'c222b6d681096f9444d2c4863d2c1174019e27cacca0a4a5c114d36dd7d7bf78',
        'ranges': ['> 1.32.3'], 'patched_versions': ['1.34.7'],
        # Bind the unpatched c-ares build recipe too: a future local patch
        # requires a new review, even when the archive itself stays the same.
        'files': {'CMakeLists.txt': 'c6004653cebc2cde5aa058eb767ebc4a1ae3afed9320b6354e849d26a6734d0c'},
        'resolution': {
            'status': 'fixed-in-pinned-source',
            'review_note': 'Conflicting upstream range reviewed: the exact c-ares 1.34.8 archive retains the 1.34.7 fix.',
            'review_sources': [
                'https://github.com/c-ares/c-ares/commit/d823199b688052dcdc1646f2ab4cb8c16b1c644a',
                'https://github.com/c-ares/c-ares/compare/d823199b688052dcdc1646f2ab4cb8c16b1c644a...v1.34.8',
                'https://c-ares.org/changelog.html',
            ],
        },
    },
}


class SourceError(Exception):
    pass


def request(url, token):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.username or parsed.password:
        raise ValueError('Only credential-free HTTPS source URLs are allowed')
    headers = {'User-Agent': 'curlimp-dependency-report', 'Accept': 'application/json'}
    if parsed.hostname == 'api.github.com' and token:
        headers['Authorization'] = f'Bearer {token}'
    return urllib.request.Request(url, headers=headers)


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != 'https':
            raise SourceError('Insecure source redirect')
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected and urllib.parse.urlsplit(newurl).hostname != 'api.github.com':
            redirected.remove_header('Authorization')
        return redirected


OPENER = urllib.request.build_opener(SafeRedirect())


def fetch(url, token):
    try:
        with OPENER.open(request(url, token), timeout=30) as response:
            return response.read().decode('utf-8')
    except urllib.error.HTTPError as error:
        raise SourceError(f'HTTP {error.code}') from None
    except (urllib.error.URLError, OSError):
        # Do not print exception text or request headers (may contain secrets).
        raise SourceError('network failure') from None
    except UnicodeError:
        raise SourceError('parse failure: expected UTF-8') from None


def fetch_json(url, token):
    try:
        return json.loads(fetch(url, token))
    except json.JSONDecodeError:
        raise SourceError('parse failure: expected JSON') from None


def version(value):
    value = value.removeprefix('curl-').removeprefix('v').replace('_', '.')
    if not re.fullmatch(r'\d+(?:\.\d+)+', value):
        raise ValueError('Unsupported version format')
    return tuple(map(int, value.split('.')))


def inventory():
    source = (ROOT / 'vendor/engine/CMakeLists.txt').read_text()
    pins = {name.lower(): value for name, value in re.findall(
        r'^set\((\w+)_(?:VERSION|COMMIT) "([^"]+)"\)', source, re.M)
        if name.lower() in REPOS}
    lock = (ROOT / 'engine.lock').read_text()
    hashes = {name.lower(): digest for name, digest in re.findall(
        r'^set\((\w+)_URL_HASH "SHA256=([a-f0-9]{64})"\)', source, re.M)}
    pins['libidn2'] = re.search(r'^LIBIDN2_VERSION=(.+)$', lock, re.M)[1]
    hashes['libidn2'] = re.search(r'^LIBIDN2_SOURCE_SHA256=([a-f0-9]{64})$', lock, re.M)[1]
    if set(pins) != set(REPOS) | {'libidn2'}:
        raise ValueError('Native pin inventory is incomplete')
    if not set(pins) <= set(hashes):
        raise ValueError('Native source hash inventory is incomplete')
    return {name: {'pin': pin.removeprefix('curl-').replace('_', '.'),
                   'source_sha256': hashes[name],
                   'policy': 'hold for legacy H2 priority support' if name == 'nghttp2'
                             else 'manual review; source/hash/patch/build validation required'}
            for name, pin in pins.items()}


def curl_affected(advisory, pin):
    if not isinstance(advisory, dict):
        raise ValueError('Expected curl advisory object')
    entries = advisory.get('affected')
    if not isinstance(entries, list) or not entries:
        raise ValueError('Curl advisory has no affected entries')
    affected = False
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('Expected curl affected-entry object')
        versions = entry.get('versions')
        if not isinstance(versions, list) or not versions or not all(isinstance(v, str) for v in versions):
            raise ValueError('Curl advisory lacks explicit affected versions; applicability unknown')
        affected |= pin in versions
    return affected


def in_range(pin, expression):
    if not isinstance(expression, str) or not expression.strip():
        raise ValueError('Missing vulnerable version range')
    current = version(pin)
    if len(current) != 3:
        raise ValueError('Advisory comparison requires a three-component numeric pin')
    # Partial versions have ecosystem-specific wildcard semantics. Do not turn
    # an unsupported partial upper bound into a false exclusion of a full pin.
    numeric = r'\d+\.\d+\.\d+'
    hyphen = re.fullmatch(rf'\s*v?({numeric})\s+-\s+v?({numeric})\s*', expression)
    if hyphen:
        lower, upper = version(hyphen[1]), version(hyphen[2])
        if lower > upper:
            raise ValueError('Reversed vulnerable version range')
        return lower <= current <= upper
    matches = []
    for part in expression.split(','):
        match = re.fullmatch(rf'\s*(<=|>=|<|>|=)?\s*v?({numeric})\s*', part)
        if not match:
            raise ValueError('Unsupported vulnerable version range')
        op, bound = match[1] or '=', version(match[2])
        matches.append({'<': current < bound, '<=': current <= bound,
                        '>': current > bound, '>=': current >= bound, '=': current == bound}[op])
    return all(matches)


def backport_present():
    patch = ROOT / 'vendor/engine/patches/nghttp2.patch'
    return patch.is_file() and hashlib.sha256(patch.read_bytes()).hexdigest() == BACKPORT_SHA256


def nghttp2_status(identifier, affected):
    if not affected:
        return 'not-affected-by-range'
    if identifier == BACKPORT_ID and backport_present():
        return 'backported'
    return 'needs-triage'


def reviewed_resolution(name, entry, finding):
    review = REVIEWED_ADVISORIES.get((name, finding['id']))
    if not review or any(entry.get(key) != review[key] for key in ('pin', 'source_sha256')):
        return {}
    if any(finding.get(key) != review[key] for key in ('ranges', 'patched_versions')):
        return {}
    for path, digest in review['files'].items():
        file = ROOT / 'vendor/engine' / path
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != digest:
            return {}
    return review['resolution']


def releases(data, token):
    errors = []
    for name, entry in data.items():
        if name == 'libidn2':
            url = 'https://ftp.gnu.org/gnu/libidn/'
        else:
            url = f'https://api.github.com/repos/{REPOS[name]}/' + (
                'commits/HEAD' if name == 'boringssl' else 'releases/latest')
        entry['release_source'] = url
        try:
            if name == 'libidn2':
                tags = re.findall(r'libidn2-(\d+\.\d+\.\d+)\.tar\.gz', fetch(url, token))
                if not tags:
                    raise ValueError('No libidn2 versions in upstream archive index')
                latest = max(tags, key=version)
            else:
                release = fetch_json(url, token)
                latest = release['sha' if name == 'boringssl' else 'tag_name']
                if not isinstance(latest, str) or not latest:
                    raise ValueError('Missing release identifier')
            entry['upstream'] = latest
            entry['release_status'] = ('same-commit' if latest == entry['pin'] else 'new-commit-review') \
                if name == 'boringssl' else ('new-release-review' if version(latest) > version(entry['pin'])
                                            else 'no-newer-release')
        except (SourceError, ValueError, KeyError, TypeError) as error:
            entry['release_status'] = 'unknown'
            entry['error'] = str(error)
            errors.append(f'{name}: {error}')
    return errors


def advisories(data, token):
    findings, errors = [], []
    curl_url = 'https://curl.se/docs/vuln.json'
    try:
        feed = fetch_json(curl_url, token)
        if not isinstance(feed, list) or not feed:
            raise ValueError('Expected nonempty curl OSV advisory array')
        for item in feed:
            identifier = item['id']
            if not isinstance(identifier, str) or not identifier:
                raise ValueError('Missing curl advisory ID')
            affected = curl_affected(item, data['curl']['pin'])
            if affected:
                findings.append({'dependency': 'curl', 'id': identifier,
                                 'status': 'needs-triage', 'source': curl_url})
        data['curl']['security_status'] = 'checked explicit affected-version lists'
        data['curl']['security_source'] = curl_url
        data['curl']['advisory_count'] = len(feed)
    except (SourceError, ValueError, KeyError, TypeError) as error:
        data['curl']['security_status'] = 'unknown'
        errors.append(f'curl advisories: {error}')
    for name, entry in data.items():
        if name == 'curl':
            continue
        if name == 'libidn2':
            entry['security_status'] = 'manual-review: no integrated advisory feed'
            entry['security_source'] = 'https://www.gnu.org/software/libidn/'
            continue
        source_findings, source_errors = github_advisories(name, entry, token)
        findings.extend(source_findings)
        errors.extend(source_errors)
    return findings, errors


def github_advisories(name, entry, token):
    findings, errors = [], []
    base = f'https://api.github.com/repos/{REPOS[name]}/security-advisories'
    entry['security_source'] = base
    count = 0
    try:
        for page in range(1, 101):
            feed = fetch_json(f'{base}?per_page=100&page={page}', token)
            if not isinstance(feed, list):
                raise ValueError('Expected upstream advisory array')
            for item in feed:
                if not isinstance(item, dict):
                    raise ValueError('Expected upstream advisory object')
                identifier = item['ghsa_id']
                if not isinstance(identifier, str) or not identifier:
                    raise ValueError('Missing upstream advisory ID')
                finding = {'dependency': name, 'id': identifier, 'status': 'unknown',
                           'source': f'https://github.com/{REPOS[name]}/security/advisories/{identifier}',
                           'severity': item.get('severity', 'unknown')}
                findings.append(finding)
                count += 1
                try:
                    if item.get('withdrawn_at'):
                        finding['status'] = 'withdrawn'
                        continue
                    vulnerabilities = item['vulnerabilities']
                    if not isinstance(vulnerabilities, list) or not vulnerabilities:
                        raise ValueError('Missing upstream vulnerable ranges')
                    matches = []
                    for vulnerability in vulnerabilities:
                        if not isinstance(vulnerability, dict):
                            raise ValueError('Expected vulnerability object')
                        package = vulnerability.get('package', {})
                        expected = {'cares': 'c-ares'}.get(name, name)
                        if not isinstance(package, dict) or package.get('name', '') not in ('', expected):
                            raise ValueError('Unrecognized upstream package identity')
                        matches.append(in_range(entry['pin'], vulnerability['vulnerable_version_range']))
                    finding['ranges'] = [v['vulnerable_version_range'] for v in vulnerabilities]
                    finding['patched_versions'] = [v.get('patched_versions') for v in vulnerabilities]
                    # Do not infer a safe range from patched_versions: advisories may
                    # describe several release branches or contain conflicting metadata.
                    status = ('needs-triage' if any(matches) else 'not-affected-by-range')
                    if name == 'nghttp2':
                        status = nghttp2_status(identifier, any(matches))
                    finding['status'] = status
                    if status == 'backported':
                        finding['backport_commit'] = BACKPORT_COMMIT
                    if status == 'needs-triage':
                        finding.update(reviewed_resolution(name, entry, finding))
                except (ValueError, KeyError, TypeError) as error:
                    finding['error'] = str(error)
                    errors.append(f'{name} advisories: {identifier}: {error}')
            if len(feed) < 100:
                break
        else:
            raise ValueError('Upstream advisory pagination limit reached')
        entry['security_status'] = ('checked published upstream advisory ranges' if count
                                    else 'no-published-advisories: not evidence of safety')
        if name == 'boringssl' and not count:
            entry['security_status'] += '; manual-review: Git commit applicability'
    except (SourceError, ValueError, KeyError, TypeError) as error:
        errors.append(f'{name} advisories: {error}')
    if errors:
        entry['security_status'] = 'unknown'
    entry['advisory_count'] = count
    return findings, errors


def markdown(report):
    lines = ['# Native dependency maintenance report', '', report['generated_at'], '',
             '| Dependency | Pin | Upstream | Release triage |', '|---|---|---|---|']
    for name, entry in report['dependencies'].items():
        lines.append(f"| {name} | {entry['pin']} | {entry.get('upstream', 'unknown')} | {entry['release_status']} |")
    lines += ['', 'nghttp2 stays pinned for legacy HTTP/2 priorities. All updates need manual review.', '',
              'Security coverage: curl explicit affected-version lists and published upstream GitHub advisories.',
              'Empty feeds, libidn2, Git-only applicability, and patch interactions require manual review.',
              'This report is not a security certification.', '',
              f"Advisories requiring triage: {report['triage_required']}", '']
    for name, entry in report['dependencies'].items():
        lines.append(f"- {name}: {entry['security_status']} ({entry.get('advisory_count', 'unknown')} advisories)")
    for finding in report['advisories']:
        lines.append(f"- {finding['dependency']} [{finding['id']}]({finding['source']}): {finding['status']}" +
                     (f"; backport `{finding['backport_commit']}`" if 'backport_commit' in finding else ''))
        if finding.get('ranges'):
            lines.append(f"  - Affected ranges: {finding['ranges']}; upstream patched versions: {finding['patched_versions']}")
        if finding.get('review_note'):
            lines.append(f"  - Review: {finding['review_note']}")
            lines.extend(f'  - Evidence: {url}' for url in finding['review_sources'])
    if report['errors']:
        lines += ['', 'Source failures — result is incomplete, not clean:', '']
        lines += ['- ' + error for error in report['errors']]
    lines += ['', 'Primary release/advisory sources:', '']
    lines += [f"- {name}: {entry['release_source']}" for name, entry in report['dependencies'].items()]
    lines += [f"- {name} security: {entry.get('security_source', 'unknown')}"
              for name, entry in report['dependencies'].items()]
    lines.append('')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('dependency-report'))
    args = parser.parse_args()
    token = os.environ.get('GITHUB_TOKEN', '')
    data = inventory()
    errors = releases(data, token)
    findings, security_errors = advisories(data, token)
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'dependencies': data,
              'advisories': findings, 'errors': errors + security_errors,
              'triage_required': sum(item['status'] in ('needs-triage', 'unknown') for item in findings)}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    result = markdown(report)
    (args.output / 'report.md').write_text(result)
    print(result)
    return 1 if report['errors'] else (2 if report['triage_required'] else 0)


if __name__ == '__main__':
    sys.exit(main())
