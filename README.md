# Job Radar

Daily job scraper + resume matcher + application tracker.

```
GitHub Actions (daily 7am ET)
  └─ scraper/  → Greenhouse, Lever, Ashby, Workday, SmartRecruiters (direct company APIs)
              → LinkedIn, Indeed, Google Jobs, ZipRecruiter, Glassdoor (python-jobspy)
              → SimplifyJobs New-Grad list
     filter (US/remote, no clearance, no senior titles) → dedupe → score vs resume.txt
        └─ Supabase Postgres (every job ever seen + your applications)
              └─ Streamlit dashboard: New | Archive | Tracker
```

Ranking: semantic similarity to your resume (up to 70 pts) + keyword boosts (up to 25)
+ role tier (CV/Perception +6, ML/AI +3, SWE −12) − penalties (5+ yrs, PhD required).
All tunable in `config.yaml`.

---

## Setup (about 20 minutes, all free)

### 1. GitHub: create a private repo
1. Sign in at github.com → top right **+** → **New repository**.
2. Name it `job-radar`, choose **Private**, click **Create repository**.
3. On the new repo page click **uploading an existing file**, drag in everything from this folder
   (including the hidden `.github` folder: on Mac press `Cmd+Shift+.` in Finder to show it), commit.
   Or with git:
   ```bash
   cd job-radar
   git init && git add . && git commit -m "init"
   git branch -M main
   git remote add origin https://github.com/<you>/job-radar.git
   git push -u origin main
   ```

### 2. Supabase: create the database
1. Go to supabase.com → **Start your project** → sign in with GitHub.
2. **New project**: name `job-radar`, set a database password (save it anywhere), region **East US**. Wait ~2 min.
3. Left sidebar → **SQL Editor** → **New query** → paste all of `schema.sql` → **Run**.
4. Left sidebar → **Project Settings** → **API Keys**. Copy:
   - **Project URL** (also shown under Settings → Data API), e.g. `https://abcd.supabase.co`
   - the **secret** key (`sb_secret_...`). On older projects this is the `service_role` key.
   Keep it private: it has full access to your database.

### 3. Connect GitHub Actions to Supabase
1. In your GitHub repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.
2. Add `SUPABASE_URL` = your project URL.
3. Add `SUPABASE_KEY` = the secret key.
4. Go to the **Actions** tab → **daily-job-scrape** → **Run workflow**. First run takes ~10–20 min
   (it fills the archive). Open the run's log to see counts per source and the top 10 matches.

### 4. Streamlit: host the dashboard
1. Go to share.streamlit.io → sign in with GitHub → **Create app** → **Deploy a public app from GitHub**.
2. Repo `job-radar`, branch `main`, main file path `dashboard/app.py`.
3. **Advanced settings → Secrets**, paste:
   ```toml
   SUPABASE_URL = "https://abcd.supabase.co"
   SUPABASE_KEY = "sb_secret_..."
   APP_PASSWORD = "something-only-you-know"
   ```
4. **Deploy**. Bookmark the URL. The password gate keeps it private.

Done. It now runs every morning on its own.

---

## Daily use
- **New**: jobs found in the last 1/3/7 days, best match first. **Applied** → moves it to Tracker. **Hide** → never see it again.
- **Archive**: every posting ever scraped, searchable, sorted by match. This is your "old postings that fit my resume" view.
- **Tracker**: change status (Saved → Applied → OA → Interview → Offer/Rejected), add notes, **Save changes**. Add jobs you found elsewhere via "Add manually".

## Adding companies
```bash
pip install -r scraper/requirements.txt
python -m scraper.tools detect https://careers.somecompany.com   # prints the line to add to companies.yaml
python -m scraper.tools validate                                 # checks every entry; remove the FAILs
```
Most companies use Greenhouse, Lever, Ashby, Workday or SmartRecruiters, so `detect` handles the majority.
Fully custom career sites (Google, Meta, Apple, Amazon, Microsoft) are covered through LinkedIn/Indeed/Google Jobs instead.

## Tuning
- Too many SWE roles? Make the SWE tier more negative in `config.yaml`, or untick it in the sidebar.
- Too few results? Lower `sim_floor` or the dashboard min score.
- New resume? Replace `resume.txt`. New jobs get scored against it from the next run.
- Run locally: `SUPABASE_URL=... SUPABASE_KEY=... python -m scraper.main`

## Notes
- LinkedIn blocks scrapers and it's against their ToS. jobspy usually works at this low volume, but if LinkedIn
  fails in the logs everything else still runs. Glassdoor breaks often; same deal.
- GitHub pauses scheduled workflows after 60 days with no commits. If runs stop, push any small change
  (or hit Run workflow).
- Supabase free projects pause after 7 days of no activity; the daily scraper counts as activity.
