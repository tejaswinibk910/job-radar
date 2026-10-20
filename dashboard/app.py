import datetime as dt
import re
from urllib.parse import quote_plus

import requests

import pandas as pd
import streamlit as st
from supabase import create_client

st.set_page_config(page_title="Job Radar", page_icon="🎯", layout="wide")

STATUSES = ["Saved", "Applied", "OA", "Interview", "Offer", "Rejected", "Withdrawn"]
CATEGORIES = ["CV / Perception", "ML / AI", "SWE"]


# ---------- auth + db ----------
def gate():
    pw = st.secrets.get("APP_PASSWORD")
    if not pw or st.session_state.get("authed"):
        return
    entered = st.text_input("Password", type="password")
    if entered == pw:
        st.session_state.authed = True
        st.rerun()
    elif entered:
        st.error("Wrong password")
    st.stop()


@st.cache_resource
def db():
    url = re.match(r"\s*(https://[^/\s]+)", st.secrets["SUPABASE_URL"]).group(1)
    return create_client(url, st.secrets["SUPABASE_KEY"].strip())


def refresh():
    st.cache_data.clear()


# ---------- queries ----------
@st.cache_data(ttl=300)
def applied_job_ids():
    rows = db().table("applications").select("job_id").not_.is_("job_id", "null").execute().data
    return {r["job_id"] for r in rows}


@st.cache_data(ttl=300)
def new_jobs(since, min_score, cats):
    q = (db().table("jobs").select("*").gte("first_seen", since.isoformat()).eq("hidden", False)
         .gte("score", min_score).order("score", desc=True).limit(300))
    if cats:
        q = q.in_("category", cats)
    return q.execute().data


@st.cache_data(ttl=300)
def archive_jobs(text, min_score, cats, sources, days, sort, page, page_size=25):
    q = db().table("jobs").select("*", count="exact").eq("hidden", False).gte("score", min_score)
    if text:
        t = re.sub(r"[,()%*]", " ", text).strip()
        q = q.or_(f"title.ilike.*{t}*,company.ilike.*{t}*,description.ilike.*{t}*")
    if cats:
        q = q.in_("category", cats)
    if sources:
        q = q.in_("source", sources)
    if days:
        q = q.gte("first_seen", (dt.date.today() - dt.timedelta(days=days)).isoformat())
    q = q.order("score" if sort == "Best match" else "first_seen", desc=True)
    res = q.range(page * page_size, page * page_size + page_size - 1).execute()
    return res.data, res.count or 0


@st.cache_data(ttl=300)
def applications():
    return db().table("applications").select("*").order("applied_on", desc=True).execute().data


@st.cache_data(ttl=3600)
def all_sources():
    rows = db().table("jobs").select("source").limit(5000).execute().data
    return sorted({r["source"] for r in rows if r["source"]})


# ---------- actions ----------
def mark_applied(job):
    try:
        db().table("applications").insert({
            "job_id": job["id"], "company": job["company"], "title": job["title"],
            "url": job["url"], "status": "Applied",
        }).execute()
        st.toast(f"Tracked: {job['title']} @ {job['company']}")
    except Exception:
        st.toast("Already in your tracker")
    refresh()


def hide_job(job):
    db().table("jobs").update({"hidden": True}).eq("id", job["id"]).execute()
    refresh()


# ---------- people finder ----------
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
GENERIC_INBOX = re.compile(r"^(noreply|no-reply|privacy|accommodations?|legal|support|info|security|benefits)@", re.I)
RELEVANT_POS = re.compile(r"machine learning|\bml\b|\bai\b|vision|perception|data|research|engineer|"
                          r"cto|founder|head|vp|director|manager|recruit|talent|hiring|people", re.I)


def team_phrase(job):
    cat = job.get("category") or ""
    return "computer vision" if cat.startswith("CV") else "machine learning" if cat.startswith("ML") else "engineering"


def search_links(job):
    co, team = job["company"], team_phrase(job)
    li = "https://www.linkedin.com/search/results/people/?keywords="
    g = "https://www.google.com/search?q="
    return {
        "LinkedIn: hiring managers": li + quote_plus(f"{co} {team} manager"),
        "LinkedIn: recruiters": li + quote_plus(f"{co} technical recruiter"),
        "LinkedIn: team members": li + quote_plus(f"{co} {team} engineer"),
        "Google: managers & leads": g + quote_plus(
            f'site:linkedin.com/in "{co}" ("engineering manager" OR "head of" OR "lead" OR founder) "{team}"'),
        "Google: recruiters": g + quote_plus(f'site:linkedin.com/in "{co}" (recruiter OR "talent acquisition")'),
    }


