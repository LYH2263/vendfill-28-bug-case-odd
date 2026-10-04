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
    if "total_fill" in payload:
        # Authoritative aggregates snapshotted on the order: ticket and summary
        # must tell the same story (whole-case fills, status-based counts).
        total_fill = int(payload.get("total_fill") or 0)
        need_fill_count = int(payload.get("need_fill_count") or 0)
        full_count = int(payload.get("full_count") or 0)
        overbooked_count = int(payload.get("overbooked_count") or 0)
    else:
        # Fallback for raw payloads that carry no precomputed aggregates.
        gap_sum = 0
        zero_fill = 0
        overbooked_count = 0
        for l in lines:
            g = int(l.get("gap") or 0)
            f = int(l.get("fill_qty") or 0)
            if g > 0:
                gap_sum += g
            else:
                gap_sum += max(f, 0)
            if f == 0:
                zero_fill += 1
            if str(l.get("status") or "") == "overbooked":
                overbooked_count += 1
        total_fill = gap_sum
        need_fill_count = len(lines)
        full_count = zero_fill
    return {
        "location_id": location_id,
        "order_id": payload.get("id"),
        "status": payload.get("status"),
        "total_fill": total_fill,
        "need_fill_count": need_fill_count,
        "full_count": full_count,
        "overbooked_count": overbooked_count,
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
        fill = int(l.get("fill_qty") or 0)
        code = str(l.get("reject_code") or l.get("reason") or "")
        # need_fill stays need_fill even when a whole-case rule rounds its fill
        # down to 0 ("不足一整箱" is not "满仓") — never collect it here.
        if status == "need_fill":
            continue
        if fill == 0 or status in ("full", "blocked", "capped", "sku_cap_full", "overbooked"):
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
