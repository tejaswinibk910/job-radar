"""Scores jobs 0-100 against the resume: semantic similarity + keyword boosts - penalties."""
import re

import numpy as np

from .common import ROOT
from .seniority import classify


def _chunks(text, size=800):
    paras, buf, out = [p.strip() for p in text.split("\n") if p.strip()], "", []
    for p in paras:
        if len(buf) + len(p) > size and buf:
            out.append(buf)
            buf = ""
        buf += p + "\n"
    if buf:
        out.append(buf)
    return out or [text]


class Matcher:
    def __init__(self, resume_text, cfg):
        from fastembed import TextEmbedding

        self.model = TextEmbedding("BAAI/bge-small-en-v1.5", cache_dir=str(ROOT / ".model_cache"))
        s = cfg["scoring"]
        self.s = s
        self.boosts = [(re.compile(k, re.I), v) for k, v in s["boost_keywords"].items()]
        self.penalties = [(re.compile(k, re.I), v) for k, v in s["penalties"].items()]
        self.sen = cfg["seniority"]
        self.tiers = [(t["name"], re.compile(t["pattern"], re.I), t["points"]) for t in cfg["role_tiers"]]
        r = self._embed(_chunks(resume_text)).mean(axis=0)
        self.resume_vec = r / np.linalg.norm(r)

    def _embed(self, texts):
        e = np.array(list(self.model.embed(texts, batch_size=64)))
        return e / np.linalg.norm(e, axis=1, keepdims=True)

    def score(self, jobs):
        if not jobs:
            return
        texts = [f"{j['title']}. {j['company']}. {j['description'][:2500]}" for j in jobs]
        sims = self._embed(texts) @ self.resume_vec
        s = self.s
        for j, sim in zip(jobs, sims):
            text = f"{j['title']} {j['description']}"
            frac = np.clip((sim - s["sim_floor"]) / (s["sim_ceiling"] - s["sim_floor"]), 0, 1)
            hits = [p.pattern for p, _ in self.boosts if p.search(text)]
            boost = min(sum(v for p, v in self.boosts if p.search(text)), s["keyword_boost_cap"])
            penalty = sum(v for p, v in self.penalties if p.search(text))
            cat, tier_pts = next(((n, pts) for n, p, pts in self.tiers if p.search(j["title"])), ("Other", 0))
            j["category"] = cat
            level, _ = classify(j["title"], j["description"], self.sen["max_years"])
            j["seniority"] = level
            raw = frac * s["similarity_weight"] + boost - penalty + tier_pts + self.sen["points"].get(level, 0)
            j["score"] = round(float(np.clip(raw, 0, 100)), 1)
            j["matched_keywords"] = [h.replace("\\b", "").replace("'?", "'") for h in hits]
