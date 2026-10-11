#!/usr/bin/env python3
"""Validate the static artifact that GitHub Pages will actually serve."""
from html.parser import HTMLParser
from pathlib import Path
import json
import re
import subprocess
import sys
from urllib.parse import unquote, urljoin, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BASE = "/curlimp/"
ORIGIN = "https://juanfontes.github.io"


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.ids, self.links, self.meta, self.jsonld, self.codes = set(), [], {}, [], []
        self.title, self.canonical, self.lang, self.h1 = "", None, None, 0
        self.in_title = self.in_json = self.in_pre = False
        self.buffer, self.code, self.language = "", "", ""
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            assert a["id"] not in self.ids, f"Duplicate id: {a['id']}"
            self.ids.add(a["id"])
        if tag == "html": self.lang = a.get("lang")
        if tag == "h1": self.h1 += 1
        if tag == "title": self.in_title = True
        if tag == "meta": self.meta[a.get("name", a.get("property"))] = a.get("content")
        if tag == "link" and a.get("rel") == "canonical": self.canonical = a["href"]
        if tag == "script" and a.get("type") == "application/ld+json": self.in_json, self.buffer = True, ""
        if tag == "pre": self.in_pre, self.code, self.language = True, "", a.get("data-language", "")
        for attr in ("href", "src"):
            if a.get(attr): self.links.append(a[attr])

    def handle_data(self, text):
        if self.in_title: self.title += text
        if self.in_json: self.buffer += text
        if self.in_pre: self.code += text

    def handle_endtag(self, tag):
        if tag == "title": self.in_title = False
        if tag == "script" and self.in_json:
            self.jsonld.append(json.loads(self.buffer))
            self.in_json = False
        if tag == "pre" and self.in_pre:
            self.codes.append((self.language, self.code))
            self.in_pre = False


def route(path):
    relative = path.relative_to(DIST).as_posix()
    return BASE + (relative[:-10] if relative.endswith("index.html") else relative)


def main():
    version = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT.parent / "Cargo.toml").read_text(), re.M)[1]
    files = sorted(DIST.rglob("*.html"))
    assert files, "Run npm run build first"
    pages = {route(path): Page(path.read_text()) for path in files}
    titles, descriptions, indexable = set(), set(), set()
    examples = 0
    for path, page in pages.items():
        assert page.lang == "en" and page.h1 == 1, path
        assert page.title and page.title not in titles, f"Missing/duplicate title: {path}"
        titles.add(page.title)
        description = page.meta.get("description", "")
        assert description and description not in descriptions, f"Missing/duplicate description: {path}"
        descriptions.add(description)
        assert page.canonical == ORIGIN + path, f"Incorrect canonical: {path}"
        assert page.meta.get("og:url") == page.canonical, path
        assert page.meta.get("og:title") == page.title, path
        assert page.meta.get("og:description") == description, path
        assert page.meta.get("twitter:card") == "summary_large_image", path
        image = urlsplit(page.meta["og:image"])
        assert image.netloc == "juanfontes.github.io" and (DIST / image.path.removeprefix(BASE)).is_file(), path
        if path.endswith("404.html"):
            assert "noindex" in page.meta.get("robots", ""), path
        else:
            assert "noindex" not in page.meta.get("robots", ""), path
            assert page.jsonld and page.jsonld[0]["@context"] == "https://schema.org", path
            indexable.add(ORIGIN + path)
        for link in page.links:
            resolved = urlsplit(urljoin(ORIGIN + path, link))
            if resolved.scheme not in ("http", "https") or resolved.netloc != "juanfontes.github.io": continue
            assert resolved.path.startswith(BASE), f"Escapes project base: {path}: {link}"
            target = unquote(resolved.path)
            local = DIST / target.removeprefix(BASE)
            assert local.is_file() or (local / "index.html").is_file(), f"Broken link: {path}: {link}"
            if resolved.fragment and target in pages:
                assert unquote(resolved.fragment) in pages[target].ids, f"Broken anchor: {path}: {link}"
        for language, code in page.codes:
            for tag in re.findall(r"juanfontes/curlimp:([A-Za-z0-9_.-]+)", code):
                assert tag in ("latest", version), f"Unexpected image tag in {path}: {tag}"
            assert not re.search(r"https://httpbin\.org/(?!status/)[^\s'\"]+", code), f"Non-status example in {path}"
            assert not re.search(r"\n\+\s", code), f"Patch marker in command: {path}"
            if language in ("sh", "bash", "shell"):
                result = subprocess.run(["sh", "-n"], input=code, text=True, capture_output=True)
                assert result.returncode == 0, f"Shell syntax in {path}: {result.stderr}"
                examples += 1
    sitemap = ET.parse(DIST / "sitemap.xml")
    urls = {node.text for node in sitemap.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")}
    assert urls == indexable, f"Sitemap mismatch: {urls ^ indexable}"
    expected = {line.strip() for line in (ROOT.parent / "src/profiles.txt").read_text().splitlines() if line.strip() and not line.startswith("#")}
    rendered = (DIST / "docs/profiles/index.html").read_text()
    assert set(re.findall(r'data-profile="([^"]+)"', rendered)) == expected, "Profile catalog drift"
    for path in [ROOT.parent / "README.md", ROOT.parent / "docker/README.md", *ROOT.joinpath("src").rglob("*.md"), *ROOT.joinpath("src").rglob("*.astro")]:
        text = path.read_text()
        assert not re.search(r"https://httpbin\.org/(?!status/)[^\s'\"]+", text), f"Non-status example: {path}"
        for tag in re.findall(r"juanfontes/curlimp:([A-Za-z0-9_.-]+)", text):
            assert tag in ("latest", version), f"Unexpected image tag in {path}: {tag}"
        if path in (ROOT.parent / "README.md", ROOT.parent / "docker/README.md"):
            for code in re.findall(r"```(?:sh|bash)\n(.*?)```", text, re.S):
                result = subprocess.run(["sh", "-n"], input=code, text=True, capture_output=True)
                assert result.returncode == 0, f"Shell syntax in {path}: {result.stderr}"
                examples += 1
    notices = (DIST / "THIRD-PARTY-NOTICES.txt").read_text()
    for package in ("@fontsource-variable/inter", "@fontsource-variable/jetbrains-mono", "@tabler/icons"):
        assert (ROOT / "node_modules" / package / "LICENSE").read_text() in notices, f"Update bundled notice for {package}"
    print(f"Validated {len(pages)} HTML pages, {len(urls)} sitemap URLs, {examples} shell blocks, {len(expected)} profiles, links, anchors and SEO metadata.")


if __name__ == "__main__":
    try: main()
    except (AssertionError, KeyError, ValueError) as error:
        print(f"Site validation failed: {error}", file=sys.stderr)
        sys.exit(1)
