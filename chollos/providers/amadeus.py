"""Proveedor de precios de hoteles vía Amadeus Self-Service API.

Alta gratuita en https://developers.amadeus.com → crea una app y obtén
`API Key` y `API Secret`. Guárdalos en variables de entorno (por defecto
AMADEUS_API_KEY / AMADEUS_API_SECRET); nunca en el YAML.

Hay dos entornos:
  * test        → https://test.api.amadeus.com  (gratis, datos limitados/cacheados)
  * production  → https://api.amadeus.com        (tras pasar la app a producción)

Flujo para hoteles (Self-Service):
  1. OAuth2: token con client_credentials.
  2. (opcional) Resolver `destination` → código IATA de ciudad.
  3. Hotel List by City → hotelIds (+ estrellas cuando están disponibles).
  4. Hotel Search (offers) → precios por hotel/fechas.
  5. Mapear a PriceQuote.

La capa HTTP se inyecta (`http_fn`) para poder testear sin red.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import Callable, Optional

from ..models import PriceQuote, WatchItem
from .base import PriceProvider

# http_fn(method, url, headers, body) -> (status_code, parsed_json)
HttpFn = Callable[[str, str, dict, Optional[bytes]], "tuple[int, dict]"]

_HOSTS = {
    "test": "https://test.api.amadeus.com",
    "production": "https://api.amadeus.com",
}


def _urllib_http(method: str, url: str, headers: dict, body: Optional[bytes]) -> "tuple[int, dict]":
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:  # noqa: PERF203
        raw = exc.read()
        try:
            return exc.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return exc.code, {"error": raw.decode("utf-8", "replace")}


def _chunks(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


class AmadeusError(RuntimeError):
    pass


class AmadeusProvider(PriceProvider):
    name = "amadeus"

    def __init__(self, api_key: str, api_secret: str, hostname: str = "test",
                 max_hotels: int = 40, http_fn: Optional[HttpFn] = None,
                 currency: str = "EUR"):
        if not api_key or not api_secret:
            raise AmadeusError(
                "Faltan credenciales de Amadeus. Define AMADEUS_API_KEY y "
                "AMADEUS_API_SECRET (o las variables indicadas en config.yaml)."
            )
        self.api_key = api_key
        self.api_secret = api_secret
        self.base = _HOSTS.get(hostname, _HOSTS["test"])
        self.max_hotels = max_hotels
        self.currency = currency
        self._http = http_fn or _urllib_http
        self._token: Optional[str] = None
        self._token_exp: float = 0.0

    # -- autenticación -------------------------------------------------------

    def _now(self) -> float:
        return time.time()

    def _get_token(self) -> str:
        if self._token and self._now() < self._token_exp:
            return self._token
        body = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": self.api_key,
            "client_secret": self.api_secret,
        }).encode()
        status, data = self._http(
            "POST", f"{self.base}/v1/security/oauth2/token",
            {"Content-Type": "application/x-www-form-urlencoded"}, body,
        )
        if status != 200 or "access_token" not in data:
            raise AmadeusError(f"No se pudo obtener token de Amadeus (HTTP {status}): {data}")
        self._token = data["access_token"]
        self._token_exp = self._now() + int(data.get("expires_in", 1799)) - 60
        return self._token

    def _get(self, path: str, params: dict) -> dict:
        url = f"{self.base}{path}?{urllib.parse.urlencode(params)}"
        headers = {"Authorization": f"Bearer {self._get_token()}"}
        status, data = self._http("GET", url, headers, None)
        if status != 200:
            raise AmadeusError(f"Amadeus GET {path} falló (HTTP {status}): {data}")
        return data

    # -- endpoints -----------------------------------------------------------

    def resolve_city_code(self, keyword: str) -> Optional[str]:
        data = self._get("/v1/reference-data/locations",
                          {"subType": "CITY", "keyword": keyword, "page[limit]": 1})
        items = data.get("data", [])
        return items[0].get("iataCode") if items else None

    def hotel_list(self, city_code: str) -> "list[dict]":
        data = self._get("/v1/reference-data/locations/hotels/by-city",
                          {"cityCode": city_code, "radius": 20,
                           "radiusUnit": "KM", "hotelSource": "ALL"})
        return data.get("data", [])

    def hotel_offers(self, hotel_ids: "list[str]", watch: WatchItem) -> "list[dict]":
        offers: list[dict] = []
        for batch in _chunks(hotel_ids, 25):
            params = {
                "hotelIds": ",".join(batch),
                "adults": watch.adults,
                "checkInDate": watch.checkin,
                "checkOutDate": watch.checkout,
                "roomQuantity": watch.rooms,
                "currency": watch.currency or self.currency,
                "bestRateOnly": "true",
            }
            try:
                data = self._get("/v3/shopping/hotel-offers", params)
            except AmadeusError:
                # Un lote puede fallar (hoteles sin disponibilidad); seguimos.
                continue
            offers.extend(data.get("data", []))
        return offers

    # -- interfaz PriceProvider ---------------------------------------------

    def fetch(self, watch: WatchItem) -> "list[PriceQuote]":
        city_code = watch.city_code
        if not city_code and watch.destination:
            city_code = self.resolve_city_code(watch.destination)
        if not city_code:
            raise AmadeusError(
                f"[{watch.name}] no hay city_code y no se pudo resolver desde "
                f"'{watch.destination}'. Añade 'city_code: XXX' en la búsqueda."
            )

        hotels = self.hotel_list(city_code)
        # Estrellas y nombre por hotelId (Amadeus a veces incluye 'rating').
        meta: dict[str, dict] = {}
        for h in hotels:
            hid = h.get("hotelId")
            if hid:
                meta[hid] = h
        hotel_ids = list(meta.keys())[: self.max_hotels]
        if not hotel_ids:
            return []

        observed_at = None  # PriceQuote pondrá la marca de tiempo actual
        quotes: list[PriceQuote] = []
        for entry in self.hotel_offers(hotel_ids, watch):
            q = self._offer_to_quote(entry, watch, meta, observed_at)
            if q is not None:
                quotes.append(q)
        return quotes

    @staticmethod
    def _offer_to_quote(entry: dict, watch: WatchItem, meta: dict,
                        observed_at) -> Optional[PriceQuote]:
        hotel = entry.get("hotel", {}) or {}
        offers = entry.get("offers", []) or []
        if not offers:
            return None
        # Precio más barato disponible del hotel.
        best = min(offers, key=lambda o: float((o.get("price", {}) or {}).get("total", "inf")))
        price = best.get("price", {}) or {}
        total = price.get("total")
        if total is None:
            return None

        hid = hotel.get("hotelId") or str(entry.get("id", "?"))
        info = meta.get(hid, {})
        rating = info.get("rating") or hotel.get("rating")
        try:
            stars = int(rating) if rating is not None else None
        except (TypeError, ValueError):
            stars = None

        name = hotel.get("name") or info.get("name") or hid
        city = (hotel.get("cityCode") or watch.city_code
                or (info.get("address", {}) or {}).get("cityName"))

        kwargs = dict(
            hotel_id=hid,
            name=name,
            url=f"https://www.google.com/travel/search?q={urllib.parse.quote(str(name))}",
            price_total=float(total),
            currency=price.get("currency", watch.currency),
            checkin=watch.checkin,
            checkout=watch.checkout,
            watch_name=watch.name,
            adults=watch.adults,
            stars=stars,
            city=city,
        )
        if observed_at:
            kwargs["observed_at"] = observed_at
        return PriceQuote(**kwargs)
