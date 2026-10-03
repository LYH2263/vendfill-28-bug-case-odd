from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Lane, Sale
router = APIRouter(prefix="/sales", tags=["sales"])

@router.get("")
def list_sales(db: Session = Depends(get_db)):
    lanes = {l.id: l for l in db.scalars(select(Lane)).all()}
    rows = db.scalars(select(Sale).order_by(Sale.sold_at.desc())).all()
    return [{"id": r.id, "lane_id": r.lane_id, "slot_no": lanes[r.lane_id].slot_no if r.lane_id in lanes else "",
             "sku_name": lanes[r.lane_id].sku_name if r.lane_id in lanes else "",
             "qty": r.qty, "sold_at": r.sold_at.isoformat()} for r in rows]
