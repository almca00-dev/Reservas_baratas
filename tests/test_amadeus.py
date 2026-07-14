"""Tests del proveedor Amadeus con una capa HTTP simulada (sin red)."""

import pytest

from chollos.config import DetectionConfig
from chollos.detector import Detector
from chollos.models import WatchItem
from chollos.providers.amadeus import AmadeusError, AmadeusProvider


def make_fake_http():
    """Simula los endpoints de Amadeus usados por el proveedor."""
    calls = {"token": 0}

    def http(method, url, headers, body):
        if url.endswith("/v1/security/oauth2/token"):
            calls["token"] += 1
            return 200, {"access_token": "TKN", "expires_in": 1799}
        if "/v1/reference-data/locations/hotels/by-city" in url:
            return 200, {"data": [
                {"hotelId": "H1", "name": "Hotel Uno", "rating": "4"},
                {"hotelId": "H2", "name": "Hotel Dos", "rating": "4"},
                {"hotelId": "H3", "name": "Hotel Tres", "rating": "4"},
                {"hotelId": "H4", "name": "Hotel Cuatro", "rating": "4"},
                {"hotelId": "HERR", "name": "Hotel Error", "rating": "4"},
            ]}
        if "/v3/shopping/hotel-offers" in url:
            return 200, {"data": [
                _offer("H1", "Hotel Uno", "380.00"),
                _offer("H2", "Hotel Dos", "400.00"),
                _offer("H3", "Hotel Tres", "360.00"),
                _offer("H4", "Hotel Cuatro", "420.00"),
                _offer("HERR", "Hotel Error", "24.00"),  # 12 EUR/noche en un 4*
            ]}
        if "/v1/reference-data/locations" in url:
            return 200, {"data": [{"iataCode": "BCN"}]}
        return 404, {"error": "no encontrado"}

    return http, calls


def _offer(hid, name, total):
    return {
        "hotel": {"hotelId": hid, "name": name, "cityCode": "BCN"},
        "offers": [{"id": "o1", "price": {"currency": "EUR", "total": total}}],
    }


def _watch():
    return WatchItem(name="Barcelona", checkin="2026-09-05",
                     checkout="2026-09-07", city_code="BCN", adults=2)


def test_credenciales_obligatorias():
    with pytest.raises(AmadeusError):
        AmadeusProvider(api_key="", api_secret="x")


def test_fetch_mapea_ofertas_a_quotes():
    http, _ = make_fake_http()
    prov = AmadeusProvider("k", "s", http_fn=http)
    quotes = prov.fetch(_watch())
    assert len(quotes) == 5
    err = next(q for q in quotes if q.hotel_id == "HERR")
    assert err.price_total == 24.0
    assert err.price_per_night == 12.0
    assert err.stars == 4
    assert err.currency == "EUR"


def test_token_se_cachea_entre_llamadas():
    http, calls = make_fake_http()
    prov = AmadeusProvider("k", "s", http_fn=http)
    prov.fetch(_watch())
    prov.fetch(_watch())
    assert calls["token"] == 1  # segundo fetch reutiliza el token


def test_detector_encuentra_error_en_datos_amadeus():
    http, _ = make_fake_http()
    prov = AmadeusProvider("k", "s", http_fn=http)
    quotes = prov.fetch(_watch())
    det = Detector(DetectionConfig(min_peers=4, peer_discount_pct=0.5))
    chollos = det.detect_batch(quotes, lambda sk, b: [])
    assert len(chollos) == 1
    assert chollos[0].quote.hotel_id == "HERR"
    assert chollos[0].discount_pct > 0.8


def test_resuelve_city_code_desde_destino():
    http, _ = make_fake_http()
    prov = AmadeusProvider("k", "s", http_fn=http)
    watch = WatchItem(name="w", checkin="2026-09-05", checkout="2026-09-07",
                      destination="Barcelona")
    quotes = prov.fetch(watch)  # sin city_code → lo resuelve a BCN
    assert len(quotes) == 5


def test_error_token_se_propaga():
    def http(method, url, headers, body):
        if url.endswith("/token"):
            return 401, {"error": "invalid_client"}
        return 200, {}
    prov = AmadeusProvider("k", "s", http_fn=http)
    with pytest.raises(AmadeusError):
        prov.fetch(_watch())
