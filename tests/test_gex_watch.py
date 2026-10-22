from vzones.gex_watch import Watch, parse_all

B1 = ("DATE=2026-10-22\nSPY: CW=770 PW=750 FLIP=774.57 PIN=760 MAXOI=750 CWOI=800 PWOI=750\n"
      "HOOD: CW=100 PW=95 FLIP=99.47 PIN=100 MAXOI=100 CWOI=105 PWOI=90")
PRE, OPEN, MID = 8 * 60, 9 * 60 + 40, 12 * 60     # minutes after midnight ET


def test_first_block_applies():
    w = Watch()
    assert w.update(B1, MID)[0] and "SPY: CW=770" in w.block()


def test_gamma_levels_frozen_after_snapshot():
    w = Watch(); w.update(B1, MID)
    moved = B1.replace("CW=770", "CW=780").replace("FLIP=774.57", "FLIP=790").replace("PIN=760", "PIN=765")
    for _ in range(5):
        assert w.update(moved, MID + 30) == (False, [])
    assert "CW=770" in w.block() and "FLIP=774.57" in w.block()


def test_opening_snapshot_once():
    w = Watch(); w.update(B1, PRE)                       # overnight block
    moved = B1.replace("CW=770", "CW=780")
    assert w.update(moved, PRE + 30) == (False, [])      # still pre-market: gamma stays
    ok, ch = w.update(moved, OPEN)                       # first poll after 09:35 ET
    assert ok and ch == ["opening snapshot (1 symbols changed)"] and "CW=780" in w.block()
    assert w.update(B1, OPEN + 5) == (False, [])         # no second snapshot


def test_oi_change_needs_confirmation_and_swap_back_is_never_pushed():
    w = Watch(confirm=2); w.update(B1, MID)
    moved = B1.replace("CWOI=800", "CWOI=810")
    assert w.update(moved, MID) == (False, [])           # seen once
    assert w.update(B1, MID) == (False, [])              # swapped back: pending dropped
    assert w.update(moved, MID) == (False, [])
    ok, ch = w.update(moved, MID)                        # twice in a row -> pushed
    assert ok and ch == ["SPY: CWOI 800->810"] and "CWOI=810" in w.block()


def test_live_gamma_mode_ignores_flip_jitter():
    w = Watch(live_gamma=True); w.update(B1, MID)
    assert w.update(B1.replace("774.57", "776.0"), MID) == (False, [])    # 0.18% < 0.25%
    big = B1.replace("774.57", "780.0")
    w.update(big, MID)
    ok, ch = w.update(big, MID)
    assert ok and ch == ["SPY: FLIP 774.57->780"]


def test_new_date_replaces_everything():
    w = Watch(); w.update(B1, MID)
    ok, ch = w.update(B1.replace("2026-10-22", "2026-10-23").replace("CW=770", "CW=790"), PRE)
    assert ok and ch == ["new session 2026-10-23"] and "CW=790" in w.block()


def test_state_survives_restart():
    w = Watch(); w.update(B1, MID)
    w2 = Watch(); w2.load(w.to_json())
    moved = B1.replace("CW=770", "CW=780")
    assert w2.update(moved, MID + 60) == (False, [])     # same day, snapshot already taken: gamma stays
    assert "CW=770" in w2.block()


def test_parse_all():
    d, lv = parse_all(B1)
    assert d == "2026-10-22" and lv["HOOD"]["PW"] == 95 and set(lv) == {"SPY", "HOOD"}
