"""Vending refill: gap = capacity - stock - in_transit; fills capped by gap; no negative fills.

Case-pack rounding: each lane may declare a case_pack (pieces per case, positive int;
empty/None/1 means per-piece). Fill qty is capped by the gap first, then rounded DOWN
to a whole-case multiple. A lane whose gap > 0 stays need_fill even when the rounded
fill is 0 ("less than one case" is never reported as "full").
"""
from __future__ import annotations
from dataclasses import asdict, dataclass

@dataclass
class FillLine:
    lane_id: int
    slot_no: str
    sku_name: str
    capacity: int
    stock: int
    in_transit: int
    gap: int
    fill_qty: int
    status: str  # need_fill | full | overbooked
    case_pack: int = 1

def compute_gap(capacity: int, stock: int, in_transit: int) -> int:
    return capacity - stock - in_transit

def effective_case_pack(case_pack: int | None) -> int:
    """None/empty/1 -> per-piece (1); anything <= 0 is treated as per-piece too."""
    try:
        pack = int(case_pack) if case_pack is not None else 1
    except (TypeError, ValueError):
        return 1
    return pack if pack > 1 else 1

def round_to_case_pack(qty: int, case_pack: int | None) -> int:
    """Round qty DOWN to a whole multiple of the case pack (floor)."""
    pack = effective_case_pack(case_pack)
    if pack <= 1:
        return qty
    return (qty // pack) * pack

def build_fill_lines(lanes: list[dict], requested: dict[int, int] | None = None) -> list[FillLine]:
    """requested optional desired fill per lane_id; capped by gap, then rounded down
    to the lane's case pack; never negative."""
    lines: list[FillLine] = []
    for lane in lanes:
        gap = compute_gap(int(lane["capacity"]), int(lane["stock"]), int(lane["in_transit"]))
        pack = effective_case_pack(lane.get("case_pack"))
        if gap < 0:
            status = "overbooked"
            fill = 0
        elif gap == 0:
            status = "full"
            fill = 0
        else:
            status = "need_fill"
            desire = gap if requested is None else int(requested.get(lane["id"], gap))
            fill = round_to_case_pack(max(0, min(desire, gap)), pack)
            # fill 0 here means "gap too small for one whole case"; the lane is
            # physically still empty, so it stays need_fill, never full.
        lines.append(FillLine(
            lane_id=lane["id"], slot_no=lane["slot_no"], sku_name=lane["sku_name"],
            capacity=lane["capacity"], stock=lane["stock"], in_transit=lane["in_transit"],
            gap=gap, fill_qty=fill, status=status, case_pack=pack,
        ))
    return lines

def summarize(lines: list[FillLine]) -> dict:
    return {
        "total_fill": sum(l.fill_qty for l in lines),
        "need_fill_count": sum(1 for l in lines if l.status == "need_fill"),
        "full_count": sum(1 for l in lines if l.status == "full"),
        "overbooked_count": sum(1 for l in lines if l.status == "overbooked"),
        "lines": [asdict(l) for l in lines],
    }
