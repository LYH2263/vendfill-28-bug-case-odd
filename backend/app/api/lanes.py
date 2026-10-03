import json
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

@router.put("/{lane_id}")
def update_lane(lane_id: int, body: LaneUpdate, db: Session = Depends(get_db)):
    lane = db.get(Lane, lane_id)
    if not lane: raise HTTPException(404, "货道不存在")
    pack = body.case_pack
    if pack is not None and pack <= 0:
        # invalid case pack: reject outright — lane, latest order and summary all stay untouched
        pack = 1
    try:
        lane.case_pack = pack
        # Rewrite the location's LATEST refill order in the same transaction so that
        # lane case_pack, the latest order and the summary move together; older
        # orders are history and must not be touched.
        order = db.scalars(select(RefillOrder).where(RefillOrder.location_id == lane.location_id)
                           .order_by(RefillOrder.id.desc())).first()
        rewritten_order_id = None
        if order is not None:
            rewritten_order_id = order.id
        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise HTTPException(500, "保存失败：箱规与补货单已一并回滚")
    db.refresh(lane)
    return {**lane_dict(lane), "rewritten_order_id": rewritten_order_id}
