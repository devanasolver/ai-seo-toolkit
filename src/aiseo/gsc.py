"""Google Search Console from the command line. Free Google API, your own data.

Approach (OAuth desktop flow, token cached on disk, plain CLI instead of an
MCP server) adapted from the MIT-licensed mcp-gsc by Amin Foroutan; see NOTICE.
Code written from scratch for a simpler command-line use.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta

CONFIG_DIR = os.environ.get("AISEO_CONFIG_DIR") or os.path.join(
    os.path.expanduser("~"), ".config", "aiseo"
)
TOKEN_FILE = os.path.join(CONFIG_DIR, "gsc_token.json")
SCOPES = ["https://www.googleapis.com/auth/webmasters"]


def _require_gsc_deps():
    try:
        import google.oauth2.credentials  # noqa: F401
        import google_auth_oauthlib.flow  # noqa: F401
        import googleapiclient.discovery  # noqa: F401
    except ImportError:
        raise SystemExit(
            "Search Console needs extra packages. Install them with:\n"
            "  pip install \"ai-seo-toolkit[gsc]\"\n"
            "(or: pip install google-api-python-client google-auth-oauthlib)"
        )


def _credentials():
    """Load saved OAuth token, refreshing or re-running the flow when needed."""
    _require_gsc_deps()
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    secrets_file = os.environ.get("AISEO_GSC_CLIENT_SECRETS") or os.path.join(
        CONFIG_DIR, "client_secrets.json"
    )
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
    if not creds or not creds.valid:
        if not os.path.exists(secrets_file):
            raise SystemExit(
                "No Google sign-in yet.\n"
                "1. Open https://console.cloud.google.com/apis/credentials\n"
                "2. Create an OAuth client (type: Desktop app) and download the JSON.\n"
                f"3. Save it as: {secrets_file}\n"
                "4. Run: aiseo gsc auth\n"
                "(Search Console API must be enabled in that Google Cloud project.)"
            )
        flow = InstalledAppFlow.from_client_secrets_file(secrets_file, SCOPES)
        creds = flow.run_local_server(port=0)
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(TOKEN_FILE, "w") as fh:
        fh.write(creds.to_json())
    return creds


def _service():
    _require_gsc_deps()
    from googleapiclient.discovery import build

    return build("searchconsole", "v1", credentials=_credentials(), cache_discovery=False)


def list_properties() -> list[dict]:
    sites = _service().sites().list().execute().get("siteEntry", [])
    return [{"site_url": s.get("siteUrl"), "permission": s.get("permissionLevel")} for s in sites]


def search_analytics(site_url: str, days: int = 28, dimensions: str = "query", row_limit: int = 25) -> dict:
    end = date.today() - timedelta(days=3)  # last 3 days are incomplete in GSC
    start = end - timedelta(days=days)
    dims = [d.strip() for d in dimensions.split(",") if d.strip()]
    body = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dimensions": dims,
        "rowLimit": row_limit,
    }
    resp = _service().searchanalytics().query(siteUrl=site_url, body=body).execute()
    rows = [
        {
            "keys": r.get("keys", []),
            "clicks": r.get("clicks", 0),
            "impressions": r.get("impressions", 0),
            "ctr": round(r.get("ctr", 0) * 100, 2),
            "position": round(r.get("position", 0), 1),
        }
        for r in resp.get("rows", [])
    ]
    return {"site_url": site_url, "start": start.isoformat(), "end": end.isoformat(), "rows": rows}


def list_sitemaps(site_url: str) -> list[dict]:
    resp = _service().sitemaps().list(siteUrl=site_url).execute()
    return [
        {
            "path": s.get("path"),
            "last_submitted": s.get("lastSubmitted"),
            "is_pending": s.get("isPending"),
            "warnings": s.get("warnings"),
            "errors": s.get("errors"),
        }
        for s in resp.get("sitemap", [])
    ]


def inspect_url(site_url: str, page_url: str) -> dict:
    body = {"inspectionUrl": page_url, "siteUrl": site_url}
    resp = _service().urlInspection().index().inspect(body=body).execute()
    result = resp.get("inspectionResult", {})
    index = result.get("indexStatusResult", {})
    return {
        "url": page_url,
        "verdict": index.get("verdict"),
        "coverage_state": index.get("coverageState"),
        "indexing_state": index.get("indexingState"),
        "last_crawl": index.get("lastCrawlTime"),
        "page_fetch_state": index.get("pageFetchState"),
        "referring_urls": (index.get("referringUrls") or [])[:5],
    }


def to_json(data) -> str:
    return json.dumps(data, indent=2, default=str)
