import hashlib
import html
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json",
})
TIMEOUT = 30


def load_yaml(name):
    with open(ROOT / name) as f:
        return yaml.safe_load(f)


def strip_html(s):
    if not s:
        return ""
    s = html.unescape(html.unescape(s))  # Greenhouse double-escapes
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def job_id(company, title, location):
    key = "|".join(x.strip().lower() for x in (company or "", title or "", location or ""))
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def to_iso(value):
    """Accepts epoch seconds/ms, ISO strings, datetime/date. Returns ISO string or None."""
    if value in (None, "", 0):
        return None
    try:
        if isinstance(value, (int, float)):
            if value > 1e12:
                value /= 1000
            return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
        if hasattr(value, "isoformat"):
            return value.isoformat()
        s = str(value)
        return datetime.fromisoformat(s.replace("Z", "+00:00")).isoformat()
    except Exception:
        return None


def make_job(source, company, title, location, url, description="", posted_at=None, is_remote=None):
    location = (location or "").strip()
    return {
        "id": job_id(company, title, location),
        "source": source,
        "company": (company or "").strip(),
        "title": (title or "").strip(),
        "location": location,
        "url": url,
        "description": (description or "")[:6000],
        "posted_at": to_iso(posted_at),
        "is_remote": bool(is_remote) if is_remote is not None else ("remote" in location.lower()),
    }
