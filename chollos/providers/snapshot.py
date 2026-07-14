"""Proveedor basado en snapshots JSON del conector de Booking.com.

Ruta real y compatible HOY: una herramienta Python que corre sola no puede
llamar al conector MCP de Booking (solo disponible dentro de una sesión de
Claude). El puente práctico es volcar los resultados de una búsqueda de
Booking a un fichero JSON en `snapshots/` y que el motor los ingiera.

Formato de cada snapshot (ver `fixtures/` para un ejemplo real):

    {
      "watch_name": "Barcelona verano",
      "destination": "Barcelona, Spain",
      "checkin": "2026-09-05",
      "checkout": "2026-09-07",
      "adults": 2,
      "currency": "EUR",
      "observed_at": "2026-07-14T09:00:00",
      "accommodations": [ ... objetos crudos de Booking ... ]
    }

Cada escaneo puede añadir un snapshot nuevo (mismo `watch_name`, distinto
`observed_at`); así se va construyendo el historial que necesita la
detección histórica.
"""

from __future__ import annotations

import glob
import json
import os
from typing import Optional

from ..models import PriceQuote, WatchItem
from .base import PriceProvider
from .booking_parse import parse_accommodations


class SnapshotProvider(PriceProvider):
    name = "snapshot"

    def __init__(self, snapshots_dir: str):
        self.snapshots_dir = snapshots_dir

    def _load_snapshots(self) -> list[dict]:
        snaps = []
        pattern = os.path.join(self.snapshots_dir, "*.json")
        for path in sorted(glob.glob(pattern)):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                data["_path"] = path
                snaps.append(data)
            except (json.JSONDecodeError, OSError):
                continue
        return snaps

    @staticmethod
    def _matches(snap: dict, watch: WatchItem) -> bool:
        if snap.get("watch_name"):
            return snap["watch_name"] == watch.name
        return (
            snap.get("destination") == watch.destination
            and snap.get("checkin") == watch.checkin
            and snap.get("checkout") == watch.checkout
        )

    def fetch(self, watch: WatchItem) -> list[PriceQuote]:
        matching = [s for s in self._load_snapshots() if self._matches(s, watch)]
        if not matching:
            return []
        latest = max(matching, key=lambda s: s.get("observed_at", ""))
        observed_at = latest.get("observed_at")
        return parse_accommodations(latest.get("accommodations", []), watch, observed_at)


def save_snapshot(snapshots_dir: str, watch_name: str, destination: str,
                  checkin: str, checkout: str, accommodations: list[dict],
                  observed_at: str, adults: int = 2, currency: str = "EUR") -> str:
    """Guarda un snapshot en disco y devuelve la ruta creada."""
    os.makedirs(snapshots_dir, exist_ok=True)
    safe = "".join(c if c.isalnum() else "_" for c in watch_name).strip("_")
    stamp = observed_at.replace(":", "").replace("-", "")
    path = os.path.join(snapshots_dir, f"{safe}_{stamp}.json")
    payload = {
        "watch_name": watch_name,
        "destination": destination,
        "checkin": checkin,
        "checkout": checkout,
        "adults": adults,
        "currency": currency,
        "observed_at": observed_at,
        "accommodations": accommodations,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return path
