"""Index the arXiv papers in C:/project/quant/quant_model/data/formula_batch/pdf (read-only): first two pages of text
per paper -> runtime/papers_index.jsonl, then score each paper against the topics of the assistant's work.

    python tools/papers_index.py            # build the index (skips papers already indexed), then rank
    python tools/papers_index.py --rank     # rank only
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = r"C:\project\quant\quant_model\data\formula_batch\pdf"
IDX = os.path.join(ROOT, "runtime", "papers_index.jsonl")

TOPICS = {
    "dealer gamma / hedging": [r"gamma exposure", r"dealer", r"market maker", r"delta[- ]hedg", r"hedging (demand|pressure|flow)", r"gamma imbalance", r"negative gamma"],
    "options open interest / pinning": [r"open interest", r"pinning", r"strike price clustering", r"option expiration", r"max(imum)? pain", r"0dte|zero[- ]day"],
    "intraday volatility forecast": [r"intraday volatility", r"realized volatility", r"\bHAR\b", r"range[- ]based", r"volatility forecast"],
    "volume profile / support-resistance": [r"volume profile", r"volume at price", r"support and resistance", r"price levels?", r"high[- ]volume node"],
    "intraday momentum / trend": [r"intraday momentum", r"trend[- ]following", r"time[- ]series momentum", r"breakout"],
    "order flow / microstructure": [r"order flow", r"order book", r"price impact", r"market microstructure"],
    "technical analysis tests": [r"technical (analysis|trading rules?)", r"moving average", r"data[- ]snooping", r"reality check"],
}


def build():
    import pymupdf
    done = set()
    if os.path.exists(IDX):
        done = {json.loads(l)["id"] for l in open(IDX, encoding="utf-8")}
    files = sorted(f for f in os.listdir(PDF) if f.endswith(".pdf"))
    os.makedirs(os.path.dirname(IDX), exist_ok=True)
    with open(IDX, "a", encoding="utf-8") as out:
        for n, f in enumerate(files):
            pid = f[:-4]
            if pid in done:
                continue
            try:
                doc = pymupdf.open(os.path.join(PDF, f))
                text = " ".join(doc[k].get_text() for k in range(min(2, doc.page_count)))
                pages = doc.page_count
                doc.close()
            except Exception as e:  # noqa: BLE001
                text, pages = f"ERROR {type(e).__name__}", 0
            text = re.sub(r"\s+", " ", text)[:6000]
            title = text[:200]
            out.write(json.dumps({"id": pid, "pages": pages, "title": title, "text": text}, ensure_ascii=False) + "\n")
            if n % 200 == 0:
                print(n, "/", len(files), flush=True)


def rank(top=12):
    rows = [json.loads(l) for l in open(IDX, encoding="utf-8")]
    res = {}
    for t, pats in TOPICS.items():
        sc = []
        for r in rows:
            low = r["text"].lower()
            hits = sum(len(re.findall(p, low)) for p in pats)
            if hits:
                sc.append((hits, r["id"], r["title"][:150]))
        sc.sort(reverse=True)
        res[t] = sc
        print(f"\n## {t}: {len(sc)} papers mention it")
        for h, pid, ti in sc[:top]:
            print(f"  {h:3}  {pid:16} {ti}")
    json.dump({t: [(h, p) for h, p, _ in v] for t, v in res.items()}, open(os.path.join(ROOT, "runtime", "papers_rank.json"), "w"), indent=0)
    print("\nindexed papers:", len(rows))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rank", action="store_true")
    a = ap.parse_args()
    if not a.rank:
        build()
    rank()
