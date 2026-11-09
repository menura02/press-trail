from datetime import UTC, datetime

import pytest

from app.collectors import extract, parse_date, parse_feed
from app.network import FetchError, Response


def test_rss_atom_relative_and_bad_entries(fixtures):
    entries, skipped = parse_feed(Response("https://gazete.example.org/feed/rss", 200, {},
                                           (fixtures / "news.rss").read_bytes()))
    assert skipped == 1
    assert entries[0].url == "https://gazete.example.org/haber?konu=baraj&sayi=1"
    assert entries[0].feed_id == "baraj-1"
    entries, skipped = parse_feed(Response("https://atom.example.org/feed.xml", 200, {},
                                           (fixtures / "news.atom").read_bytes()))
    assert skipped == 0
    assert entries[0].url == "https://atom.example.org/bulten/olcum"
    assert entries[0].feed_id == "urn:entry:1"


@pytest.mark.parametrize("body", [
    b"<rss>",
    b'<!DOCTYPE rss [<!ENTITY x SYSTEM "file:///secret">]><rss>&x;</rss>',
    b"<rss>" + b"<a>" * 70 + b"</a>" * 70 + b"</rss>",
])
def test_unsafe_or_malformed_feed(body):
    with pytest.raises(FetchError, match="parse"):
        parse_feed(Response("https://example.com", 200, {}, body))


@pytest.mark.parametrize(("value", "state"), [
    ("2025-05-13T09:15:00", "uncertain"),
    ("Tue, 13 May 2025 09:15:00 -0000", "uncertain"),
    ("2025-05-13T09:15:00 TRT", "uncertain"),
    ("geçersiz", "invalid"),
    (None, "missing"),
])
def test_unknown_dates(value, state):
    assert parse_date(value) == (None, state)


def test_known_date():
    assert parse_date("Tue, 13 May 2025 09:15:00 +0300") == (
        datetime(2025, 5, 13, 6, 15, tzinfo=UTC), "known")


def test_article_links_are_scoped_to_article_text(fixtures):
    body, links = extract(Response("https://atom.example.org/bulten/olcum", 200, {},
                                   (fixtures / "news.html").read_bytes()))
    assert "doluluk" in body and "Reklam" not in body
    assert [(link["url"], link["kind"]) for link in links] == [
        ("https://gazete.example.org/haber?konu=baraj&sayi=1", "explicit"),
        ("https://atom.example.org/arsiv", "link"),
    ]
    assert "Ölçümlerin" in links[0]["context"]


def test_paywall_marker(fixtures):
    html = (fixtures / "news.html").read_bytes().replace(
        b"</head>", b'<script type="application/ld+json">{"isAccessibleForFree":false}</script></head>')
    with pytest.raises(FetchError, match="access"):
        extract(Response("https://example.com/article", 200, {}, html))

