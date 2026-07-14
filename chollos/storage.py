"""Persistencia en SQLite: histórico de precios y chollos detectados."""

from __future__ import annotations

import os
import sqlite3
from typing import Optional

from .models import Chollo, PriceQuote

_SCHEMA = """
CREATE TABLE IF NOT EXISTS quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hotel_id TEXT NOT NULL,
    name TEXT,
    url TEXT,
    price_total REAL NOT NULL,
    currency TEXT,
    checkin TEXT NOT NULL,
    checkout TEXT NOT NULL,
    adults INTEGER,
    stars INTEGER,
    review_score REAL,
    review_count INTEGER,
    city TEXT,
    district TEXT,
    watch_name TEXT,
    observed_at TEXT NOT NULL,
    stay_key TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_quotes_stay ON quotes(stay_key);
CREATE INDEX IF NOT EXISTS idx_quotes_observed ON quotes(observed_at);

CREATE TABLE IF NOT EXISTS chollos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hotel_id TEXT NOT NULL,
    name TEXT,
    city TEXT,
    checkin TEXT,
    checkout TEXT,
    price_total REAL,
    price_per_night REAL,
    currency TEXT,
    baseline_per_night REAL,
    discount_pct REAL,
    reason TEXT,
    score REAL,
    detail TEXT,
    url TEXT,
    watch_name TEXT,
    observed_at TEXT,
    fingerprint TEXT UNIQUE
);
"""


def _fingerprint(ch: Chollo) -> str:
    """Identifica un chollo concreto para no volver a avisar del mismo precio."""
    q = ch.quote
    return f"{q.stay_key()}|{round(q.price_total, 2)}"


class Storage:
    def __init__(self, db_path: str):
        self.db_path = db_path
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- histórico de precios ------------------------------------------------

    def save_quotes(self, quotes: list[PriceQuote]) -> int:
        rows = [
            (
                q.hotel_id, q.name, q.url, q.price_total, q.currency,
                q.checkin, q.checkout, q.adults, q.stars, q.review_score,
                q.review_count, q.city, q.district, q.watch_name,
                q.observed_at, q.stay_key(),
            )
            for q in quotes
        ]
        self.conn.executemany(
            """INSERT INTO quotes (hotel_id, name, url, price_total, currency,
                    checkin, checkout, adults, stars, review_score, review_count,
                    city, district, watch_name, observed_at, stay_key)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        self.conn.commit()
        return len(rows)

    def history_prices(self, stay_key: str, before: Optional[str] = None) -> list[float]:
        """Precios totales históricos de una estancia, opcionalmente anteriores a `before`."""
        if before:
            cur = self.conn.execute(
                "SELECT price_total FROM quotes WHERE stay_key = ? AND observed_at < ? ORDER BY observed_at",
                (stay_key, before),
            )
        else:
            cur = self.conn.execute(
                "SELECT price_total FROM quotes WHERE stay_key = ? ORDER BY observed_at",
                (stay_key,),
            )
        return [r["price_total"] for r in cur.fetchall()]

    # -- chollos detectados --------------------------------------------------

    def record_chollo(self, ch: Chollo) -> bool:
        """Guarda un chollo. Devuelve True si es nuevo, False si ya existía."""
        row = ch.to_row()
        try:
            self.conn.execute(
                """INSERT INTO chollos (hotel_id, name, city, checkin, checkout,
                        price_total, price_per_night, currency, baseline_per_night,
                        discount_pct, reason, score, detail, url, watch_name,
                        observed_at, fingerprint)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    row["hotel_id"], row["name"], row["city"], row["checkin"],
                    row["checkout"], row["price_total"], row["price_per_night"],
                    row["currency"], row["baseline_per_night"], row["discount_pct"],
                    row["reason"], row["score"], row["detail"], row["url"],
                    row["watch_name"], row["observed_at"], _fingerprint(ch),
                ),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def recent_chollos(self, limit: int = 50) -> list[sqlite3.Row]:
        cur = self.conn.execute(
            "SELECT * FROM chollos ORDER BY id DESC LIMIT ?", (limit,)
        )
        return cur.fetchall()

    def top_chollos(self, limit: int = 50) -> list[sqlite3.Row]:
        """Chollos ordenados por mayor descuento (score)."""
        cur = self.conn.execute(
            "SELECT * FROM chollos ORDER BY score DESC, id DESC LIMIT ?", (limit,)
        )
        return cur.fetchall()

    def stats(self) -> dict:
        q = self.conn.execute("SELECT COUNT(*) c, MAX(observed_at) m FROM quotes").fetchone()
        c = self.conn.execute("SELECT COUNT(*) c FROM chollos").fetchone()
        w = self.conn.execute("SELECT COUNT(DISTINCT watch_name) c FROM quotes").fetchone()
        return {
            "quotes": q["c"] or 0,
            "chollos": c["c"] or 0,
            "watches": w["c"] or 0,
            "last_observation": q["m"],
        }
