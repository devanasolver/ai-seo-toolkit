"""Offline tests: audit runs against a local fixture server, no internet needed."""

import functools
import http.server
import os
import threading

import pytest

from aiseo.audit import audit, _parse_robots, _bot_blocked, _jsonld_types
from aiseo.keywords import expand_keywords
from bs4 import BeautifulSoup

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def server():
    handler = functools.partial(Quiet, directory=FIXTURES)
    srv = http.server.HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_full_audit_good_site(server):
    result = audit(server)
    assert result.score >= 70, f"good fixture should score well, got {result.score}"
    assert result.band in ("Good", "Excellent")
    by_key = {c.key: c for c in result.categories}
    assert by_key["structured_data"].score == by_key["structured_data"].max_score
    assert by_key["meta"].score == by_key["meta"].max_score
    d = result.to_dict()
    assert d["url"].startswith("http://127.0.0.1")
    assert isinstance(d["fixes"], list)


def test_audit_missing_files_scores_lower(server):
    # The fixture server has no /llms.txt on missing paths -> SimpleHTTPRequestHandler 404s,
    # and the soft-404 probe returns 404, so discovery points come only from real files.
    result = audit(server)
    disc = next(c for c in result.categories if c.key == "discovery")
    assert disc.score >= 10  # llms.txt exists in fixtures


def test_parse_robots_and_bot_blocking():
    groups = _parse_robots("User-agent: *\nDisallow: /\n\nUser-agent: GPTBot\nAllow: /\n")
    assert _bot_blocked(groups, "Bingbot") is True
    assert _bot_blocked(groups, "GPTBot") is False


def test_parse_robots_allow_all():
    groups = _parse_robots("User-agent: *\nAllow: /\n")
    assert _bot_blocked(groups, "ClaudeBot") is False


def test_jsonld_types_nested():
    soup = BeautifulSoup(
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@graph":[{"@type":"Organization"},'
        '{"@type":["Article","BlogPosting"]}]}</script>',
        "lxml",
    )
    assert _jsonld_types(soup) == {"Organization", "Article", "BlogPosting"}


def test_jsonld_invalid_ignored():
    soup = BeautifulSoup('<script type="application/ld+json">not json</script>', "lxml")
    assert _jsonld_types(soup) == set()


def test_keywords_parsing(monkeypatch):
    class FakeResp:
        def json(self):
            return ["ai seo", ["ai seo tool", "ai seo course"]]

    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(params["q"])
        return FakeResp()

    monkeypatch.setattr("requests.get", fake_get)
    rows = expand_keywords("ai seo", alphabet=False, questions=False)
    assert rows == [
        {"keyword": "ai seo tool", "source": "seed"},
        {"keyword": "ai seo course", "source": "seed"},
    ]


def test_keywords_dedupe_and_sources(monkeypatch):
    class FakeResp:
        def __init__(self, items):
            self.items = items

        def json(self):
            return ["x", self.items]

    def fake_get(url, params=None, headers=None, timeout=None):
        if params["q"] == "seed":
            return FakeResp(["alpha", "beta"])
        return FakeResp(["alpha", "gamma"])

    monkeypatch.setattr("requests.get", fake_get)
    rows = expand_keywords("seed", alphabet=False, questions=True)
    kw = [r["keyword"] for r in rows]
    assert kw == ["alpha", "beta", "gamma"]
    assert rows[0]["source"] == "seed"
    assert rows[2]["source"] == "question"
