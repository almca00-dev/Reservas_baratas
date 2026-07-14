"""Proveedor de datos sintéticos para pruebas y demostración.

Genera un conjunto realista de hoteles por categoría e inyecta un "error de
precio" evidente (un 4* a ~12 EUR/noche) para poder ver el detector en acción
sin depender de datos externos.
"""

from __future__ import annotations

from ..models import PriceQuote, WatchItem
from .base import PriceProvider

# Precio/noche "normal" aproximado por categoría de estrellas.
_BASE_PPN = {1: 60, 2: 90, 3: 130, 4: 190, 5: 350}


class DemoProvider(PriceProvider):
    name = "demo"

    def __init__(self, inject_error: bool = True):
        self.inject_error = inject_error

    def fetch(self, watch: WatchItem) -> list[PriceQuote]:
        nights = watch.nights
        quotes: list[PriceQuote] = []
        hid = 0

        # Varios hoteles por categoría con precios cercanos al "normal".
        for stars, base in _BASE_PPN.items():
            for i in range(5):
                hid += 1
                ppn = base * (0.9 + 0.05 * i)  # dispersión 0.90x .. 1.10x
                quotes.append(PriceQuote(
                    hotel_id=f"demo-{hid}",
                    name=f"Hotel Demo {stars}* #{i + 1}",
                    url=f"https://example.com/hotel/demo-{hid}",
                    price_total=round(ppn * nights, 2),
                    currency=watch.currency,
                    checkin=watch.checkin,
                    checkout=watch.checkout,
                    watch_name=watch.name,
                    adults=watch.adults,
                    stars=stars,
                    review_score=8.0 + stars * 0.1,
                    review_count=500 + hid,
                    city=watch.destination or "Demo City",
                    district="Centro",
                    observed_at=f"{watch.checkin}T00:00:{hid:02d}",
                ))

        if self.inject_error:
            quotes.append(PriceQuote(
                hotel_id="demo-error",
                name="Gran Hotel Demo 4* (ERROR DE PRECIO)",
                url="https://example.com/hotel/demo-error",
                price_total=round(12.0 * nights, 2),  # 12 EUR/noche en un 4*
                currency=watch.currency,
                checkin=watch.checkin,
                checkout=watch.checkout,
                watch_name=watch.name,
                adults=watch.adults,
                stars=4,
                review_score=8.7,
                review_count=1234,
                city=watch.destination or "Demo City",
                district="Centro",
                observed_at=f"{watch.checkin}T00:00:99",
            ))

        return quotes
