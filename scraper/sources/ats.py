"""Direct career-site APIs. These are public, unauthenticated JSON endpoints."""
import logging
from urllib.parse import quote

from ..common import SESSION, TIMEOUT, make_job, strip_html

log = logging.getLogger(__name__)


def greenhouse(slug):
    r = SESSION.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true", timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        out.append(make_job(
            "greenhouse", j.get("company_name") or slug.title(), j.get("title"),
            (j.get("location") or {}).get("name"), j.get("absolute_url"),
            strip_html(j.get("content")), j.get("first_published"),  # updated_at isn't a post date
        ))
    return out


def lever(slug):
    r = SESSION.get(f"https://api.lever.co/v0/postings/{slug}?mode=json", timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for j in r.json():
        cats = j.get("categories") or {}
        desc = (j.get("descriptionPlain") or "") + " " + " ".join(
            strip_html(l.get("content")) for l in j.get("lists", []))
        out.append(make_job(
            "lever", slug.title(), j.get("text"), cats.get("location"), j.get("hostedUrl"),
            desc, j.get("createdAt"), j.get("workplaceType") == "remote",
        ))
    return out


def ashby(slug):
    r = SESSION.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        if j.get("isListed") is False:
            continue
        out.append(make_job(
            "ashby", slug.title(), j.get("title"), j.get("location"), j.get("jobUrl"),
            j.get("descriptionPlain") or strip_html(j.get("descriptionHtml")),
            j.get("publishedAt"), j.get("isRemote"),
        ))
    return out


def workday(c, terms, title_ok):
    base = f"https://{c['tenant']}.{c['wd']}.myworkdayjobs.com"
    api = f"{base}/wday/cxs/{c['tenant']}/{c['site']}"
    seen, out = set(), []
    for term in terms:
        for offset in range(0, 100, 20):  # up to 100 results per term
            r = SESSION.post(f"{api}/jobs", json={"appliedFacets": {}, "limit": 20, "offset": offset,
                                                  "searchText": term}, timeout=TIMEOUT)
            r.raise_for_status()
            postings = r.json().get("jobPostings", [])
            for p in postings:
                path = p.get("externalPath")
                if not path or path in seen or not title_ok(p.get("title")):
                    continue
                seen.add(path)
                desc, posted = "", None
                try:
                    d = SESSION.get(f"{api}{path}", timeout=TIMEOUT).json().get("jobPostingInfo", {})
                    desc, posted = strip_html(d.get("jobDescription")), d.get("startDate")
                except Exception:
                    pass
                out.append(make_job("workday", c["name"], p.get("title"), p.get("locationsText"),
                                    f"{base}/en-US/{c['site']}{path}", desc, posted))
            if len(postings) < 20:
                break
    return out


def smartrecruiters(company, terms, title_ok):
    seen, out = set(), []
    for term in terms:
        r = SESSION.get(f"https://api.smartrecruiters.com/v1/companies/{company}/postings"
                        f"?q={quote(term)}&limit=100", timeout=TIMEOUT)
        r.raise_for_status()
        for p in r.json().get("content", []):
            if p["id"] in seen or not title_ok(p.get("name")):
                continue
            seen.add(p["id"])
            loc = p.get("location") or {}
            loc_str = ", ".join(x for x in (loc.get("city"), loc.get("region"), loc.get("country")) if x)
            desc = ""
            try:
                d = SESSION.get(f"https://api.smartrecruiters.com/v1/companies/{company}/postings/{p['id']}",
                                timeout=TIMEOUT).json()
                secs = (d.get("jobAd") or {}).get("sections") or {}
                desc = " ".join(strip_html((secs.get(k) or {}).get("text"))
                                for k in ("jobDescription", "qualifications"))
            except Exception:
                pass
            out.append(make_job("smartrecruiters", (p.get("company") or {}).get("name") or company,
                                p.get("name"), loc_str, f"https://jobs.smartrecruiters.com/{company}/{p['id']}",
                                desc, p.get("releasedDate"), loc.get("remote")))
    return out


def amazon(terms, title_ok):
    """amazon.jobs public search endpoint."""
    seen, out = set(), []
    for term in terms:
        r = SESSION.get("https://www.amazon.jobs/en/search.json", params={
            "base_query": term, "loc_query": "United States", "country": "USA",
            "result_limit": 100, "sort": "recent"}, timeout=TIMEOUT)
        r.raise_for_status()
        for j in r.json().get("jobs", []):
            jid = j.get("id_icims") or j.get("job_path")
            if jid in seen or not title_ok(j.get("title")):
                continue
            seen.add(jid)
            desc = " ".join(strip_html(j.get(k)) for k in ("description", "basic_qualifications", "preferred_qualifications"))
            out.append(make_job("amazon", "Amazon", j.get("title"), j.get("normalized_location") or j.get("location"),
                                "https://www.amazon.jobs" + (j.get("job_path") or ""), desc, None))
    return out
