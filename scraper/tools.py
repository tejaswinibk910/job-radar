"""Helpers.
  python -m scraper.tools validate        -> checks every company in companies.yaml responds
  python -m scraper.tools detect <url>    -> guesses which ATS a careers page uses + the slug
  python -m scraper.tools rescore         -> re-scores all stored jobs after you change resume.txt/config.yaml
  python -m scraper.tools discover        -> tests every name in companies_wishlist.txt, writes companies.discovered.yaml
"""
import re
import sys

from .common import SESSION, TIMEOUT, load_yaml
from .sources import ats

PATTERNS = {
    "greenhouse": r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board\?for=)?([\w-]+)",
    "lever": r"jobs\.lever\.co/([\w-]+)",
    "ashby": r"jobs\.ashbyhq\.com/([\w.-]+)",
    "workday": r"([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([\w-]+)",
    "smartrecruiters": r"(?:jobs|careers)\.smartrecruiters\.com/([\w-]+)",
}


def detect(url):
    html = url + " " + SESSION.get(url, timeout=TIMEOUT, headers={"Accept": "text/html"}).text
    found = False
    for name, pat in PATTERNS.items():
        for m in set(re.findall(pat, html)):
            found = True
            if name == "workday":
                t, wd, site = m
                print(f"workday: - {{name: {t.title()}, tenant: {t}, wd: {wd}, site: {site}}}")
            else:
                print(f"{name}: - {m}")
    if not found:
        print("No known ATS found. The site may be custom or load jobs with JavaScript.\n"
              "Try clicking a job on their site and running detect on that job's URL.")


def validate():
    cfg, c = load_yaml("config.yaml"), load_companies()
    always = lambda t: True
    checks = [(f"greenhouse:{s}", lambda s=s: ats.greenhouse(s)) for s in c.get("greenhouse") or []]
    checks += [(f"lever:{s}", lambda s=s: ats.lever(s)) for s in c.get("lever") or []]
    checks += [(f"ashby:{s}", lambda s=s: ats.ashby(s)) for s in c.get("ashby") or []]
    checks += [(f"workday:{w['name']}", lambda w=w: ats.workday(w, cfg["ats_search_terms"][:1], lambda t: False))
               for w in c.get("workday") or []]
    checks += [(f"smartrecruiters:{s}", lambda s=s: ats.smartrecruiters(s, ["engineer"], lambda t: False))
               for s in c.get("smartrecruiters") or []]
    bad = []
    for label, fn in checks:
        try:
            n = len(fn())
            print(f"OK    {label} ({n} postings)" if n else f"OK    {label}")
        except Exception as e:
            bad.append(label)
            print(f"FAIL  {label}: {e}")
    print(f"\n{len(checks) - len(bad)}/{len(checks)} OK. Fix or remove: {', '.join(bad) or 'none'}")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "detect":
        detect(sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1] == "validate":
        validate()
    elif len(sys.argv) < 2 or sys.argv[1] not in ("discover", "rescore"):
        print(__doc__)


# ---------------- discovery ----------------
import concurrent.futures as cf  # noqa: E402

import yaml  # noqa: E402

from .common import ROOT  # noqa: E402

PROBES = {
    "greenhouse": lambda s: SESSION.get(f"https://boards-api.greenhouse.io/v1/boards/{s}/jobs", timeout=15),
    "lever": lambda s: SESSION.get(f"https://api.lever.co/v0/postings/{s}?mode=json&limit=5", timeout=15),
    "ashby": lambda s: SESSION.get(f"https://api.ashbyhq.com/posting-api/job-board/{s}", timeout=15),
    "smartrecruiters": lambda s: SESSION.get(f"https://api.smartrecruiters.com/v1/companies/{s}/postings?limit=1", timeout=15),
}


def _count(ats, r):
    if r.status_code != 200:
        return 0
    try:
        d = r.json()
    except Exception:
        return 0
    if ats == "greenhouse":
        return len(d.get("jobs", []))
    if ats == "lever":
        return len(d) if isinstance(d, list) else 0
    if ats == "ashby":
        return len(d.get("jobs", []))
    return d.get("totalFound", 0)


def _slugs(line):
    name, _, extra = line.partition("|")
    name = name.strip()
    base = re.sub(r"[^a-z0-9 ]", "", name.lower())
    cands = [base.replace(" ", ""), base.replace(" ", "-"), name.replace(" ", "")]
    cands += [e.strip() for e in extra.split(",") if e.strip()]
    seen, out = set(), []
    for c in cands:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return name, out


