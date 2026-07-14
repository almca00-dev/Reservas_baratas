"""Tests del almacenamiento en SQLite."""

import os
import tempfile

from chollos.detector import Detector
from chollos.config import DetectionConfig
from chollos.models import Chollo, PriceQuote
from chollos.storage import Storage


def _q(hotel_id, ppn, observed):
    return PriceQuote(
        hotel_id=hotel_id, name=f"H{hotel_id}", url="", price_total=ppn * 2,
        currency="EUR", checkin="2026-09-05", checkout="2026-09-07",
        watch_name="w", adults=2, stars=4, observed_at=observed,
    )


def _tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    return path


def test_guardar_y_leer_historial():
    path = _tmp_db()
    try:
        with Storage(path) as st:
            st.save_quotes([_q("a", 200, "2026-07-10T00:00:00"),
                            _q("a", 220, "2026-07-11T00:00:00")])
            hist = st.history_prices(_q("a", 0, "x").stay_key())
            assert hist == [400.0, 440.0]
            # 'before' excluye observaciones posteriores.
            hist_before = st.history_prices(_q("a", 0, "x").stay_key(),
                                            before="2026-07-11T00:00:00")
            assert hist_before == [400.0]
    finally:
        os.unlink(path)


def test_record_chollo_deduplica():
    path = _tmp_db()
    try:
        q = _q("error", 12, "2026-07-14T00:00:00")
        ch = Chollo(quote=q, reason="comparativa", baseline_per_night=200,
                    discount_pct=0.94, score=94, detail="test")
        with Storage(path) as st:
            assert st.record_chollo(ch) is True
            assert st.record_chollo(ch) is False  # mismo fingerprint
            assert len(st.recent_chollos()) == 1
    finally:
        os.unlink(path)


def test_engine_detecta_sobre_historial_previo():
    """El baseline histórico se calcula con datos anteriores al escaneo actual."""
    from chollos.models import WatchItem
    path = _tmp_db()
    try:
        det = Detector(DetectionConfig(min_history_points=3, min_peers=99))
        with Storage(path) as st:
            # Sembramos 3 observaciones "normales".
            for i, obs in enumerate(["2026-07-10T00:00:00", "2026-07-11T00:00:00",
                                     "2026-07-12T00:00:00"]):
                st.save_quotes([_q("a", 200, obs)])
            # Nueva observación barata.
            nueva = _q("a", 40, "2026-07-14T00:00:00")
            chollos = det.detect_batch([nueva], st.history_prices)
            assert len(chollos) == 1
            assert chollos[0].reason == "historico"
    finally:
        os.unlink(path)
