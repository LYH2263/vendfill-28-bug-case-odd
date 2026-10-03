"""API-level tests for case-pack editing: lane save, latest-order rewrite and
summary must move together atomically; invalid packs roll everything back;
historical orders are never touched."""
import json
import os
import tempfile

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["SEED_ON_EMPTY"] = "true"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models.models import Lane, RefillOrder


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        from app.services.seed import seed_if_empty
        seed_if_empty(db)
    finally:
        db.close()
    with TestClient(app) as c:
        yield c


def lane_id(client, slot_no):
    rows = client.get("/api/lanes").json()
    return next(r["id"] for r in rows if r["slot_no"] == slot_no)


def latest_line(client, slot_no):
    data = client.get("/api/refills/latest?location_id=1").json()
    return data, next(l for l in data["lines"] if l["slot_no"] == slot_no)


def stored_order_lines(order_id):
    db = SessionLocal()
    try:
        return json.loads(db.get(RefillOrder, order_id).lines_json)
    finally:
        db.close()


def test_seed_b1_case_pack_4_gap_7_fills_4(client):
    res = client.post("/api/refills/run?location_id=1")
    assert res.status_code == 200
    line = next(l for l in res.json()["lines"] if l["slot_no"] == "B1")
    assert line["gap"] == 7
    assert line["case_pack"] == 4
    assert line["fill_qty"] == 4
    assert line["status"] == "need_fill"


def test_update_case_pack_rewrites_latest_order_and_summary(client):
    order = client.post("/api/refills/run?location_id=1").json()
    b1 = lane_id(client, "B1")

    res = client.put(f"/api/lanes/{b1}", json={"case_pack": 3})
    assert res.status_code == 200
    assert res.json()["case_pack"] == 3
    assert res.json()["rewritten_order_id"] == order["id"]

    # same order rewritten in place (not a new one), all lines recomputed: 7 -> 6
    latest, b1_line = latest_line(client, "B1")
    assert latest["id"] == order["id"]
    assert b1_line["fill_qty"] == 6
    assert b1_line["case_pack"] == 3

    # summary comes from the same rewritten order — same multiples everywhere
    summary = client.get("/api/refills/summary?location_id=1").json()
    assert summary["total_fill"] == sum(l["fill_qty"] for l in latest["lines"])
    assert summary["need_fill_count"] == sum(1 for l in latest["lines"] if l["status"] == "need_fill")

    # lane row reflects the new pack
    assert next(r for r in client.get("/api/lanes").json() if r["id"] == b1)["case_pack"] == 3


def test_invalid_case_pack_rolls_back_lane_and_order(client):
    order = client.post("/api/refills/run?location_id=1").json()
    b1 = lane_id(client, "B1")

    for bad in (0, -2):
        res = client.put(f"/api/lanes/{b1}", json={"case_pack": bad})
        assert res.status_code == 400

    # lane unchanged
    assert next(r for r in client.get("/api/lanes").json() if r["id"] == b1)["case_pack"] == 4
    # latest order unchanged — still the seeded pack-4 math
    latest, b1_line = latest_line(client, "B1")
    assert latest["id"] == order["id"]
    assert b1_line["fill_qty"] == 4
    assert b1_line["case_pack"] == 4
    # stored order content is byte-for-byte what the API serves back
    assert stored_order_lines(order["id"])["lines"] == latest["lines"]
    assert stored_order_lines(order["id"])["total_fill"] == latest["total_fill"]


def test_historical_orders_are_not_rewritten(client):
    first = client.post("/api/refills/run?location_id=1").json()
    b1 = lane_id(client, "B1")
    client.put(f"/api/lanes/{b1}", json={"case_pack": 2})
    second = client.post("/api/refills/run?location_id=1").json()
    assert second["id"] != first["id"]

    # editing again must only rewrite the latest (second) order
    client.put(f"/api/lanes/{b1}", json={"case_pack": 4})
    first_lines = stored_order_lines(first["id"])
    first_b1 = next(l for l in first_lines["lines"] if l["slot_no"] == "B1")
    assert first_b1["case_pack"] == 2          # left as it was when it stopped being latest
    assert first_b1["fill_qty"] == 6
    _, b1_line = latest_line(client, "B1")
    assert b1_line["case_pack"] == 4
    assert b1_line["fill_qty"] == 4


def test_empty_case_pack_falls_back_to_per_piece(client):
    client.post("/api/refills/run?location_id=1")
    b1 = lane_id(client, "B1")
    for body in ({"case_pack": None}, {"case_pack": 1}):
        res = client.put(f"/api/lanes/{b1}", json=body)
        assert res.status_code == 200
        _, b1_line = latest_line(client, "B1")
        assert b1_line["fill_qty"] == 7        # same as per-piece refill
        assert b1_line["case_pack"] == 1


def test_rewrite_failure_rolls_back_lane_and_order(client, monkeypatch):
    order = client.post("/api/refills/run?location_id=1").json()
    b1 = lane_id(client, "B1")
    before = stored_order_lines(order["id"])

    import app.api.lanes as lanes_api

    def boom(*_a, **_k):
        raise RuntimeError("simulated rewrite failure")

    monkeypatch.setattr(lanes_api, "summarize", boom)
    res = client.put(f"/api/lanes/{b1}", json={"case_pack": 2})
    assert res.status_code == 500

    # no half-success: lane case_pack AND order content both back to pre-save state
    assert next(r for r in client.get("/api/lanes").json() if r["id"] == b1)["case_pack"] == 4
    assert stored_order_lines(order["id"]) == before
    _, b1_line = latest_line(client, "B1")
    assert b1_line["fill_qty"] == 4


def test_migration_adds_column_and_backfills_b1(client):
    # simulate a database created before case packs existed
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE lanes"))
        conn.execute(text(
            "CREATE TABLE lanes (id INTEGER PRIMARY KEY, location_id INTEGER,"
            " slot_no VARCHAR(16), sku_name VARCHAR(64), capacity INTEGER,"
            " stock INTEGER, in_transit INTEGER)"
        ))
        conn.execute(text(
            "INSERT INTO lanes (location_id, slot_no, sku_name, capacity, stock, in_transit)"
            " VALUES (1, 'B1', '薯片', 12, 3, 2)"
        ))
    from app.main import ensure_case_pack_column
    ensure_case_pack_column()
    db = SessionLocal()
    try:
        lane = db.scalars(select(Lane).where(Lane.slot_no == "B1")).first()
        assert lane.case_pack == 4
    finally:
        db.close()


def test_less_than_one_case_never_counts_as_full(client):
    client.post("/api/refills/run?location_id=1")
    c1 = lane_id(client, "C1")  # gap 10
    res = client.put(f"/api/lanes/{c1}", json={"case_pack": 12})
    assert res.status_code == 200

    _, c1_line = latest_line(client, "C1")
    assert c1_line["fill_qty"] == 0
    assert c1_line["status"] == "need_fill"

    full = client.get("/api/refills/full?location_id=1").json()["lanes"]
    assert all(l["slot_no"] != "C1" for l in full)
    assert any(l["slot_no"] == "A2" for l in full)  # genuinely full lane still listed

    summary = client.get("/api/refills/summary?location_id=1").json()
    latest, _ = latest_line(client, "C1")
    assert summary["full_count"] == sum(1 for l in latest["lines"] if l["status"] == "full")
    assert summary["need_fill_count"] == sum(1 for l in latest["lines"] if l["status"] == "need_fill")
