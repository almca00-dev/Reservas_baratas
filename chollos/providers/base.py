"""Interfaz de proveedor de precios.

Un proveedor sabe, dada una búsqueda (WatchItem), devolver la lista de
cotizaciones (PriceQuote) disponibles en ese momento. Esta abstracción
permite intercambiar la fuente de datos sin tocar el motor de detección:

- SnapshotProvider: lee snapshots JSON con el formato del conector de
  Booking.com (ruta real y compatible hoy).
- DemoProvider: datos sintéticos para pruebas y demo.
- BookingApiProvider: hueco para una API real (RapidAPI / partner) con clave.
- (futuro) FlightsProvider: mismo contrato para vuelos.
"""

from __future__ import annotations

import abc

from ..models import PriceQuote, WatchItem


class PriceProvider(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def fetch(self, watch: WatchItem) -> list[PriceQuote]:
        """Devuelve las cotizaciones actuales para la búsqueda dada."""
        raise NotImplementedError
