from app.services.fill_engine import build_fill_lines, compute_gap, round_to_case_pack, summarize

def test_gap_basic():
    assert compute_gap(20, 5, 0) == 15
    assert compute_gap(20, 10, 5) == 5

def test_no_negative_fill():
    lanes = [{"id": 1, "slot_no": "A1", "sku_name": "水", "capacity": 10, "stock": 12, "in_transit": 0}]
    lines = build_fill_lines(lanes)
    assert lines[0].fill_qty == 0
    assert lines[0].status == "overbooked"

def test_cap_by_gap():
    lanes = [{"id": 1, "slot_no": "A1", "sku_name": "水", "capacity": 20, "stock": 5, "in_transit": 0}]
    lines = build_fill_lines(lanes, requested={1: 100})
    assert lines[0].fill_qty == 15
    assert lines[0].gap == 15

def test_full_zero_fill():
    lanes = [{"id": 1, "slot_no": "A1", "sku_name": "水", "capacity": 10, "stock": 8, "in_transit": 2}]
    s = summarize(build_fill_lines(lanes))
    assert s["full_count"] == 1
    assert s["total_fill"] == 0

def test_case_pack_rounds_down_to_multiple():
    # seed scenario: B1 case_pack 4, gap 7 -> fill can only be 4
    lanes = [{"id": 1, "slot_no": "B1", "sku_name": "薯片", "capacity": 12, "stock": 3, "in_transit": 2, "case_pack": 4}]
    lines = build_fill_lines(lanes)
    assert lines[0].gap == 7
    assert lines[0].fill_qty == 4
    assert lines[0].status == "need_fill"
    assert lines[0].case_pack == 4

def test_case_pack_applies_after_gap_cap():
    lanes = [{"id": 1, "slot_no": "A1", "sku_name": "水", "capacity": 20, "stock": 5, "in_transit": 0, "case_pack": 4}]
    lines = build_fill_lines(lanes, requested={1: 100})
    assert lines[0].fill_qty == 12  # capped to gap 15 first, then floored to 12

def test_case_pack_zero_fill_stays_need_fill_not_full():
    # gap 10 < case_pack 12: rounds to 0, but the physical gap is still > 0
    lanes = [{"id": 1, "slot_no": "C1", "sku_name": "能量棒", "capacity": 10, "stock": 0, "in_transit": 0, "case_pack": 12}]
    s = summarize(build_fill_lines(lanes))
    line = s["lines"][0]
    assert line["fill_qty"] == 0
    assert line["status"] == "need_fill"  # "不足一整箱" must never read as "满仓"
    assert s["need_fill_count"] == 1
    assert s["full_count"] == 0
    assert s["total_fill"] == 0

def test_case_pack_none_or_one_is_per_piece():
    base = {"id": 1, "slot_no": "A1", "sku_name": "水", "capacity": 20, "stock": 5, "in_transit": 0}
    for pack in (None, 1):
        lines = build_fill_lines([{**base, "case_pack": pack}])
        assert lines[0].fill_qty == 15
        assert lines[0].case_pack == 1

def test_case_pack_non_positive_falls_back_to_per_piece():
    base = {"id": 1, "slot_no": "A1", "sku_name": "水", "capacity": 20, "stock": 5, "in_transit": 0}
    for pack in (0, -3):
        lines = build_fill_lines([{**base, "case_pack": pack}])
        assert lines[0].fill_qty == 15

def test_round_to_case_pack_helper():
    assert round_to_case_pack(7, 4) == 4
    assert round_to_case_pack(8, 4) == 8
    assert round_to_case_pack(3, 4) == 0
    assert round_to_case_pack(7, None) == 7
    assert round_to_case_pack(7, 1) == 7
