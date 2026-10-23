from vzones.gex_block import parse_block, format_block

BLOCK = """DATE=2026-10-22
INTU: CW=360 PW=340 FLIP=355 PIN=350
SPX: CW=6800 PW=6700 FLIP=6755.5 PIN=6750 DFLIP=6740
spy: cw=770,pw=750  flip=774.56\tpin=760
"""


def test_picks_current_ticker_line():
    lv = parse_block(BLOCK, "INTU")
    assert (lv["CW"], lv["PW"], lv["FLIP"], lv["PIN"]) == (360, 340, 355, 350)
    assert lv["DFLIP"] is None and lv["DATE"] == "2026-10-22"


def test_exchange_prefix_caret_and_loose_format():
    assert parse_block(BLOCK, "NASDAQ:INTU")["CW"] == 360
    assert parse_block(BLOCK, "^SPX")["DFLIP"] == 6740
    lv = parse_block(BLOCK, "SPY")
    assert (lv["CW"], lv["PW"], lv["FLIP"], lv["PIN"]) == (770, 750, 774.56, 760)


def test_missing_symbol_and_garbage():
    assert parse_block(BLOCK, "AAPL") is None
    assert parse_block("", "INTU") is None
    lv = parse_block("INTU: CW=360\r FOO=1 PW=abc", "INTU")
    assert lv["CW"] == 360 and lv["PW"] is None and lv["DATE"] == ""


def test_maxoi_key():
    lv = parse_block("SPY: CW=770 PW=750 FLIP=774.57 PIN=760 DFLIP=771.36 MAXOI=750", "SPY")
    assert lv["MAXOI"] == 750
    assert parse_block(BLOCK, "INTU")["MAXOI"] is None


def test_oi_walls():
    from vzones.gex_block import oi_walls
    st = [{"strike": 98, "call_oi": 9, "put_oi": 500}, {"strike": 100, "call_oi": 900, "put_oi": 900},
          {"strike": 105, "call_oi": 300, "put_oi": 1}, {"strike": 110, "call_oi": 300, "put_oi": 0},
          {"strike": 90, "call_oi": 0, "put_oi": 400}]
    # 100 sits inside the 0.6% buffer (spot 100.2) and is skipped; ties go to the strike nearer price
    assert oi_walls(st, 100.2) == (105, 98)
    assert oi_walls([], 100.0) == (None, None)
    lv = parse_block("SPY: CWOI=800 PWOI=750", "SPY")
    assert (lv["CWOI"], lv["PWOI"]) == (800, 750)


def test_round_trip():
    rows = {"^SPX": {"CW": 6800.0, "PW": 6700.0, "FLIP": 6755.5012, "PIN": 6750.0, "DFLIP": None}}
    text = format_block("2026-10-22", rows)
    assert text == "DATE=2026-10-22\nSPX: CW=6800 PW=6700 FLIP=6755.5 PIN=6750"
    lv = parse_block(text, "SPX")
    assert lv["FLIP"] == 6755.5 and lv["DFLIP"] is None


def test_wall_state_and_status_line():
    from vzones.gex_block import wall_state, status_line
    assert wall_state(110, 100, 90) == 1
    assert wall_state(100.2, 100, 90) == 2
    assert wall_state(95, 100, 90) == 3
    assert wall_state(90.3, 100, 90) == 4
    assert wall_state(80, 100, 90) == 5
    assert wall_state(95, None, 90) == 0
    lv = {"AAA": {"CW": 100, "PW": 90, "FLIP": 96}, "BBB": {"CW": 50, "PW": 40, "FLIP": 45}, "CCC": {"CW": 10, "PW": 8}}
    s = status_line(lv, {"AAA": 95, "BBB": 55, "CCC": 9}, "14:35")
    assert s == "#S: T=14:35 BBB=55|1|+ AAA=95|3|- CCC=9|3|"
    assert status_line(lv, {}, "14:35") is None
