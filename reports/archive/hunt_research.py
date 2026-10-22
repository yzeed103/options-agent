import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pandas as pd, vzones
from vzones.research import run_grid
D = pathlib.Path(__file__).resolve().parent.parent / "data"
H = vzones.VZParams(lookback=120, weak_ratio=0.8, break_ratio=1.5, adx_strong=25, step=4)
DL = vzones.VZParams(lookback=120, weak_ratio=0.8, break_ratio=1.3, adx_strong=20)
res = pd.concat([run_grid(vzones.load_lean_csv(D / "spy_hourly_lean.csv.gz"), H, "SPY 1h"),
                 run_grid(vzones.load_lean_csv(D / "spy_daily_lean.csv.gz"), DL, "SPY 1d", br=1.3),
                 run_grid(vzones.load_lean_csv(D / "qqq_daily_lean.csv.gz"), DL, "QQQ 1d", br=1.3)])
out = pathlib.Path(__file__).resolve().parent / "hunt_research.csv"; res.to_csv(out, index=False)
pd.set_option("display.width", 200); print(res.to_string(index=False))
