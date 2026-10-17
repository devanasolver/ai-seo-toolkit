"""aiseo command line: audit, keywords, gsc."""

from __future__ import annotations

import click

from . import __version__


@click.group()
@click.version_option(__version__, prog_name="aiseo")
def main():
    """Free AI-search + SEO toolkit. Audit any site, research keywords, read Search Console."""


@main.command()
@click.argument("url")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def audit(url: str, as_json: bool):
    """Score how visible a website is to AI search engines (0-100) and list fixes."""
    from .audit import audit as run_audit
    from .report import format_json, format_text

    result = run_audit(url)
    click.echo(format_json(result) if as_json else format_text(result))
    raise SystemExit(0 if result.band != "Critical" else 1)


@main.command()
@click.argument("seed")
@click.option("--no-alphabet", is_flag=True, help="Skip a-z expansion (faster).")
@click.option("--no-questions", is_flag=True, help="Skip question-style expansion.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def keywords(seed: str, no_alphabet: bool, no_questions: bool, as_json: bool):
    """Free keyword ideas for a topic, from Google autocomplete."""
    from .keywords import expand_keywords

    rows = expand_keywords(seed, alphabet=not no_alphabet, questions=not no_questions)
    if as_json:
        import json

        click.echo(json.dumps(rows, indent=2))
    else:
        click.echo(f"{len(rows)} keyword ideas for '{seed}':\n")
        for row in rows:
            click.echo(f"  {row['keyword']}")


@main.group()
def gsc():
    """Google Search Console: your own search data, no paid tools."""


@gsc.command("auth")
def gsc_auth():
    """Sign in with Google once; the token is saved on your computer."""
    from .gsc import list_properties

    props = list_properties()
    click.echo(f"Signed in. {len(props)} Search Console properties found:")
    for p in props:
        click.echo(f"  {p['site_url']}  ({p['permission']})")


@gsc.command("properties")
def gsc_properties():
    """List your Search Console properties."""
    from .gsc import list_properties, to_json

    click.echo(to_json(list_properties()))


@gsc.command("analytics")
@click.argument("site_url")
@click.option("--days", default=28, show_default=True, help="How far back to look.")
@click.option("--dimensions", default="query", show_default=True,
              help="query, page, country, device, date, or a comma mix like query,page")
@click.option("--limit", default=25, show_default=True)
def gsc_analytics(site_url: str, days: int, dimensions: str, limit: int):
    """Top queries/pages: clicks, impressions, CTR, position."""
    from .gsc import search_analytics, to_json

    click.echo(to_json(search_analytics(site_url, days, dimensions, limit)))


@gsc.command("sitemaps")
@click.argument("site_url")
def gsc_sitemaps(site_url: str):
    """Sitemaps Google knows about, with errors and warnings."""
    from .gsc import list_sitemaps, to_json

    click.echo(to_json(list_sitemaps(site_url)))


@gsc.command("inspect")
@click.argument("site_url")
@click.argument("page_url")
def gsc_inspect(site_url: str, page_url: str):
    """Is a page indexed? Verdict, coverage, last crawl."""
    from .gsc import inspect_url, to_json

    click.echo(to_json(inspect_url(site_url, page_url)))


if __name__ == "__main__":
    main()
