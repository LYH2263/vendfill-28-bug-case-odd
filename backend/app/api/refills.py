import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Lane, Location, RefillOrder
from app.services.fill_engine import build_fill_lines, summarize
from app.services.page_split import present_full, present_summary, present_ticket
router = APIRouter(prefix="/refills", tags=["refills"])

def _lanes_payload(db: Session, location_id: int) -> list[dict]:
    lanes = db.scalars(select(Lane).where(Lane.location_id == location_id)
                       .order_by(Lane.slot_no)).all()
    return [{"id": l.id, "slot_no": l.slot_no, "sku_name": l.sku_name,
             "capacity": l.capacity, "stock": l.stock, "in_transit": l.in_transit,
             "case_pack": l.case_pack} for l in lanes]

def build_summary(db: Session, location_id: int) -> dict:
    """Recompute the authoritative fill summary for a location from its lanes."""
    return summarize(build_fill_lines(_lanes_payload(db, location_id)))

@router.post("/run")
def run_refill(location_id: int = 1, db: Session = Depends(get_db)):
    loc = db.get(Location, location_id)
    if not loc: raise HTTPException(404, "点位不存在")
    summary = build_summary(db, location_id)
    order = RefillOrder(location_id=location_id, created_at=datetime.utcnow(),
                        lines_json=json.dumps(summary, ensure_ascii=False))
    db.add(order); db.commit(); db.refresh(order)
    return present_ticket({"id": order.id, "location_id": location_id, **summary})

@router.get("/latest")
def latest(location_id: int = 1, db: Session = Depends(get_db)):
    order = db.scalars(select(RefillOrder).where(RefillOrder.location_id == location_id)
                       .order_by(RefillOrder.id.desc())).first()
    if not order:
        return run_refill(location_id=location_id, db=db)
    data = json.loads(order.lines_json)
    return present_ticket({"id": order.id, "location_id": location_id, **data})

@router.get("/full")
def full_lanes(location_id: int = 1, db: Session = Depends(get_db)):
    data = latest(location_id=location_id, db=db)
    return present_full(location_id, data)

@router.get("/summary")
def refill_summary(location_id: int = 1, db: Session = Depends(get_db)):
    data = latest(location_id=location_id, db=db)
    return present_summary(location_id, data)
