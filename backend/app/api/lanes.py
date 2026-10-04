from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Lane, RefillOrder
from app.services.fill_engine import build_fill_lines, compute_gap, summarize
router = APIRouter(prefix="/lanes", tags=["lanes"])

def lane_dict(r: Lane) -> dict:
    gap = compute_gap(r.capacity, r.stock, r.in_transit)
    return {"id": r.id, "location_id": r.location_id, "slot_no": r.slot_no, "sku_name": r.sku_name,
            "capacity": r.capacity, "stock": r.stock, "in_transit": r.in_transit, "gap": gap,
            "case_pack": r.case_pack,
            "fill_pct": round(r.stock / r.capacity * 100, 1) if r.capacity else 0}

@router.get("")
def list_lanes(location_id: int | None = None, db: Session = Depends(get_db)):
    q = select(Lane).order_by(Lane.slot_no)
    if location_id is not None: q = q.where(Lane.location_id == location_id)
    return [lane_dict(r) for r in db.scalars(q).all()]

class LaneUpdate(BaseModel):
    # pieces per case; null/omitted = per-piece. Must be a positive integer when set.
    case_pack: int | None = None

def _lanes_payload(db: Session, location_id: int) -> list[dict]:
    lanes = db.scalars(select(Lane).where(Lane.location_id == location_id)
                       .order_by(Lane.slot_no)).all()
    return [{"id": l.id, "slot_no": l.slot_no, "sku_name": l.sku_name,
             "capacity": l.capacity, "stock": l.stock, "in_transit": l.in_transit,
             "case_pack": l.case_pack} for l in lanes]

@router.put("/{lane_id}")
def update_lane(lane_id: int, body: LaneUpdate, db: Session = Depends(get_db)):
    lane = db.get(Lane, lane_id)
    if not lane: raise HTTPException(404, "货道不存在")
    pack = body.case_pack
    if pack is not None and pack <= 0:
        # invalid case pack: reject outright — lane, latest order and summary
        # all stay exactly as they were, nothing enters the transaction.
        raise HTTPException(400, "箱规必须为正整数（留空表示按件补）")
    import json
    try:
        lane.case_pack = pack
        # Flush the lane change inside the SAME transaction before recomputing,
        # so the fresh summary sees the new case pack.
        db.flush()
        # Rewrite ONLY the location's latest refill order in this transaction:
        # lane case_pack and the live ticket move together or not at all.
        # Older orders are history and are never touched.
        order = db.scalars(select(RefillOrder).where(RefillOrder.location_id == lane.location_id)
                           .order_by(RefillOrder.id.desc())).first()
        rewritten_order_id = None
        if order is not None:
            summary = summarize(build_fill_lines(_lanes_payload(db, lane.location_id)))
            order.lines_json = json.dumps(summary, ensure_ascii=False)
            db.flush()
            rewritten_order_id = order.id
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(500, "保存失败：箱规与补货单已一并回滚")
    db.refresh(lane)
    return {**lane_dict(lane), "rewritten_order_id": rewritten_order_id}