def emails_in_posting(job):
    found = {e.rstrip(".") for e in EMAIL_RE.findall(job.get("description") or "")}
    return sorted(e for e in found if not GENERIC_INBOX.match(e))


@st.cache_data(ttl=3600)
def cached_contacts(company):
    rows = db().table("contacts").select("results").eq("company", company.lower()).execute().data
    return rows[0]["results"] if rows else None


def hunter_lookup(company):
    r = requests.get("https://api.hunter.io/v2/domain-search", timeout=20, params={
        "company": company, "type": "personal", "limit": 25, "api_key": st.secrets["HUNTER_API_KEY"]})
    r.raise_for_status()
    people = []
    for e in r.json().get("data", {}).get("emails", []):
        if not RELEVANT_POS.search(e.get("position") or ""):
            continue
        people.append({k: e.get(k) for k in ("first_name", "last_name", "position", "value",
                                              "linkedin", "confidence")})
    people.sort(key=lambda p: -(p.get("confidence") or 0))
    db().table("contacts").upsert({"company": company.lower(), "results": people,
                                   "fetched_at": dt.datetime.utcnow().isoformat()}).execute()
    st.cache_data.clear()


def people_panel(job, key):
    st.markdown(f"**People at {job['company']}**")
    emails = emails_in_posting(job)
    if emails:
        st.markdown("In the posting: " + ", ".join(f"`{e}`" for e in emails))
    for label, url in search_links(job).items():
        st.markdown(f"- [{label}]({url})")
    if "HUNTER_API_KEY" in st.secrets:
        try:
            cached = cached_contacts(job["company"])
        except Exception:
            cached = None
            st.caption("Run migration_002_contacts.sql in Supabase to enable saved lookups.")
        if cached is None:
            if st.button("Look up emails (uses 1 Hunter credit)", key=f"hu-{key}"):
                try:
                    hunter_lookup(job["company"])
                    st.rerun()
                except Exception as e:
                    st.error(f"Hunter lookup failed: {e}")
        elif not cached:
            st.caption("Hunter found no relevant people for this company.")
        else:
            for p in cached[:8]:
                name = f"{p.get('first_name') or ''} {p.get('last_name') or ''}".strip() or "Unknown"
                li = f" · [LinkedIn]({p['linkedin']})" if p.get("linkedin") else ""
                st.markdown(f"- **{name}**, {p.get('position') or ''}  \n  `{p.get('value')}` "
                            f"({p.get('confidence') or '?'}% confidence){li}")
    st.caption("Verify before reaching out: the person hiring for this exact role may not show up here.")


# ---------- ui pieces ----------
def job_card(job, key):
    with st.container(border=True):
        left, right = st.columns([6, 1])
        title = (job["title"] or "").replace("[", "(").replace("]", ")")
        left.markdown(f"**[{title}]({job['url']})**  \n{job['company']}")
        posted = (job.get("posted_at") or "")[:10] or "unknown"
        left.caption(f"{job['location'] or 'Location n/a'}  |  {job.get('category') or ''}  |  "
                     f"via {job['source']}  |  posted {posted}  |  found {job['first_seen']}")
        if job.get("matched_keywords"):
            left.caption("Matched: " + ", ".join(job["matched_keywords"][:8]))
        right.metric("Match", f"{job['score']:.0f}")
        right.button("Applied", key=f"a-{key}", on_click=mark_applied, args=(job,), type="primary",
                     use_container_width=True)
        right.button("Hide", key=f"h-{key}", on_click=hide_job, args=(job,), use_container_width=True)
        with right.popover("People", use_container_width=True):
            people_panel(job, key)


# ---------- app ----------
gate()
st.title("Job Radar")

with st.sidebar:
    st.header("Filters")
    min_score = st.slider("Min match score", 0, 100, 40, 5)
    cats = st.multiselect("Role type", CATEGORIES, default=CATEGORIES)
    if st.button("Refresh data"):
        refresh()

