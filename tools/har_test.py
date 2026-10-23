"""PREREG addendum A: does HAR improve the rest-of-day range forecast, and does positioning add anything on top of HAR?
Runs on the data source of VZ_TAG (default IEX; VZ_TAG=sip for the consolidated feed).

    python tools/har_test.py
Writes <reports>/invention/har_results.json.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from vzones.assistant import data, eyes, regime as R  # noqa: E402


def main():
    rows = []
    for s in sorted(f[:-7] for f in os.listdir(data.BARS) if f.endswith("_5m.csv")):
        b = data.load_bars(s)
        if len(b) < 2000:
            continue
        rows += R.rows_for_symbol(s, eyes.build(s, b, tfs=(5,), paths=False)[5])
        print(s, len(rows), flush=True)
    df = R.usable(pd.DataFrame(rows), har=True)
    dates = sorted(df.date.unique())
    cut = dates[int(len(dates) * 0.6)]
    tr, te = df[df.date < cut].reset_index(drop=True), df[df.date >= cut].reset_index(drop=True)
    pt = R.predict(R.fit_all(tr, har=True), te)
    out = {"source": data.FEED, "rows": len(df), "test_rows": len(te), "test_days": int(te.date.nunique()), "cut": str(cut), "times": []}
    for t, g in pt.groupby("time"):
        mae = {k: float((g[f"f_{k}"] - g.y).abs().mean()) for k in ("B1", "B3", "B4", "P", "P4")}
        a = R.boot_mae_diff(g, "f_B3", "f_B4")
        b = R.boot_mae_diff(g, "f_B4", "f_P4")
        out["times"].append(dict(time=t, n=len(g), **{f"mae_{k}": v for k, v in mae.items()},
                                 har_gain=a["diff"], har_lo=a["lo"], har_hi=a["hi"], har_rel=a["rel"],
                                 pos_gain=b["diff"], pos_lo=b["lo"], pos_hi=b["hi"], pos_rel=b["rel"],
                                 har_passes=bool(a["lo"] > 0 and a["rel"] >= 0.02 and mae["B4"] < min(mae["B1"], mae["B3"])),
                                 pos_passes=bool(b["lo"] > 0 and b["rel"] >= 0.02 and mae["P4"] < min(mae["B1"], mae["B3"], mae["B4"]))))
    p = os.path.join(data.REPORTS, "invention")
    os.makedirs(p, exist_ok=True)
    json.dump(out, open(os.path.join(p, "har_results.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "times"}))
    print(pd.DataFrame(out["times"]).round(4).to_string())


if __name__ == "__main__":
    main()
