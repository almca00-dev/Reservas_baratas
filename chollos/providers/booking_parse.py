"""Conversión del JSON de Booking.com a PriceQuote.

El conector de Booking devuelve objetos con esta forma (campos relevantes):

    {
      "id": 1896903,
      "name": "ibis Styles Barcelona City Bogatell",
      "url": "https://www.booking.com/hotel/...",
      "price": {"book": 474.5, "currency": "EUR"},
      "rating": {"number_of_reviews": 4692, "review_score": 8.5, "stars": 2},
      "location": {"city_name": "Barcelona", "district_name": "Sant Martí", ...}
    }

`rating` puede faltar (p. ej. algunos hostales sin puntuación).
"""

from __future__ import annotations

from typing import Any, Optional

from ..models import PriceQuote, WatchItem


def _get(d: Optional[dict], *keys, default=None):
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default


def parse_accommodation(raw: dict, watch: WatchItem, observed_at: Optional[str] = None) -> Optional[PriceQuote]:
    price = _get(raw, "price", "book")
    if price is None:
        return None
    kwargs = dict(
        hotel_id=str(raw.get("id")),
        name=raw.get("name", "?"),
        url=raw.get("url", ""),
        price_total=float(price),
        currency=_get(raw, "price", "currency", default=watch.currency),
        checkin=watch.checkin,
        checkout=watch.checkout,
        watch_name=watch.name,
        adults=watch.adults,
        stars=_get(raw, "rating", "stars"),
        review_score=_get(raw, "rating", "review_score"),
        review_count=_get(raw, "rating", "number_of_reviews"),
        city=_get(raw, "location", "city_name"),
        district=_get(raw, "location", "district_name"),
    )
    if observed_at:
        kwargs["observed_at"] = observed_at
    return PriceQuote(**kwargs)


def parse_accommodations(raw_list: list[dict], watch: WatchItem,
                         observed_at: Optional[str] = None) -> list[PriceQuote]:
    quotes = []
    for raw in raw_list or []:
        q = parse_accommodation(raw, watch, observed_at)
        if q is not None:
            quotes.append(q)
    return quotes
