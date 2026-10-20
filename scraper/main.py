"""Daily run: scrape all sources -> filter -> dedupe -> score new jobs -> store in Supabase."""
import logging
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

from supabase import create_client

from .common import ROOT, load_yaml
from .filters import Filters
from .matcher import Matcher
from .sources import aggregators, ats

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("job-radar")


def collect(cfg, companies, flt):
    tasks = []  # (label, fn)
    for s in companies.get("greenhouse") or []:
        tasks.append((f"greenhouse:{s}", lambda s=s: ats.greenhouse(s)))
    for s in companies.get("lever") or []:
        tasks.append((f"lever:{s}", lambda s=s: ats.lever(s)))
    for s in companies.get("ashby") or []:
        tasks.append((f"ashby:{s}", lambda s=s: ats.ashby(s)))
    for c in companies.get("workday") or []:
        tasks.append((f"workday:{c['name']}", lambda c=c: ats.workday(c, cfg["ats_search_terms"], flt.title_ok)))
    for c in companies.get("smartrecruiters") or []:
        tasks.append((f"smartrecruiters:{c}", lambda c=c: ats.smartrecruiters(c, cfg["ats_search_terms"], flt.title_ok)))
    tasks.append(("simplify", aggregators.simplify))

    jobs, failed = [], []

    def run(task):
        label, fn = task
        try:
            res = fn()
            log.info("%-32s %4d jobs", label, len(res))
            return res
        except Exception as e:
            failed.append(label)
            log.warning("%-32s FAILED: %s", label, e)
            return []

    with ThreadPoolExecutor(max_workers=8) as pool:
        for res in pool.map(run, tasks):
            jobs.extend(res)

    # aggregators run sequentially (rate limits)
    try:
        agg = aggregators.jobspy_all(cfg)
        log.info("%-32s %4d jobs", "jobspy (linkedin/indeed/...)", len(agg))
        jobs.extend(agg)
    except Exception as e:
        failed.append("jobspy")
        log.warning("jobspy FAILED: %s", e)
    return jobs, failed


def existing_ids(db, ids):
    found = set()
    ids = list(ids)
    for i in range(0, len(ids), 200):
        res = db.table("jobs").select("id").in_("id", ids[i:i + 200]).execute()
        found.update(r["id"] for r in res.data)
    return found


def main():
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not url or not key:
        sys.exit("Set SUPABASE_URL and SUPABASE_KEY env vars.")
    m = re.match(r"\s*(https://[^/\s]+)", url)
    if not m:
        sys.exit(f"SUPABASE_URL should look like https://abcd.supabase.co")
    db = create_client(m.group(1), key.strip())
    try:  # fail fast before spending 15 min scraping
        db.table("jobs").select("id").limit(1).execute()
    except Exception as e:
        sys.exit(f"Can't reach the jobs table. Check SUPABASE_URL/SUPABASE_KEY and that schema.sql ran. ({e})")

    cfg, companies = load_yaml("config.yaml"), load_yaml("companies.yaml")
    flt = Filters(cfg)

    raw, failed = collect(cfg, companies, flt)
    kept = {}
    for j in raw:
        if j["title"] and j["url"] and flt.keep(j):
            # prefer the copy with the longer description when duplicated across sources
            if j["id"] not in kept or len(j["description"]) > len(kept[j["id"]]["description"]):
                kept[j["id"]] = j
    log.info("raw=%d  after filters+dedupe=%d", len(raw), len(kept))

    new_ids = set(kept) - existing_ids(db, kept.keys())
    new = [kept[i] for i in new_ids]
    log.info("new jobs: %d", len(new))
    if not new:
        return

    resume = (ROOT / "resume.txt").read_text()
    Matcher(resume, cfg).score(new)

    for i in range(0, len(new), 300):
        db.table("jobs").upsert(new[i:i + 300], on_conflict="id", ignore_duplicates=True).execute()

    top = sorted(new, key=lambda j: j["score"], reverse=True)[:10]
    log.info("Top new matches:")
    for j in top:
        log.info("  %5.1f  %s @ %s (%s)", j["score"], j["title"], j["company"], j["location"])
    if failed:
        log.info("Failed sources (%d): %s", len(failed), ", ".join(failed))


if __name__ == "__main__":
    main()
