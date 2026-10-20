"""LinkedIn / Indeed / Google Jobs / ZipRecruiter / Glassdoor via python-jobspy, plus SimplifyJobs."""
import logging
import time

from ..common import SESSION, TIMEOUT, make_job

log = logging.getLogger(__name__)

SIMPLIFY_URLS = [
    "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json",
    "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/main/.github/scripts/listings.json",
]


def simplify(urls=None):
    for url in urls or SIMPLIFY_URLS:
        try:
            r = SESSION.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            data = r.json()
            break
        except Exception as e:
            log.warning("simplify %s failed: %s", url, e)
    else:
        return []
    cutoff = time.time() - 60 * 86400  # last 60 days only
    out = []
    for j in data:
        if not j.get("active", True) or not j.get("is_visible", True):
            continue
        if (j.get("date_posted") or 0) < cutoff:
            continue
        locs = j.get("locations") or []
        out.append(make_job("github-lists", j.get("company_name"), j.get("title"), "; ".join(locs),
                            j.get("url"), "new grad entry level", j.get("date_posted"),
                            any("remote" in l.lower() for l in locs)))
    return out


def jobspy_all(cfg):
    from jobspy import scrape_jobs  # imported lazily: heavy

    js = cfg["jobspy"]
    out = []
    for site in js["sites"]:
        for term in cfg["search_terms"]:
            try:
                df = scrape_jobs(
                    site_name=[site],
                    search_term=term,
                    google_search_term=f"{term} jobs in United States since yesterday",
                    location="United States",
                    results_wanted=js["results_per_term"],
                    hours_old=js["hours_old"],
                    country_indeed="USA",
                    linkedin_fetch_description=False,
                    verbose=0,
                )
            except Exception as e:
                log.warning("jobspy %s / %r failed: %s", site, term, e)
                continue
            for row in df.fillna("").to_dict("records"):
                out.append(make_job(site, str(row.get("company")), str(row.get("title")),
                                    str(row.get("location")), str(row.get("job_url")),
                                    str(row.get("description")), row.get("date_posted") or None,
                                    bool(row.get("is_remote")) if row.get("is_remote") != "" else None))
            time.sleep(2)  # be polite, avoid rate limits
    return out
