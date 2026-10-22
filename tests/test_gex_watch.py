from vzones.gex_watch import Watch, parse_all

B1 = "DATE=2026-10-22\nSPY: CW=770 PW=750 FLIP=774.57 PIN=760\nHOOD: CW=100 PW=95 FLIP=99.47 PIN=100"


def test_first_block_applies():
    w = Watch()
    assert w.update(B1)[0] and "SPY: CW=770" in w.block()


def test_flip_jitter_is_ignored():
    w = Watch(); w.update(B1)
    assert w.update(B1.replace("774.57", "774.9"))[0] is False      # 0.04% move
    assert w.update(B1.replace("774.57", "776.0")) == (False, [])   # 0.18% move, under 0.25%


def test_change_needs_confirmation_and_swap_back_is_never_pushed():
    w = Watch(confirm=2); w.update(B1)
    moved = B1.replace("CW=770", "CW=780")
    assert w.update(moved) == (False, [])                # seen once
    assert w.update(B1) == (False, [])                   # swapped back: pending dropped
    assert w.update(moved) == (False, [])                # seen once again
    ok, ch = w.update(moved)                             # twice in a row -> pushed
    assert ok and ch == ["SPY: CW 770->780"] and "CW=780" in w.block()


def test_new_date_replaces_everything():
    w = Watch(); w.update(B1)
    ok, ch = w.update(B1.replace("2026-10-22", "2026-10-23").replace("CW=770", "CW=790"))
    assert ok and ch == ["new session 2026-10-23"] and "CW=790" in w.block()


def test_parse_all():
    d, lv = parse_all(B1)
    assert d == "2026-10-22" and lv["HOOD"]["PW"] == 95 and set(lv) == {"SPY", "HOOD"}