apps = applications()
applied_ids = applied_job_ids()
week_ago = (dt.date.today() - dt.timedelta(days=7)).isoformat()
m1, m2, m3, m4 = st.columns(4)
m1.metric("Applied total", sum(a["status"] != "Saved" for a in apps))
m2.metric("Applied this week", sum((a["applied_on"] or "") >= week_ago for a in apps))
m3.metric("Interviews / OAs", sum(a["status"] in ("OA", "Interview") for a in apps))
m4.metric("Offers", sum(a["status"] == "Offer" for a in apps))

tab_new, tab_archive, tab_tracker = st.tabs(["New", "Archive", "Tracker"])

with tab_new:
    window = st.radio("Found in the last", ["1 day", "3 days", "7 days"], horizontal=True)
    since = dt.date.today() - dt.timedelta(days=int(window.split()[0]))
    jobs = [j for j in new_jobs(since, min_score, tuple(cats)) if j["id"] not in applied_ids]
    st.caption(f"{len(jobs)} new matches")
    if not jobs:
        st.info("Nothing new above your score threshold. Try lowering it in the sidebar.")
    for j in jobs:
        job_card(j, f"n-{j['id']}")

with tab_archive:
    c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
    text = c1.text_input("Search title, company, description", placeholder="e.g. perception, NVIDIA, LiDAR")
    sources = c2.multiselect("Source", all_sources())
    days_label = c3.selectbox("Found within", ["Any time", "30 days", "90 days"])
    sort = c4.selectbox("Sort", ["Best match", "Newest"])
    days = None if days_label == "Any time" else int(days_label.split()[0])

    page = st.session_state.get("page", 0)
    rows, total = archive_jobs(text, min_score, tuple(cats), tuple(sources), days, sort, page)
    pages = max(1, -(-total // 25))
    st.caption(f"{total} postings  |  page {page + 1} of {pages}")
    for j in rows:
        if j["id"] in applied_ids:
            continue
        job_card(j, f"r-{j['id']}")
    p1, _, p2 = st.columns([1, 4, 1])
    if p1.button("Previous", disabled=page == 0):
        st.session_state.page = page - 1
        st.rerun()
    if p2.button("Next", disabled=page + 1 >= pages):
        st.session_state.page = page + 1
        st.rerun()

with tab_tracker:
    if apps:
        counts = pd.Series([a["status"] for a in apps]).value_counts().reindex(STATUSES, fill_value=0)
        st.bar_chart(counts, horizontal=True, height=220)

        df = pd.DataFrame(apps)[["id", "company", "title", "status", "applied_on", "notes", "url"]]
        df["applied_on"] = pd.to_datetime(df["applied_on"]).dt.date
        edited = st.data_editor(
            df, hide_index=True, use_container_width=True, key="tracker",
            column_config={
                "id": None,
                "status": st.column_config.SelectboxColumn("Status", options=STATUSES, required=True),
                "applied_on": st.column_config.DateColumn("Applied on"),
                "notes": st.column_config.TextColumn("Notes", width="large"),
                "url": st.column_config.LinkColumn("Link", display_text="open"),
            },
            disabled=["company", "title", "url"],
        )
        if st.button("Save changes", type="primary"):
            changed = 0
            for (_, old), (_, new) in zip(df.iterrows(), edited.iterrows()):
                if (old["status"], old["notes"], old["applied_on"]) != (new["status"], new["notes"], new["applied_on"]):
                    db().table("applications").update({
                        "status": new["status"], "notes": new["notes"] or "",
                        "applied_on": new["applied_on"].isoformat() if new["applied_on"] else None,
                        "updated_at": dt.datetime.utcnow().isoformat(),
                    }).eq("id", new["id"]).execute()
                    changed += 1
            refresh()
            st.success(f"Saved {changed} change(s)")
            st.rerun()
    else:
        st.info("No applications yet. Hit Applied on any job, or add one below.")

    with st.expander("Add an application manually (job not in the list)"):
        with st.form("manual", clear_on_submit=True):
            a, b = st.columns(2)
            company = a.text_input("Company")
            title = b.text_input("Role")
            url = st.text_input("Job link")
            c, d = st.columns(2)
            status = c.selectbox("Status", STATUSES, index=1)
            applied_on = d.date_input("Applied on", dt.date.today())
            notes = st.text_area("Notes")
            if st.form_submit_button("Add") and company and title:
                db().table("applications").insert({
                    "company": company, "title": title, "url": url, "status": status,
                    "applied_on": applied_on.isoformat(), "notes": notes,
                }).execute()
                refresh()
                st.rerun()
