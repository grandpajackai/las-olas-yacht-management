#!/usr/bin/env python3
"""Check generated static pages locally, and optionally verify a live deployment.

Uses only Python's standard library. Run after ``python3 build.py``::

    python3 scripts/check-site.py
    python3 scripts/check-site.py --url https://grandpajackai.github.io/las-olas-yacht-management/

The live check reads every emitted HTML page and asset, verifies its exact deployed
contents, and requests an unknown route to check the branded HTTP 404 response.
It does not submit forms or send visitor information.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import posixpath
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen
import uuid
import xml.etree.ElementTree as ET
import json


ROOT = Path(__file__).resolve().parents[1]
CSS_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I)


class Page(HTMLParser):
    def __init__(self, source: str):
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.ids: list[str] = []
        self.refs: list[tuple[str, str]] = []
        self.titles: list[str] = []
        self.heading_counts: Counter[str] = Counter()
        self.meta: dict[str, list[str]] = {}
        self.canonicals: list[str] = []
        self.schemas: list[str] = []
        self.styles: list[str] = []
        self._capture: str | None = None
        self._buffer = ""
        self.feed(source)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        values = dict(attrs)
        self.tags.append((tag, values))
        if values.get("id"):
            self.ids.append(values["id"])
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.heading_counts[tag] += 1
        if tag == "title":
            self._capture, self._buffer = "title", ""
        elif tag == "script" and values.get("type") == "application/ld+json":
            self._capture, self._buffer = "schema", ""
        elif tag == "style":
            self._capture, self._buffer = "style", ""
        if tag == "meta":
            key = values.get("name") or values.get("property")
            if key:
                self.meta.setdefault(key, []).append(values.get("content") or "")
        if tag == "link" and "canonical" in (values.get("rel") or "").split():
            self.canonicals.append(values.get("href") or "")
        for attribute in ("href", "src", "poster"):
            if values.get(attribute):
                self.refs.append((attribute, values[attribute]))
        if values.get("srcset"):
            for candidate in values["srcset"].split(","):
                if candidate.strip():
                    self.refs.append(("srcset", candidate.strip().split()[0]))
        if values.get("style"):
            self.styles.append(values["style"])

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str):
        capture_for_tag = {"title": "title", "script": "schema", "style": "style"}
        if self._capture and self._capture == capture_for_tag.get(tag):
            target = {"title": self.titles, "schema": self.schemas, "style": self.styles}
            target[self._capture].append(self._buffer.strip())
            self._capture, self._buffer = None, ""

    def handle_data(self, data: str):
        if self._capture:
            self._buffer += data


class Audit:
    def __init__(self, docs: Path):
        self.docs = docs.resolve()
        self.errors: list[str] = []
        self.checked_refs = 0
        self.pages: dict[Path, Page] = {}
        self.base = ""
        self.origin = ""
        self.base_path = ""

    def fail(self, where: str | Path, message: str):
        if isinstance(where, Path):
            where = str(where.relative_to(self.docs))
        self.errors.append(f"{where}: {message}")

    def page_url(self, file: Path) -> str:
        relative = file.relative_to(self.docs).as_posix()
        if relative == "404.html":
            relative = "404/"
        elif relative.endswith("index.html"):
            relative = relative[:-len("index.html")]
        return self.base + relative

    def target(self, raw: str, source_url: str, where: Path, fragment=True) -> Path | None:
        """Resolve a local URL, enforcing the deployed repository prefix."""
        raw = raw.strip()
        if not raw or raw.startswith(("data:", "blob:", "mailto:", "tel:")):
            return None
        parsed_raw = urlsplit(raw)
        if parsed_raw.scheme and parsed_raw.scheme not in {"http", "https"}:
            self.fail(where, f"unsupported URL scheme: {raw}")
            return None
        url = urlsplit(urljoin(source_url, raw))
        if url.scheme not in {"http", "https"}:
            return None
        if url.netloc != urlsplit(self.origin).netloc:
            return None
        self.checked_refs += 1
        normalized = posixpath.normpath(unquote(url.path))
        prefix = self.base_path.rstrip("/")
        if prefix and normalized != prefix and not normalized.startswith(prefix + "/"):
            self.fail(where, f"URL escapes site base path {prefix}/: {raw}")
            return None
        relative = normalized[len(prefix):].lstrip("/")
        file = (self.docs / relative).resolve()
        if not file.is_relative_to(self.docs):
            self.fail(where, f"URL escapes output directory: {raw}")
            return None
        if file.is_dir():
            file /= "index.html"
        if not file.is_file():
            self.fail(where, f"missing local target: {raw}")
            return None
        if fragment and url.fragment and file.suffix == ".html":
            target_page = self.pages.get(file)
            if target_page and unquote(url.fragment) not in target_page.ids:
                self.fail(where, f"missing fragment #{url.fragment}: {raw}")
        return file

    def check_schema_urls(self, obj, source: Path):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in {"url", "@id", "item", "mainEntityOfPage"} and isinstance(value, str):
                    self.target(value, self.page_url(source), source, fragment=False)
                self.check_schema_urls(value, source)
        elif isinstance(obj, list):
            for value in obj:
                self.check_schema_urls(value, source)

    def check(self):
        if not self.docs.is_dir():
            self.errors.append(f"Missing generated output directory: {self.docs}")
            return
        for file in sorted(self.docs.rglob("*.html")):
            try:
                self.pages[file] = Page(file.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError) as error:
                self.fail(file, f"cannot parse HTML: {error}")
        homepage = self.pages.get(self.docs / "index.html")
        if not homepage or len(homepage.canonicals) != 1:
            self.errors.append("Homepage must have exactly one canonical URL to establish the site base.")
            return
        self.base = homepage.canonicals[0].rstrip("/") + "/"
        parsed_base = urlsplit(self.base)
        if parsed_base.scheme != "https" or not parsed_base.netloc:
            self.errors.append(f"Homepage canonical must be an absolute HTTPS URL: {self.base}")
            return
        self.origin = urlunsplit((parsed_base.scheme, parsed_base.netloc, "", "", ""))
        self.base_path = parsed_base.path.rstrip("/")
        titles: dict[str, Path] = {}
        descriptions: dict[str, Path] = {}
        for file, page in self.pages.items():
            alias_404 = file == self.docs / "404.html"
            expected_url = self.page_url(file)
            if page.heading_counts["h1"] != 1:
                self.fail(file, f"expected one H1, found {page.heading_counts['h1']}")
            duplicate_ids = [key for key, count in Counter(page.ids).items() if count > 1]
            if duplicate_ids:
                self.fail(file, f"duplicate IDs: {', '.join(duplicate_ids)}")
            if len(page.titles) != 1 or not page.titles[0]:
                self.fail(file, "expected one nonempty title")
            elif not alias_404:
                if page.titles[0] in titles:
                    self.fail(file, f"duplicate title with {titles[page.titles[0]].relative_to(self.docs)}")
                titles[page.titles[0]] = file
            description = page.meta.get("description", [])
            if len(description) != 1 or not description[0]:
                self.fail(file, "expected one nonempty meta description")
            elif not alias_404:
                if description[0] in descriptions:
                    self.fail(file, f"duplicate description with {descriptions[description[0]].relative_to(self.docs)}")
                descriptions[description[0]] = file
            if page.canonicals != [expected_url]:
                self.fail(file, f"canonical must be {expected_url}, found {page.canonicals}")
            required_meta = {"og:url": expected_url, "og:title": page.titles[0] if page.titles else "",
                             "og:description": description[0] if description else ""}
            for key, expected in required_meta.items():
                if page.meta.get(key) != [expected]:
                    self.fail(file, f"{key} must match page metadata")
            for key in ("og:image", "og:image:alt", "og:site_name", "og:type", "twitter:card", "viewport"):
                if len(page.meta.get(key, [])) != 1 or not page.meta[key][0]:
                    self.fail(file, f"expected one nonempty {key}")
            for image in page.meta.get("og:image", []):
                if not image.startswith(self.base):
                    self.fail(file, f"Open Graph image must use the site base: {image}")
                self.target(image, expected_url, file)
            if not page.schemas:
                self.fail(file, "missing JSON-LD")
            for source in page.schemas:
                try:
                    schema = json.loads(source)
                except ValueError as error:
                    self.fail(file, f"invalid JSON-LD: {error}")
                    continue
                self.check_schema_urls(schema, file)
                graph = schema.get("@graph", []) if isinstance(schema, dict) else []
                if not any(item.get("@type") == "WebPage" and item.get("url") == expected_url
                           for item in graph if isinstance(item, dict)):
                    self.fail(file, "JSON-LD is missing the matching WebPage URL")
            for attribute, raw in page.refs:
                self.target(raw, expected_url, file)
            for style in page.styles:
                for _, raw in CSS_URL.findall(style):
                    self.target(raw, expected_url, file)
            for tag, attrs in page.tags:
                if tag == "img":
                    if "alt" not in attrs:
                        self.fail(file, "image lacks an alt attribute")
                    if not attrs.get("width") or not attrs.get("height"):
                        self.fail(file, "image lacks intrinsic width/height")
                for key in ("aria-controls", "aria-labelledby", "aria-describedby", "for"):
                    for referenced_id in (attrs.get(key) or "").split():
                        if referenced_id not in page.ids:
                            self.fail(file, f"{key} refers to missing ID {referenced_id}")
        for file in sorted(self.docs.rglob("*.css")):
            source_url = self.base + file.relative_to(self.docs).as_posix()
            for _, raw in CSS_URL.findall(file.read_text(encoding="utf-8")):
                if raw.startswith("#"):
                    continue  # SVG filters in CSS reference the document in which the rule is used.
                self.target(raw, source_url, file)
        expected_sitemap = {self.page_url(file) for file in self.pages
                            if file not in {self.docs / "404.html", self.docs / "404/index.html"}}
        try:
            sitemap = ET.parse(self.docs / "sitemap.xml")
            locations = [element.text or "" for element in sitemap.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
            if len(locations) != len(set(locations)):
                self.errors.append("sitemap.xml: duplicate URLs")
            if set(locations) != expected_sitemap:
                missing, extra = expected_sitemap - set(locations), set(locations) - expected_sitemap
                self.errors.append(f"sitemap.xml: route mismatch (missing={sorted(missing)}, extra={sorted(extra)})")
        except (OSError, ET.ParseError) as error:
            self.errors.append(f"sitemap.xml: {error}")
        try:
            robots = (self.docs / "robots.txt").read_text(encoding="utf-8")
            sitemap_lines = re.findall(r"^Sitemap:\s*(\S+)\s*$", robots, re.M | re.I)
            if sitemap_lines != [self.base + "sitemap.xml"]:
                self.errors.append(f"robots.txt: sitemap must use {self.base}sitemap.xml")
        except OSError as error:
            self.errors.append(f"robots.txt: {error}")


def request(url: str) -> tuple[int, bytes, str]:
    req = Request(url, headers={"User-Agent": "Las-Olas-Static-QA/1.0", "Cache-Control": "no-cache"})
    try:
        with urlopen(req, timeout=25) as response:
            return response.status, response.read(), response.headers.get("Content-Type", "")
    except HTTPError as error:
        return error.code, error.read(), error.headers.get("Content-Type", "")


def live_check(audit: Audit, deployment: str):
    deployment = deployment.rstrip("/") + "/"
    if deployment != audit.base:
        audit.errors.append(f"Live URL {deployment} does not match the generated canonical base {audit.base}; rebuild with SITE_URL first.")
        return
    files = sorted(file for file in audit.docs.rglob("*")
                   if file.is_file() and (file.suffix == ".html" or "assets" in file.relative_to(audit.docs).parts
                                         or file.name in {"sitemap.xml", "robots.txt"}))

    def verify(file: Path):
        relative = file.relative_to(audit.docs).as_posix()
        if relative.endswith("index.html"):
            relative = relative[:-len("index.html")]
        url = deployment + relative
        try:
            status, body, content_type = request(url)
            if status != 200:
                return f"{url}: expected HTTP 200, received {status}"
            if hashlib.sha256(body).digest() != hashlib.sha256(file.read_bytes()).digest():
                return f"{url}: deployed contents differ from generated local file"
            if file.suffix == ".html" and "text/html" not in content_type.lower():
                return f"{url}: expected HTML content type, received {content_type}"
            return None
        except (OSError, URLError) as error:
            return f"{url}: fetch failed: {error}"

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(verify, file) for file in files]
        for future in as_completed(futures):
            error = future.result()
            if error:
                audit.errors.append(error)
    unknown_url = deployment + "__qa_missing_" + uuid.uuid4().hex + "/"
    try:
        status, body, content_type = request(unknown_url)
        if status != 404:
            audit.errors.append(f"Unknown route: expected HTTP 404, received {status}")
        page = Page(body.decode("utf-8", errors="replace"))
        expected_page = audit.pages.get(audit.docs / "404.html")
        if not expected_page or page.titles != expected_page.titles:
            audit.errors.append("Unknown route: branded page-not-found title is missing")
        home_links = [attrs for tag, attrs in page.tags if tag == "a" and attrs.get("href") == audit.base_path + "/"]
        if not home_links:
            audit.errors.append("Unknown route: site-base home recovery link is missing")
        for attribute, raw in page.refs:
            audit.target(raw, audit.base + "404/", audit.docs / "404.html")
        if "text/html" not in content_type.lower():
            audit.errors.append(f"Unknown route: expected HTML content type, received {content_type}")
    except (OSError, URLError) as error:
        audit.errors.append(f"Unknown route: fetch failed: {error}")
    print(f"Live check: {len(files)} HTML/assets/support files and one unknown route requested.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", help="Also fetch every generated HTML page/asset from this exact deployment URL")
    parser.add_argument("--docs", type=Path, default=ROOT / "docs", help="Generated output directory (default: docs)")
    options = parser.parse_args()
    audit = Audit(options.docs)
    audit.check()
    print(f"Local check: {len(audit.pages)} HTML files, {audit.checked_refs} internal references, metadata, JSON-LD, CSS assets, sitemap and robots.")
    if options.url and not audit.errors:
        live_check(audit, options.url)
    if audit.errors:
        print(f"FAIL: {len(audit.errors)} issue(s)", file=sys.stderr)
        for error in audit.errors[:60]:
            print(f"  {error}", file=sys.stderr)
        if len(audit.errors) > 60:
            print(f"  … {len(audit.errors) - 60} more", file=sys.stderr)
        return 1
    print("PASS: no issues found in these checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
