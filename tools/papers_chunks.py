"""Split the paper index into review batches: every paper that is finance or relevant statistics, with its abstract.
Writes runtime/papers_chunks/chunk_<k>.txt."""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDX = os.path.join(ROOT, "runtime", "papers_index.jsonl")
OUT = os.path.join(ROOT, "runtime", "papers_chunks")
FIN = r"q-fin|stock|option|portfolio|volatil|trading|asset pric|market mak|order book|hedg|financ|returns|equity|futures|liquidity|intraday|limit order|price impact|backtest|momentum"
STAT = r"time series|forecast|multiple (testing|hypothes)|false discovery|conformal|regime|change[- ]?point|bootstrap|overfit|calibrat|quantile regression|heavy[- ]tail"


def abstract(text: str) -> str:
    m = re.search(r"abstract[\s.:—-]*", text, re.I)
    s = text[m.end():] if m else text[200:]
    return s[:900]


rows = [json.loads(l) for l in open(IDX, encoding="utf-8")]
pick = [r for r in rows if re.search(FIN, r["text"][:4000], re.I) or re.search(STAT, r["text"][:4000], re.I)]
n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
os.makedirs(OUT, exist_ok=True)
for k in range(n):
    part = pick[k::n]
    with open(os.path.join(OUT, f"chunk_{k}.txt"), "w", encoding="utf-8") as f:
        for r in part:
            f.write(f"=== {r['id']}\nTITLE: {r['title'][:180]}\nABSTRACT: {abstract(r['text'])}\n\n")
print(len(rows), "papers,", len(pick), "candidates in", n, "batches of about", len(pick) // n)
