"""Helpers.
  python -m scraper.tools validate        -> checks every company in companies.yaml responds
  python -m scraper.tools detect <url>    -> guesses which ATS a careers page uses + the slug
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
    cfg, c = load_yaml("config.yaml"), load_yaml("companies.yaml")
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
    else:
        print(__doc__)