def discover():
    existing = load_yaml("companies.yaml")
    known = {(a, str(s).lower()) for a in PROBES for s in existing.get(a) or []}
    lines = [l.strip() for l in (ROOT / "companies_wishlist.txt").read_text().splitlines()
             if l.strip() and not l.startswith("#")]
    if "--no-yc" not in sys.argv:
        from .sources.startups import yc_hiring_companies
        yc = yc_hiring_companies()
        print(f"Added {len(yc)} hiring YC companies in AI/CV/robotics/infra to the search")
        lines += yc
    tasks = [(name, ats, slug) for line in lines for name, slugs in [_slugs(line)]
             for ats in PROBES for slug in slugs if (ats, slug.lower()) not in known]

    def probe(t):
        name, ats, slug = t
        try:
            return name, ats, slug, _count(ats, PROBES[ats](slug))
        except Exception:
            return name, ats, slug, 0

    hits = {}  # name -> (ats, slug, n) best board
    with cf.ThreadPoolExecutor(max_workers=16) as pool:
        for name, ats, slug, n in pool.map(probe, tasks):
            if n and (name not in hits or n > hits[name][2]):
                hits[name] = (ats, slug, n)

    found = {a: [] for a in PROBES}
    for name, (ats, slug, n) in sorted(hits.items()):
        found[ats].append(slug)
        print(f"FOUND {name:28} {ats:16} {slug} ({n} jobs)")
    missing = [n for n, _ in (_slugs(l) for l in lines) if n not in hits]
    out = {a: sorted(set(v)) for a, v in found.items() if v}
    (ROOT / "companies.discovered.yaml").write_text(
        "# Auto-generated by `python -m scraper.tools discover`. Merged with companies.yaml at runtime.\n"
        + yaml.safe_dump(out, sort_keys=True))
    print(f"\n{len(hits)} new boards written to companies.discovered.yaml")
    print(f"Not found ({len(missing)}; likely Workday/custom/no openings; LinkedIn/Indeed/HN still cover them):\n  "
          + ", ".join(missing[:300]))


def load_companies():
    """companies.yaml + companies.discovered.yaml, merged and de-duplicated."""
    c = load_yaml("companies.yaml") or {}
    p = ROOT / "companies.discovered.yaml"
    if p.exists():
        for ats, items in (yaml.safe_load(p.read_text()) or {}).items():
            cur = c.setdefault(ats, []) or []
            seen = {str(x).lower() for x in cur}
            cur += [x for x in items if str(x).lower() not in seen]
            c[ats] = cur
    return c


if __name__ == "__main__" and len(sys.argv) >= 2 and sys.argv[1] == "discover":
    discover()


# ---------------- rescore ----------------
def rescore():
    """Re-scores every stored job with the current resume.txt + config.yaml. Hides jobs now classed Senior."""
    import os

    from supabase import create_client

    from .matcher import Matcher
    from .seniority import classify

    url = re.match(r"\s*(https://[^/\s]+)", os.environ["SUPABASE_URL"]).group(1)
    db = create_client(url, os.environ["SUPABASE_KEY"].strip())
    cfg = load_yaml("config.yaml")
    rows, start = [], 0
    while True:
        batch = db.table("jobs").select("id,title,company,description").range(start, start + 999).execute().data
        rows += batch
        if len(batch) < 1000:
            break
        start += 1000
    print(f"Rescoring {len(rows)} jobs")
    for r in rows:
        r["description"] = r.get("description") or ""
    Matcher((ROOT / "resume.txt").read_text(), cfg).score(rows)
    updates = []
    for r in rows:
        senior = classify(r["title"], r["description"], cfg["seniority"]["max_years"])[0] == "Senior"
        updates.append({"id": r["id"], "score": r["score"], "category": r["category"],
                        "seniority": r["seniority"], "matched_keywords": r["matched_keywords"],
                        **({"hidden": True} if senior else {})})
    hidden = sum(1 for u in updates if u.get("hidden"))
    for n, u in enumerate(updates, 1):  # row-by-row partial updates; ~2k rows takes a few minutes
        uid = u.pop("id")
        db.table("jobs").update(u).eq("id", uid).execute()
        if n % 500 == 0:
            print(f"  {n}/{len(updates)}")
    print(f"Done. {hidden} jobs hidden as Senior.")


if __name__ == "__main__" and len(sys.argv) >= 2 and sys.argv[1] == "rescore":
    rescore()
