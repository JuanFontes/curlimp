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
    except (urllib.error.URLError, OSError) as error:
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
    pins['libidn2'] = re.search(r'^LIBIDN2_VERSION=(.+)$', lock, re.M)[1]
    if set(pins) != set(REPOS) | {'libidn2'}:
        raise ValueError('Native pin inventory is incomplete')
    return {name: {'pin': pin.removeprefix('curl-').replace('_', '.'),
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
