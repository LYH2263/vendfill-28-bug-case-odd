from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.api.router import api_router
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.services.seed import seed_if_empty


def ensure_case_pack_column() -> None:
    """Add lanes.case_pack to databases created before case packs existed.
    When the column is freshly added, align seed lane B1 with the seeded
    case pack (4) so old dev databases match a fresh seed."""
    insp = inspect(engine)
    if "lanes" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("lanes")}
    if "case_pack" in cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE lanes ADD COLUMN case_pack INTEGER"))
        conn.execute(text("UPDATE lanes SET case_pack = 4 WHERE slot_no = 'B1'"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_case_pack_column()
    if settings.seed_on_empty:
        db = SessionLocal()
        try:
            seed_if_empty(db)
        finally:
            db.close()
    yield


app = FastAPI(title="VendFill", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api")
