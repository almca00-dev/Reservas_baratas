"""Tests de las estrategias de detección de chollos."""

from chollos.config import DetectionConfig
from chollos.detector import Detector
from chollos.models import PriceQuote, WatchItem
from chollos.providers.booking_parse import parse_accommodations
from chollos.providers.demo import DemoProvider


def _q(hotel_id, ppn, stars, nights=2, observed="2026-07-14T00:00:00"):
    return PriceQuote(
        hotel_id=hotel_id, name=f"H{hotel_id}", url="", price_total=ppn * nights,
        currency="EUR", checkin="2026-09-05", checkout="2026-09-07",
        watch_name="w", adults=2, stars=stars, observed_at=observed,
    )


def _no_history(stay_key, before):
    return []


def test_comparativa_detecta_precio_absurdo():
    cfg = DetectionConfig(peer_discount_pct=0.5, min_peers=4)
    det = Detector(cfg)
    quotes = [_q("a", 200, 4), _q("b", 190, 4), _q("c", 210, 4),
              _q("d", 195, 4), _q("error", 12, 4)]
    chollos = det.detect_batch(quotes, _no_history)
    assert len(chollos) == 1
    assert chollos[0].quote.hotel_id == "error"
    assert chollos[0].reason == "comparativa"
    assert chollos[0].discount_pct > 0.8


def test_comparativa_no_falsos_positivos_precios_normales():
    cfg = DetectionConfig(peer_discount_pct=0.5, min_peers=4)
    det = Detector(cfg)
    quotes = [_q("a", 200, 4), _q("b", 190, 4), _q("c", 210, 4),
              _q("d", 195, 4), _q("e", 180, 4)]
    assert det.detect_batch(quotes, _no_history) == []


def test_comparativa_requiere_minimo_de_vecinos():
    cfg = DetectionConfig(peer_discount_pct=0.5, min_peers=4)
    det = Detector(cfg)
    # Solo 3 vecinos del tier => no aplica comparativa aunque haya uno barato.
    quotes = [_q("a", 200, 4), _q("b", 190, 4), _q("error", 10, 4)]
    assert det.detect_batch(quotes, _no_history) == []


def test_historico_detecta_caida():
    cfg = DetectionConfig(historical_drop_pct=0.5, min_history_points=3, min_peers=99)
    det = Detector(cfg)
    # Precio normal ~200/noche (400 total, 2 noches). Ahora 40/noche.
    history = [400.0, 420.0, 410.0]
    quotes = [_q("a", 40, 4)]
    chollos = det.detect_batch(quotes, lambda sk, b: history)
    assert len(chollos) == 1
    assert chollos[0].reason == "historico"
    assert chollos[0].discount_pct > 0.7


def test_historico_ignora_sin_suficiente_historial():
    cfg = DetectionConfig(historical_drop_pct=0.5, min_history_points=3, min_peers=99)
    det = Detector(cfg)
    quotes = [_q("a", 40, 4)]
    assert det.detect_batch(quotes, lambda sk, b: [400.0, 420.0]) == []


def test_floor_ignora_precios_corruptos():
    cfg = DetectionConfig(min_peers=4, floor_price_per_night=5.0)
    det = Detector(cfg)
    quotes = [_q("a", 200, 4), _q("b", 190, 4), _q("c", 210, 4),
              _q("d", 195, 4), _q("basura", 0.5, 4)]
    assert det.detect_batch(quotes, _no_history) == []


def test_umbral_absoluto():
    cfg = DetectionConfig(min_peers=99, absolute_max_price_per_night=50.0)
    det = Detector(cfg)
    quotes = [_q("a", 40, 4)]
    chollos = det.detect_batch(quotes, _no_history)
    assert len(chollos) == 1
    assert chollos[0].reason == "umbral_absoluto"


def test_demo_provider_inyecta_error_detectable():
    watch = WatchItem(name="w", checkin="2026-09-05", checkout="2026-09-07",
                      destination="Demo")
    quotes = DemoProvider().fetch(watch)
    det = Detector(DetectionConfig())
    chollos = det.detect_batch(quotes, _no_history)
    assert any(c.quote.hotel_id == "demo-error" for c in chollos)


def test_parse_fixture_real_sin_error():
    """Los datos reales de Barcelona no deben disparar falsos positivos."""
    import json
    import os
    path = os.path.join(os.path.dirname(__file__), "..", "fixtures",
                        "booking_barcelona_real.json")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    watch = WatchItem(name="Barcelona verano", checkin="2026-09-05",
                      checkout="2026-09-07", destination="Barcelona, Spain")
    quotes = parse_accommodations(data["accommodations"], watch, data["observed_at"])
    assert len(quotes) == 10
    # El hostal sin rating se parsea sin estrellas.
    assert any(q.stars is None for q in quotes)
    det = Detector(DetectionConfig())
    assert det.detect_batch(quotes, _no_history) == []
