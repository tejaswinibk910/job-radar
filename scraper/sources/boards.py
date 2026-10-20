"""Job boards with public APIs: Adzuna (free key), The Muse, Remotive, RemoteOK, Himalayas."""
import logging
import os
import time

from ..common import SESSION, TIMEOUT, make_job, strip_html

log = logging.getLogger(__name__)


def adzuna(terms):
    """Large US aggregator. Free key at developer.adzuna.com. Skipped if no key."""
    app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        log.info("adzuna: no ADZUNA_APP_ID/ADZUNA_APP_KEY set, skipping")
        return []
    out = []
    for term in terms:
        for page in (1, 2):
            r = SESSION.get(f"https://api.adzuna.com/v1/api/jobs/us/search/{page}", timeout=TIMEOUT, params={
                "app_id": app_id, "app_key": app_key, "what": term, "max_days_old": 3,
                "results_per_page": 50, "sort_by": "date", "content-type": "application/json"})
            r.raise_for_status()
            results = r.json().get("results", [])
            for j in results:
                out.append(make_job("adzuna", (j.get("company") or {}).get("display_name"), j.get("title"),
                                    (j.get("location") or {}).get("display_name"), j.get("redirect_url"),
                                    strip_html(j.get("description")), j.get("created")))
            if len(results) < 50:
                break
            time.sleep(1)
    return out


def themuse():
    out = []
    for level in ("Entry Level", "Mid Level"):
        for page in range(10):
            r = SESSION.get("https://www.themuse.com/api/public/jobs", timeout=TIMEOUT,
                            params={"level": level, "page": page, "descending": "true"})
            r.raise_for_status()
            results = r.json().get("results", [])
            for j in results:
                locs = "; ".join(l.get("name", "") for l in j.get("locations", []))
                out.append(make_job("themuse", (j.get("company") or {}).get("name"), j.get("name"), locs,
                                    (j.get("refs") or {}).get("landing_page"), strip_html(j.get("contents")),
                                    j.get("publication_date")))
            if not results:
                break
    return out


def remotive(terms):
    out = []
    for term in terms[:3]:  # Remotive asks for light usage
        r = SESSION.get("https://remotive.com/api/remote-jobs", params={"search": term}, timeout=TIMEOUT)
        r.raise_for_status()
        for j in r.json().get("jobs", []):
            out.append(make_job("remotive", j.get("company_name"), j.get("title"),
                                "Remote: " + (j.get("candidate_required_location") or ""), j.get("url"),
                                strip_html(j.get("description")), j.get("publication_date"), True))
    return out


def remoteok():
    r = SESSION.get("https://remoteok.com/api", timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for j in r.json()[1:]:  # first element is a legal notice
        out.append(make_job("remoteok", j.get("company"), j.get("position"),
                            "Remote: " + (j.get("location") or ""), j.get("url"),
                            strip_html(j.get("description")) + " " + " ".join(j.get("tags") or []),
                            j.get("date"), True))
    return out


def himalayas():
    out = []
    for offset in range(0, 400, 20):
        r = SESSION.get("https://himalayas.app/jobs/api", params={"limit": 20, "offset": offset}, timeout=TIMEOUT)
        r.raise_for_status()
        jobs = r.json().get("jobs", [])
        for j in jobs:
            locs = j.get("locationRestrictions") or []
            out.append(make_job("himalayas", j.get("companyName"), j.get("title"),
                                "Remote: " + (", ".join(locs) if locs else "Worldwide"),
                                j.get("applicationLink") or j.get("guid"), strip_html(j.get("description")),
                                j.get("pubDate"), True))
        if len(jobs) < 20:
            break
    return out
