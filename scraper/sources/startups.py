"""Startup sources: Hacker News 'Who is Hiring' + YC hiring company list (for board discovery)."""
import html as htmllib
import logging
import re

from ..common import SESSION, TIMEOUT, make_job, strip_html

log = logging.getLogger(__name__)

LOC_HINT = re.compile(r"remote|onsite|on-site|hybrid|in.office|\b[A-Z]{2}\b|united states|\busa?\b|new york|"
                      r"san francisco|sf\b|bay area|nyc|boston|seattle|austin|los angeles|la\b", re.I)


def hackernews(role_patterns):
    hits = SESSION.get("https://hn.algolia.com/api/v1/search_by_date",
                       params={"tags": "story,author_whoishiring", "hitsPerPage": 10}, timeout=TIMEOUT).json()["hits"]
    story = next(h for h in hits if "who is hiring" in (h.get("title") or "").lower())
    item = SESSION.get(f"https://hn.algolia.com/api/v1/items/{story['objectID']}", timeout=60).json()
    out = []
    for c in item.get("children", []):
        raw = c.get("text") or ""
        if not raw:
            continue
        first = strip_html(htmllib.unescape(raw).split("<p>")[0])
        parts = [p.strip() for p in re.split(r"\s+[|•]\s+", first) if p.strip()]
        if len(parts) < 2:
            continue
        text = strip_html(raw)
        roles = [p for p in parts[1:] if any(r.search(p) for r in role_patterns)]
        if not roles and not any(r.search(text[:600]) for r in role_patterns):
            continue
        title = roles[0] if roles else parts[1]
        others = [p for p in parts[1:] if p not in roles and p != title]
        locs = [p for p in others if LOC_HINT.search(p)] or others  # fall back so "London" still gets checked
        location = " | ".join(locs)[:200]
        out.append(make_job("hackernews", parts[0][:80], title[:200], location,
                            f"https://news.ycombinator.com/item?id={c['id']}", text, c.get("created_at"),
                            "remote" in first.lower()))
    return out


YC_URLS = ["https://yc-oss.github.io/api/companies/hiring.json",
           "https://yc-oss.github.io/api/companies/all.json"]
YC_RELEVANT = re.compile(r"\bai\b|artificial intelligence|machine learning|computer vision|robot|autonom|drone|"
                         r"\bvision\b|\bllm|generative|deep learning|perception|lidar|imaging|geospatial|"
                         r"satellite|3d|spatial|healthcare|medical|developer tools|infrastructure", re.I)


def yc_hiring_companies():
    """Returns wishlist-style lines ('Name | slug1, slug2') for hiring YC companies in relevant spaces."""
    data = None
    for url in YC_URLS:
        try:
            data = SESSION.get(url, timeout=60).json()
            break
        except Exception as e:
            log.warning("yc list %s failed: %s", url, e)
    if not data:
        return []
    lines = []
    for co in data:
        if not co.get("isHiring", True) or (co.get("status") or "Active") not in ("Active", "Public"):
            continue
        blob = " ".join(str(co.get(k) or "") for k in ("one_liner", "long_description", "industry",
                                                      "subindustry", "tags", "industries"))
        if not YC_RELEVANT.search(blob):
            continue
        extra = [co.get("slug") or ""]
        site = re.sub(r"^https?://(www\.)?", "", co.get("website") or "").split("/")[0]
        if site:
            extra.append(site.split(".")[0])
        name = (co.get("name") or "").replace("|", " ").strip()
        if name:
            lines.append(f"{name} | {', '.join(e for e in extra if e)}")
    return lines
