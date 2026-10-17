"""AI-search visibility audit.

Original implementation by ai-seo-toolkit. The idea of scoring a site for
AI answer engines was inspired by the MIT-licensed geo-optimizer-skill
(Auriti-Labs); see NOTICE. All code here is written from scratch.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = "aiseo-toolkit/0.1 (+https://github.com/devanasolver/ai-seo-toolkit)"
TIMEOUT = 20

# Well-known AI crawlers. Allowing them is what makes a site citable by AI answers.
AI_BOTS = [
    "GPTBot", "ChatGPT-User", "OAI-SearchBot",
    "ClaudeBot", "Claude-User",
    "PerplexityBot", "Perplexity-User",
    "Google-Extended", "Applebot-Extended",
    "Meta-ExternalAgent", "Bingbot",
]

VALUABLE_SCHEMAS = {
    "Organization", "WebSite", "WebPage", "Article", "BlogPosting",
    "FAQPage", "HowTo", "Product", "SoftwareApplication", "Person",
    "BreadcrumbList", "Review", "LocalBusiness",
}


@dataclass
class Check:
    name: str
    points: int
    max_points: int
    ok: bool
    detail: str
    fix: str = ""


@dataclass
class CategoryResult:
    key: str
    title: str
    checks: list = field(default_factory=list)

    @property
    def score(self) -> int:
        return sum(c.points for c in self.checks)

    @property
    def max_score(self) -> int:
        return sum(c.max_points for c in self.checks)


@dataclass
class AuditResult:
    url: str
    categories: list = field(default_factory=list)
    fixes: list = field(default_factory=list)  # (impact, text)

    @property
    def score(self) -> int:
        return sum(c.score for c in self.categories)

    @property
    def max_score(self) -> int:
        return sum(c.max_score for c in self.categories)

    @property
    def band(self) -> str:
        pct = self.score / max(self.max_score, 1) * 100
        if pct >= 80:
            return "Excellent"
        if pct >= 60:
            return "Good"
        if pct >= 40:
            return "Needs work"
        return "Critical"

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "score": self.score,
            "max_score": self.max_score,
            "band": self.band,
            "categories": [
                {
                    "key": c.key,
                    "title": c.title,
                    "score": c.score,
                    "max_score": c.max_score,
                    "checks": [
                        {
                            "name": ch.name,
                            "ok": ch.ok,
                            "points": ch.points,
                            "max_points": ch.max_points,
                            "detail": ch.detail,
                            "fix": ch.fix,
                        }
                        for ch in c.checks
                    ],
                }
                for c in self.categories
            ],
            "fixes": [{"impact": i, "fix": f} for i, f in self.fixes],
        }


def _get(url: str) -> requests.Response:
    return requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, allow_redirects=True)


def _parse_robots(text: str) -> dict:
    """Return {user_agent_lower: {'allow': set, 'disallow': set}} plus '*' group."""
    groups: dict = {}
    current: list = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            current = [value.lower()]
            groups.setdefault(value.lower(), {"allow": set(), "disallow": set()})
        elif key in ("allow", "disallow") and current:
            for ua in current:
                groups.setdefault(ua, {"allow": set(), "disallow": set()})[key].add(value)
    return groups


def _blocks_all(rules: dict) -> bool:
    """True if the rules block the whole site (Disallow: / with no Allow override)."""
    return "/" in rules.get("disallow", set()) and not rules.get("allow")


def _bot_blocked(groups: dict, bot: str) -> bool:
    rules = groups.get(bot.lower()) or groups.get("*") or {}
    return _blocks_all(rules)


def _jsonld_types(soup: BeautifulSoup) -> set:
    types: set = set()

    def walk(node):
        if isinstance(node, dict):
            t = node.get("@type")
            if isinstance(t, str):
                types.add(t)
            elif isinstance(t, list):
                types.update(x for x in t if isinstance(x, str))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            walk(json.loads(tag.string or ""))
        except (ValueError, TypeError):
            continue
    return types


def check_ai_access(base_url: str) -> CategoryResult:
    cat = CategoryResult("ai_access", "AI crawler access (robots.txt)")
    robots_url = urljoin(base_url, "/robots.txt")
    unreachable = None
    try:
        resp = _get(robots_url)
        if resp.status_code != 200:
            unreachable = f"robots.txt returned HTTP {resp.status_code}"
    except requests.RequestException as exc:
        unreachable = f"Could not fetch robots.txt: {exc}"
    if unreachable:
        cat.checks.append(Check("robots.txt reachable", 0, 5, False, unreachable,
                                "Create a robots.txt at the root of your site (https://yoursite.com/robots.txt)."))
        cat.checks.append(Check("Site not fully blocked", 0, 5, False, "Unknown without a robots.txt.",
                                "Add a robots.txt with 'User-agent: *' and 'Allow: /'."))
        cat.checks.append(Check("AI crawlers allowed", 0, 15, False,
                                "Unknown whether AI crawlers are welcome.",
                                "Add robots.txt rules that Allow the AI bots (GPTBot, ClaudeBot, PerplexityBot, and friends)."))
        return cat

    cat.checks.append(Check("robots.txt reachable", 5, 5, True, "robots.txt loads fine."))
    groups = _parse_robots(resp.text)
    star = groups.get("*", {})
    if _blocks_all(star):
        cat.checks.append(Check("Site not fully blocked", 0, 5, False,
                                "robots.txt has 'User-agent: *' with 'Disallow: /'. Nothing can crawl the site.",
                                "Remove the blanket 'Disallow: /' rule."))
    else:
        cat.checks.append(Check("Site not fully blocked", 5, 5, True, "No blanket block found."))

    blocked = [b for b in AI_BOTS if _bot_blocked(groups, b)]
    allowed_count = len(AI_BOTS) - len(blocked)
    points = round(15 * allowed_count / len(AI_BOTS))
    if blocked:
        cat.checks.append(Check("AI crawlers allowed", points, 15, False,
                                f"Blocked AI crawlers: {', '.join(blocked)}.",
                                "Add 'User-agent: GPTBot / Allow: /' style rules for the AI bots you want citing you."))
    else:
        cat.checks.append(Check("AI crawlers allowed", 15, 15, True,
                                "No known AI crawler is blocked."))
    return cat


def check_discovery(base_url: str) -> CategoryResult:
    cat = CategoryResult("discovery", "AI discovery files (llms.txt, sitemap)")
    # llms.txt
    try:
        resp = _get(urljoin(base_url, "/llms.txt"))
        body = resp.text or ""
        looks_real = resp.status_code == 200 and ("#" in body or "http" in body) and "<html" not in body.lower()
        if looks_real:
            cat.checks.append(Check("llms.txt present", 10, 10, True, "llms.txt found and looks valid."))
        else:
            cat.checks.append(Check("llms.txt present", 0, 10, False,
                                    "No llms.txt found (or it returns a web page).",
                                    "Create /llms.txt: a short Markdown file that tells AI models what your site is and links key pages."))
    except requests.RequestException:
        cat.checks.append(Check("llms.txt present", 0, 10, False, "Could not fetch /llms.txt.",
                                "Create /llms.txt at your site root."))
    # sitemap
    for path in ("/sitemap.xml", "/sitemap_index.xml"):
        try:
            resp = _get(urljoin(base_url, path))
        except requests.RequestException:
            continue
        if resp.status_code == 200 and "<url" in resp.text or "<sitemap>" in resp.text:
            count = resp.text.count("<url>")
            cat.checks.append(Check("XML sitemap", 5, 5, True, f"Sitemap found at {path} ({count} URLs)."))
            break
    else:
        cat.checks.append(Check("XML sitemap", 0, 5, False, "No sitemap.xml found.",
                                "Add an XML sitemap and reference it in robots.txt."))
    return cat


def check_structured_data(soup: BeautifulSoup) -> CategoryResult:
    cat = CategoryResult("structured_data", "Structured data (schema.org)")
    types = _jsonld_types(soup)
    if types:
        cat.checks.append(Check("JSON-LD present", 8, 8, True, f"Found schema types: {', '.join(sorted(types))}."))
    else:
        cat.checks.append(Check("JSON-LD present", 0, 8, False, "No JSON-LD structured data on the page.",
                                "Add JSON-LD schema (at minimum Organization and WebSite) so AI engines know who you are."))
    entity = types & {"Organization", "WebSite", "Person", "LocalBusiness"}
    cat.checks.append(Check("Entity schema", 6 if entity else 0, 6, bool(entity),
                            "Site/organization schema present." if entity else "No Organization, WebSite or Person schema.",
                            "" if entity else "Add Organization + WebSite JSON-LD to your home page."))
    content = types & {"Article", "BlogPosting", "FAQPage", "HowTo", "Product", "SoftwareApplication", "Review"}
    cat.checks.append(Check("Content schema", 6 if content else 0, 6, bool(content),
                            "Content schema present." if content else "No Article/FAQ/Product-style schema.",
                            "" if content else "Mark up articles, FAQs and products with matching schema types."))
    return cat


def check_content(soup: BeautifulSoup) -> CategoryResult:
    cat = CategoryResult("content", "Content AI can quote")
    text = soup.get_text(" ", strip=True)
    words = len(text.split())
    cat.checks.append(Check("Enough text", 5 if words >= 300 else (2 if words >= 100 else 0), 5, words >= 300,
                            f"About {words} words of visible text.",
                            "" if words >= 300 else "Thin pages rarely get cited. Aim for 300+ useful words."))
    h1s = soup.find_all("h1")
    cat.checks.append(Check("One clear H1", 3 if len(h1s) == 1 else 0, 3, len(h1s) == 1,
                            f"{len(h1s)} H1 headings.",
                            "" if len(h1s) == 1 else "Use exactly one H1 that states the page topic plainly."))
    heads = [int(h.name[1]) for h in soup.find_all(["h1", "h2", "h3", "h4"])]
    ordered = all(b >= a for a, b in zip(heads, heads[1:]))
    cat.checks.append(Check("Heading order", 2 if ordered and heads else 0, 2, ordered and bool(heads),
                            "Headings are in order." if ordered and heads else "Headings skip levels or are missing.",
                            "" if ordered and heads else "Use H2/H3 in order; AI models read structure to find answers."))
    first_p = soup.find("p")
    pw = len(first_p.get_text(" ", strip=True).split()) if first_p else 0
    cat.checks.append(Check("Answer-first opening", 4 if pw >= 15 else 0, 4, pw >= 15,
                            f"First paragraph has {pw} words.",
                            "" if pw >= 15 else "Open pages with a direct 1-2 sentence answer. AI answers quote the first clear statement."))
    faq = bool(soup.find_all(["details"])) or any(
        (h.get_text(strip=True).endswith("?")) for h in soup.find_all(["h2", "h3", "h4"])
    )
    cat.checks.append(Check("FAQ-style content", 3 if faq else 0, 3, faq,
                            "Question-style headings or FAQ blocks found." if faq else "No question-style headings.",
                            "" if faq else "Add headings phrased as real questions people ask, each with a short answer."))
    links = [a for a in soup.find_all("a", href=True) if not a["href"].startswith(("http", "//", "mailto:"))]
    cat.checks.append(Check("Internal links", 3 if len(links) >= 3 else 0, 3, len(links) >= 3,
                            f"{len(links)} internal links.",
                            "" if len(links) >= 3 else "Link your pages to each other so crawlers find your best content."))
    return cat


def check_meta(soup: BeautifulSoup) -> CategoryResult:
    cat = CategoryResult("meta", "Title, description, canonical")
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    ok = 10 <= len(title) <= 70
    cat.checks.append(Check("Title tag", 3 if ok else 0, 3, ok, f"Title is {len(title)} characters.",
                            "" if ok else "Write a clear 10-70 character title."))
    desc = soup.find("meta", attrs={"name": "description"})
    desc = (desc.get("content") or "").strip() if desc else ""
    ok = 50 <= len(desc) <= 170
    cat.checks.append(Check("Meta description", 3 if ok else 0, 3, ok, f"Description is {len(desc)} characters.",
                            "" if ok else "Write a 50-170 character description that answers what the page is about."))
    canon = soup.find("link", attrs={"rel": "canonical"})
    cat.checks.append(Check("Canonical URL", 2 if canon else 0, 2, bool(canon),
                            "Canonical link present." if canon else "No canonical link.",
                            "" if canon else "Add <link rel=\"canonical\"> so engines know the one true URL."))
    og = soup.find("meta", attrs={"property": "og:title"})
    cat.checks.append(Check("Social tags", 2 if og else 0, 2, bool(og),
                            "Open Graph tags present." if og else "No Open Graph tags.",
                            "" if og else "Add og:title and og:description so shared links and AI previews look right."))
    return cat


def check_technical(url: str, response: requests.Response, elapsed: float, base_url: str) -> CategoryResult:
    cat = CategoryResult("technical", "Technical basics")
    https = urlparse(url).scheme == "https"
    cat.checks.append(Check("HTTPS", 2 if https else 0, 2, https,
                            "Site uses HTTPS." if https else "Site is plain HTTP.",
                            "" if https else "Move to HTTPS. AI engines and browsers distrust plain HTTP."))
    ok = response.status_code == 200
    cat.checks.append(Check("Page loads", 2 if ok else 0, 2, ok, f"HTTP {response.status_code}.",
                            "" if ok else "The page does not return 200."))
    fast = elapsed < 2.0
    cat.checks.append(Check("Loads fast", 3 if fast else (1 if elapsed < 5 else 0), 3, fast,
                            f"First response in {elapsed:.1f}s.",
                            "" if fast else "Slow pages get crawled less. Aim for a first response under 2 seconds."))
    try:
        probe = _get(urljoin(base_url, "/this-page-should-not-exist-aiseo-probe"))
        soft404 = probe.status_code == 200
    except requests.RequestException:
        soft404 = False
    cat.checks.append(Check("Real 404s", 0 if soft404 else 3, 3, not soft404,
                            "Missing pages return 200 (soft 404)." if soft404 else "Missing pages return a real 404.",
                            "Make unknown URLs return HTTP 404. Soft 404s confuse both Google and AI crawlers." if soft404 else ""))
    return cat


def audit(url: str) -> AuditResult:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    start = time.monotonic()
    response = _get(url)
    elapsed = time.monotonic() - start
    base = f"{urlparse(response.url).scheme}://{urlparse(response.url).netloc}"
    soup = BeautifulSoup(response.text, "lxml")

    result = AuditResult(url=response.url)
    result.categories.append(check_ai_access(base))
    result.categories.append(check_discovery(base))
    result.categories.append(check_structured_data(soup))
    result.categories.append(check_content(soup))
    result.categories.append(check_meta(soup))
    result.categories.append(check_technical(response.url, response, elapsed, base))

    fixes = []
    for cat in result.categories:
        for ch in cat.checks:
            if not ch.ok and ch.fix:
                fixes.append((ch.max_points - ch.points, ch.fix))
    result.fixes = sorted(fixes, key=lambda f: -f[0])
    return result
