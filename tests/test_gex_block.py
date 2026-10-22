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


def test_round_trip():
    rows = {"^SPX": {"CW": 6800.0, "PW": 6700.0, "FLIP": 6755.5012, "PIN": 6750.0, "DFLIP": None}}
    text = format_block("2026-10-22", rows)
    assert text == "DATE=2026-10-22\nSPX: CW=6800 PW=6700 FLIP=6755.5 PIN=6750"
    lv = parse_block(text, "SPX")
    assert lv["FLIP"] == 6755.5 and lv["DFLIP"] is None
