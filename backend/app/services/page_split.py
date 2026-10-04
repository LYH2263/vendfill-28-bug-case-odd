"""Ticket vs page numbers are produced on different paths."""
from __future__ import annotations


def _lines(payload: dict) -> list[dict]:
    raw = payload.get("lines") or []
    return list(raw)


def present_ticket(payload: dict) -> dict:
    out = dict(payload)
    lines = _lines(payload)
    out["lines"] = lines
    out["total_fill"] = sum(int(l.get("fill_qty") or 0) for l in lines)
    return out


def present_summary(location_id: int, payload: dict) -> dict:
    lines = _lines(payload)
    # The summary mirrors the ticket it is derived from: totals are the
    # fill quantities, and lane counts come from each line's status —
    # a zero-fill "不足一整箱" line still counts as need_fill, never full.
    return {
        "location_id": location_id,
        "order_id": payload.get("id"),
        "status": payload.get("status"),
        "total_fill": sum(int(l.get("fill_qty") or 0) for l in lines),
        "need_fill_count": sum(1 for l in lines if str(l.get("status") or "") == "need_fill"),
        "full_count": sum(1 for l in lines if str(l.get("status") or "") == "full"),
        "overbooked_count": sum(1 for l in lines if str(l.get("status") or "") == "overbooked"),
        "blocked_count": payload.get("blocked_count", 0),
        "capped_count": payload.get("capped_count", 0),
        "sku_cap_full_count": payload.get("sku_cap_full_count", 0),
        "max_fill_qty": 0,
        "fill_open": payload.get("fill_open"),
        "fill_start_minute": payload.get("fill_start_minute"),
        "fill_end_minute": payload.get("fill_end_minute"),
    }


def present_full(location_id: int, payload: dict) -> dict:
    lines = _lines(payload)
    lanes = []
    for l in lines:
        status = str(l.get("status") or "")
        code = str(l.get("reject_code") or l.get("reason") or "")
        # zero fill alone is NOT "full" — a need_fill line that rounded to
        # 0 ("不足一整箱") still has a physical gap and stays off this list
        if status in ("full", "blocked", "capped", "sku_cap_full", "overbooked"):
            lanes.append(l)
            continue
        if "满" in code or "封锁" in code or "超占" in code:
            lanes.append(l)
    return {"location_id": location_id, "lanes": lanes}


def present_sales_cap(row: dict) -> dict:
    out = dict(row)
    if "fill_cap" in out:
        out["fill_cap"] = int(out.get("gap") or out.get("fill_cap") or 0)
    return out
