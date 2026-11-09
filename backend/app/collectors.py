from dataclasses import dataclass
from datetime import UTC, datetime
import json
import re
import warnings
from xml.etree.ElementTree import ParseError

import feedparser
from bs4 import BeautifulSoup
from dateutil.parser import UnknownTimezoneWarning, parse
from defusedxml.ElementTree import fromstring
from defusedxml.common import DefusedXmlException
from readability import Document

from .network import FetchError, normalize_url


@dataclass
class Entry:
    url: str
    feed_id: str | None
    title: str
    summary: str
    published_raw: str | None
    updated_raw: str | None


def plain(value):
    return " ".join(BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True).split())


def parse_feed(response):
    try:
        root = fromstring(response.body, forbid_dtd=True, forbid_entities=True, forbid_external=True)
        if root.tag.split("}")[-1] not in {"rss", "feed", "RDF"}:
            raise ValueError
        stack = [(root, 1)]
        count = 0
        while stack:
            element, depth = stack.pop()
            count += 1
            if depth > 64 or count > 20000:
                raise ValueError
            stack.extend((child, depth + 1) for child in element)
    except (ValueError, ParseError, DefusedXmlException):
        raise FetchError("parse") from None
    data = feedparser.parse(response.body, response_headers={"content-location": response.url},
                            resolve_relative_uris=True, sanitize_html=True)
    entries = []
    skipped = 0
    for item in data.entries[:100]:
        try:
            url = normalize_url(item.get("link"), response.url)
            title = plain(item.get("title"))[:1500]
            summary = plain(item.get("summary"))[:20000]
            if not (title or summary):
                raise FetchError("parse")
            entries.append(Entry(url, item.get("id", "")[:600] or None, title, summary,
                                 dict.get(item, "published"), dict.get(item, "updated")))
        except FetchError:
            skipped += 1
    return entries, skipped + max(0, len(data.entries) - 100)


def parse_date(raw):
    if not raw:
        return None, "missing"
    try:
        if not re.search(r"\d{2}:\d{2}", raw):
            return None, "uncertain" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw.strip()) else "invalid"
        with warnings.catch_warnings():
            warnings.simplefilter("error", UnknownTimezoneWarning)
            value = parse(raw, default=datetime(1900, 1, 1))
        if value.year == 1900 and "1900" not in raw:
            return None, "invalid"
        explicit = re.search(r"(?:Z|[+-]\d{2}(?::?\d{2})?|\b(?:UTC|GMT)\)?)\s*$", raw, re.I)
        if not explicit or value.utcoffset() is None or raw.strip().endswith(("-0000", "-00:00")):
            return None, "uncertain"
        return value.astimezone(UTC), "known"
    except UnknownTimezoneWarning:
        return None, "uncertain"
    except (ValueError, OverflowError):
        return None, "invalid"


def extract(response):
    if response.status in {401, 403, 407, 451}:
        raise FetchError("access")
    if response.status != 200:
        raise FetchError("http")
    mime = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if mime and mime not in {"text/html", "application/xhtml+xml"}:
        raise FetchError("parse")
    source = BeautifulSoup(response.body, "html.parser")
    base = response.url
    base_tag = source.select_one("head base[href]")
    if base_tag:
        try:
            base = normalize_url(base_tag["href"], base)
        except FetchError:
            pass
    blocked = source.select_one('meta[property="article:isAccessibleForFree"][content="false"], '
                                '[itemprop="isAccessibleForFree"][content="false"]')
    def restricted(value):
        if isinstance(value, dict):
            return str(value.get("isAccessibleForFree")).lower() == "false" or any(
                restricted(item) for item in value.values())
        return isinstance(value, list) and any(restricted(item) for item in value)

    def restricted_script(script):
        try:
            return restricted(json.loads(script.get_text()))
        except (ValueError, RecursionError):
            return False

    if blocked or any(restricted_script(script) for script in source.select('script[type="application/ld+json"]')):
        raise FetchError("access")
    try:
        region = BeautifulSoup(Document(str(source)).summary(), "html.parser")
    except Exception:
        raise FetchError("parse") from None
    for element in region.select("nav, aside, footer, header, script, style, form"):
        element.decompose()
    body = "\n\n".join(p.get_text(" ", strip=True) for p in region.select("p") if p.get_text(strip=True))
    if len(body) < 100:
        raise FetchError("extract")
    links = []
    seen = set()
    for a in region.select("p a[href], blockquote a[href]"):
        try:
            url = normalize_url(a["href"], base)
        except FetchError:
            continue
        label = a.get_text(" ", strip=True)[:300]
        context = a.find_parent(["p", "blockquote"]).get_text(" ", strip=True)[:700]
        key = (url, label, context)
        if key in seen:
            continue
        seen.add(key)
        folded = label.casefold().strip(" :")
        kind = "explicit" if folded in {"kaynak", "orijinal kaynak", "kaynak haber"} else "link"
        links.append({"url": url, "text": label, "context": context, "kind": kind})
        if len(links) == 100:
            break
    return body[:150000], links

