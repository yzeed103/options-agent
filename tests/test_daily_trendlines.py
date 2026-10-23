import numpy as np
import pandas as pd

from vzones.daily_trendlines import daily_lines


def _day(date, closes):
    t = pd.date_range(f"{date} 09:30", periods=len(closes), freq="5min", tz="America/New_York")
    c = np.array(closes, float)
    return pd.DataFrame({"time": t.astype(str), "open": c, "high": c + 0.2, "low": c - 0.2, "close": c, "volume": 1})


def _zigzag_up(n=60):
    # rising zigzag: swing lows climb, so a rising support from today's lows must appear
    base = np.linspace(100, 110, n)
    return list(base + 1.5 * np.sin(np.arange(n) / 2.0))


def test_green_line_from_today_and_never_closed_through():
    df = pd.concat([_day("2026-10-21", _zigzag_up()), _day("2026-10-22", _zigzag_up())], ignore_index=True)
    r = daily_lines(df, k=2)
    day = pd.to_datetime(df["time"]).dt.date.to_numpy()
    c = df["close"].to_numpy()
    shown = [(i, ln) for i, ln in enumerate(r["green"]) if ln is not None]
    assert shown, "an uptrend must get a rising support line"
    for i, (a, y0, s) in shown:
        assert day[a] == day[i]                       # built from today's swing only
        assert s > 0                                  # rising
        assert all(c[j] >= y0 + s * (j - a) - 1e-9 for j in range(a + 1, i))   # no close below it before bar i


def test_new_session_starts_empty():
    df = pd.concat([_day("2026-10-21", _zigzag_up()), _day("2026-10-22", _zigzag_up())], ignore_index=True)
    r = daily_lines(df, k=2)
    first = int(np.argmax(pd.to_datetime(df["time"]).dt.date.to_numpy() == pd.Timestamp("2026-10-22").date()))
    assert r["green"][first] is None and r["red"][first] is None


def test_break_ends_the_line():
    up = _zigzag_up(40)
    crash = list(np.linspace(up[-1], up[-1] - 15, 10))
    df = _day("2026-10-22", up + crash)
    r = daily_lines(df, k=2)
    assert r["break_green"].any()
    b = int(np.argmax(r["break_green"]))
    assert r["green"][b] is None


def test_small_lines_stay_inside_the_window():
    from vzones.daily_trendlines import small_lines
    df = pd.concat([_day("2026-10-21", _zigzag_up()), _day("2026-10-22", _zigzag_up())], ignore_index=True)
    r = small_lines(df, k=1, window=15)
    c = df["close"].to_numpy()
    shown = [(i, ln) for i, ln in enumerate(r["green"]) if ln is not None]
    assert len(shown) > len(df) * 0.3, "small lines should be on screen much of the time"
    for i, (a, y0, s) in shown:
        assert i - a <= 15                            # anchor inside the last 15 bars
        assert all(c[j] >= y0 + s * (j - a) - 1e-9 for j in range(a + 1, i))
