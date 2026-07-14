"""Hueco para un proveedor de Booking en vivo mediante API HTTP.

No está activo por defecto: Booking.com no ofrece una API pública abierta y
el scraping directo va contra sus términos de uso. Las vías legítimas son:

  * El programa de afiliados / Demand API de Booking (requiere alta y clave).
  * Un proveedor intermediario tipo RapidAPI ("Booking.com" API) con clave.

Cuando dispongas de un endpoint y una clave, implementa `fetch` para llamar a
la API, mapear la respuesta a la forma de `booking_parse.parse_accommodations`
y devolver los `PriceQuote`. El resto del sistema (almacenamiento, detección,
avisos) no cambia.
"""

from __future__ import annotations

import os
from typing import Optional

from ..models import PriceQuote, WatchItem
from .base import PriceProvider


class BookingApiProvider(PriceProvider):
    name = "booking_api"

    def __init__(self, base_url: str, api_key_env: str = "BOOKING_API_KEY"):
        self.base_url = base_url
        self.api_key: Optional[str] = os.environ.get(api_key_env)

    def fetch(self, watch: WatchItem) -> list[PriceQuote]:
        raise NotImplementedError(
            "BookingApiProvider aún no está implementado. Configura una API real "
            "(Demand API de Booking o un proveedor RapidAPI), mapea la respuesta con "
            "booking_parse.parse_accommodations y devuelve los PriceQuote. "
            "Mientras tanto usa SnapshotProvider (snapshots JSON) o DemoProvider."
        )
