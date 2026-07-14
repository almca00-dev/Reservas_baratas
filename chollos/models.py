"""Modelos de datos del buscador de chollos."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


def _nights_between(checkin: str, checkout: str) -> int:
    """Número de noches entre dos fechas ISO (YYYY-MM-DD)."""
    ci = date.fromisoformat(checkin)
    co = date.fromisoformat(checkout)
    n = (co - ci).days
    return n if n > 0 else 1


@dataclass
class WatchItem:
    """Una búsqueda que vigilamos periódicamente."""

    name: str
    checkin: str
    checkout: str
    destination: Optional[str] = None
    hotel_names: Optional[list[str]] = None
    adults: int = 2
    rooms: int = 1
    currency: str = "EUR"

    @property
    def nights(self) -> int:
        return _nights_between(self.checkin, self.checkout)

    def key(self) -> str:
        target = self.destination or ",".join(self.hotel_names or [])
        return f"{self.name}|{target}|{self.checkin}|{self.checkout}|{self.adults}"


@dataclass
class PriceQuote:
    """Una observación de precio para un alojamiento en una fecha concreta."""

    hotel_id: str
    name: str
    url: str
    price_total: float
    currency: str
    checkin: str
    checkout: str
    watch_name: str
    adults: int = 2
    stars: Optional[int] = None
    review_score: Optional[float] = None
    review_count: Optional[int] = None
    city: Optional[str] = None
    district: Optional[str] = None
    observed_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @property
    def nights(self) -> int:
        return _nights_between(self.checkin, self.checkout)

    @property
    def price_per_night(self) -> float:
        return round(self.price_total / self.nights, 2)

    def stay_key(self) -> str:
        """Identifica la "misma estancia" (hotel + fechas + ocupación).

        Sirve para agrupar observaciones históricas del mismo producto.
        """
        return f"{self.hotel_id}|{self.checkin}|{self.checkout}|{self.adults}"


@dataclass
class Chollo:
    """Candidato a chollo detectado."""

    quote: PriceQuote
    reason: str          # 'historico' | 'comparativa'
    baseline_per_night: float
    discount_pct: float  # 0..1  (0.6 = 60% por debajo del precio normal)
    score: float
    detail: str

    def to_row(self) -> dict:
        q = self.quote
        return {
            "hotel_id": q.hotel_id,
            "name": q.name,
            "city": q.city,
            "checkin": q.checkin,
            "checkout": q.checkout,
            "price_total": q.price_total,
            "price_per_night": q.price_per_night,
            "currency": q.currency,
            "baseline_per_night": round(self.baseline_per_night, 2),
            "discount_pct": round(self.discount_pct, 4),
            "reason": self.reason,
            "score": round(self.score, 2),
            "detail": self.detail,
            "url": q.url,
            "watch_name": q.watch_name,
            "observed_at": q.observed_at,
        }
