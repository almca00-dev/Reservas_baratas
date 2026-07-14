"""Detección de chollos (candidatos a error de precio).

Dos estrategias complementarias:

1. Histórica: comparar el precio actual de una estancia contra su propio precio
   "normal" (mediana de observaciones anteriores). Detecta caídas bruscas.
   Necesita historial acumulado.

2. Comparativa (cross-sectional): comparar el precio/noche de un hotel contra
   la mediana de sus "vecinos" del mismo nivel (misma categoría de estrellas)
   en la misma búsqueda. Detecta precios absurdamente bajos ya en el primer
   escaneo, sin necesidad de historial.

Además, un umbral absoluto opcional: cualquier precio/noche por debajo de
`absolute_max_price_per_night` se marca directamente.
"""

from __future__ import annotations

import statistics
from typing import Optional

from .config import DetectionConfig
from .models import Chollo, PriceQuote


def _tier(q: PriceQuote) -> str:
    """Grupo de comparación de un alojamiento."""
    if q.stars and q.stars >= 1:
        return f"{q.stars}*"
    return "sin_estrellas"


def _median(values: list[float]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return statistics.median(vals)


def _score(discount_pct: float, savings_per_night: float) -> float:
    """Prioriza descuento porcentual y, en menor medida, el ahorro absoluto."""
    return round(discount_pct * 100 + min(savings_per_night, 1000) / 20, 2)


class Detector:
    def __init__(self, config: DetectionConfig):
        self.cfg = config

    def detect_batch(self, quotes: list[PriceQuote], history_fn) -> list[Chollo]:
        """Detecta chollos en un lote de cotizaciones de una misma búsqueda.

        `history_fn(stay_key, before) -> list[float]` devuelve los precios
        totales históricos de una estancia anteriores al momento observado.
        """
        cfg = self.cfg

        # Medianas por categoría (precio/noche) para la estrategia comparativa.
        tiers: dict[str, list[float]] = {}
        for q in quotes:
            if q.price_per_night >= cfg.floor_price_per_night:
                tiers.setdefault(_tier(q), []).append(q.price_per_night)
        tier_median = {t: _median(v) for t, v in tiers.items()}

        chollos: list[Chollo] = []
        for q in quotes:
            ppn = q.price_per_night
            if ppn < cfg.floor_price_per_night:
                continue

            candidate = self._best_candidate(q, ppn, tier_median, tiers, history_fn)
            if candidate is not None:
                chollos.append(candidate)

        chollos.sort(key=lambda c: c.score, reverse=True)
        return chollos

    def _best_candidate(self, q, ppn, tier_median, tiers, history_fn) -> Optional[Chollo]:
        cfg = self.cfg
        best: Optional[Chollo] = None

        def consider(cand: Chollo) -> None:
            nonlocal best
            if best is None or cand.discount_pct > best.discount_pct:
                best = cand

        # 1) Estrategia histórica
        hist = history_fn(q.stay_key(), q.observed_at)
        if len(hist) >= cfg.min_history_points:
            base_total = _median(hist)
            if base_total and base_total > 0 and q.price_total <= base_total * (1 - cfg.historical_drop_pct):
                disc = 1 - (q.price_total / base_total)
                base_ppn = base_total / q.nights
                savings = base_ppn - ppn
                consider(Chollo(
                    quote=q,
                    reason="historico",
                    baseline_per_night=base_ppn,
                    discount_pct=disc,
                    score=_score(disc, savings),
                    detail=(f"{ppn:.0f} {q.currency}/noche frente a un precio normal de "
                            f"~{base_ppn:.0f} (mediana de {len(hist)} observaciones)"),
                ))

        # 2) Estrategia comparativa
        tier = _tier(q)
        peers = tiers.get(tier, [])
        peer_med = tier_median.get(tier)
        if peer_med and len(peers) >= cfg.min_peers and ppn <= peer_med * cfg.peer_discount_pct:
            disc = 1 - (ppn / peer_med)
            savings = peer_med - ppn
            consider(Chollo(
                quote=q,
                reason="comparativa",
                baseline_per_night=peer_med,
                discount_pct=disc,
                score=_score(disc, savings),
                detail=(f"{ppn:.0f} {q.currency}/noche frente a ~{peer_med:.0f} de mediana "
                        f"en hoteles de {tier} ({len(peers)} comparables)"),
            ))

        # 3) Umbral absoluto
        cap = cfg.absolute_max_price_per_night
        if cap is not None and ppn <= cap:
            ref = peer_med or ppn
            disc = max(0.0, 1 - (ppn / ref)) if ref else 0.0
            consider(Chollo(
                quote=q,
                reason="umbral_absoluto",
                baseline_per_night=ref,
                discount_pct=disc,
                score=_score(disc, max(0.0, ref - ppn)) + 5,
                detail=f"{ppn:.0f} {q.currency}/noche, por debajo del umbral fijado ({cap:.0f})",
            ))

        return best
