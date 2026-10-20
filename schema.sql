-- Run once in Supabase: SQL Editor -> New query -> paste -> Run

create table if not exists jobs (
  id               text primary key,          -- hash of company+title+location (dedupes across sources)
  source           text,
  company          text,
  title            text,
  location         text,
  url              text,
  description      text,
  posted_at        timestamptz,
  first_seen       date not null default current_date,
  score            real,
  category         text,                       -- CV / Perception, ML / AI, SWE
  seniority        text,                       -- New Grad, Entry, Mid, Unknown
  matched_keywords text[],
  is_remote        boolean,
  hidden           boolean not null default false
);
create index if not exists jobs_first_seen_idx on jobs (first_seen desc);
create index if not exists jobs_score_idx on jobs (score desc);

create table if not exists applications (
  id          uuid primary key default gen_random_uuid(),
  job_id      text unique references jobs(id) on delete set null,  -- null for manually added apps
  company     text not null,
  title       text not null,
  url         text,
  status      text not null default 'Applied',
  applied_on  date default current_date,
  notes       text default '',
  updated_at  timestamptz default now()
);

-- RLS on with no policies = only your secret key can read/write. Keeps your data private.
alter table jobs enable row level security;
alter table applications enable row level security;
-- Run once in Supabase SQL Editor (adds a cache so Hunter lookups aren't repeated)
create table if not exists contacts (
  company     text primary key,          -- lowercased company name
  results     jsonb not null default '[]',
  fetched_at  timestamptz default now()
);
alter table contacts enable row level security;

-- Upgrades for databases created before these columns existed (safe to re-run)
alter table jobs add column if not exists category text;
alter table jobs add column if not exists seniority text;
