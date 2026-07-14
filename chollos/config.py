"""Carga y validación de la configuración (YAML)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional

import yaml

from .models import WatchItem


@dataclass
class DetectionConfig:
    # % por debajo del propio precio normal para considerarlo chollo (histórico)
    historical_drop_pct: float = 0.5
    # precio como fracción de la mediana de sus "vecinos" comparables (comparativa)
    peer_discount_pct: float = 0.5
    # nº mínimo de observaciones históricas para fiarnos del baseline histórico
    min_history_points: int = 3
    # nº mínimo de vecinos comparables para la detección por comparativa
    min_peers: int = 4
    # techo absoluto opcional de precio/noche por debajo del cual siempre avisa
    absolute_max_price_per_night: Optional[float] = None
    # ignorar precios ridículamente bajos (probable dato corrupto, no chollo real)
    floor_price_per_night: float = 1.0


@dataclass
class EmailConfig:
    enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    username: str = ""
    # nombre de la variable de entorno que contiene la contraseña de aplicación
    password_env: str = "CHOLLOS_EMAIL_PASSWORD"
    sender: str = ""
    to: list[str] = field(default_factory=list)

    @property
    def password(self) -> str:
        return os.environ.get(self.password_env, "")


@dataclass
class Config:
    currency: str = "EUR"
    user_country_code: str = "es"
    user_locale: str = "es"
    db_path: str = "data/chollos.db"
    snapshots_dir: str = "snapshots"
    watchlist: list[WatchItem] = field(default_factory=list)
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    email: EmailConfig = field(default_factory=EmailConfig)


def _watch_from_dict(d: dict[str, Any], default_currency: str) -> WatchItem:
    return WatchItem(
        name=d["name"],
        checkin=d["checkin"],
        checkout=d["checkout"],
        destination=d.get("destination"),
        hotel_names=d.get("hotel_names"),
        adults=int(d.get("adults", 2)),
        rooms=int(d.get("rooms", 1)),
        currency=d.get("currency", default_currency),
    )


def load_config(path: str) -> Config:
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    currency = raw.get("currency", "EUR")
    cfg = Config(
        currency=currency,
        user_country_code=raw.get("user_country_code", "es"),
        user_locale=raw.get("user_locale", "es"),
        db_path=raw.get("storage", {}).get("db_path", "data/chollos.db"),
        snapshots_dir=raw.get("storage", {}).get("snapshots_dir", "snapshots"),
    )

    for w in raw.get("watchlist", []) or []:
        cfg.watchlist.append(_watch_from_dict(w, currency))

    det = raw.get("detection", {}) or {}
    cfg.detection = DetectionConfig(
        historical_drop_pct=float(det.get("historical_drop_pct", 0.5)),
        peer_discount_pct=float(det.get("peer_discount_pct", 0.5)),
        min_history_points=int(det.get("min_history_points", 3)),
        min_peers=int(det.get("min_peers", 4)),
        absolute_max_price_per_night=det.get("absolute_max_price_per_night"),
        floor_price_per_night=float(det.get("floor_price_per_night", 1.0)),
    )

    em = (raw.get("notifications", {}) or {}).get("email", {}) or {}
    cfg.email = EmailConfig(
        enabled=bool(em.get("enabled", False)),
        smtp_host=em.get("smtp_host", "smtp.gmail.com"),
        smtp_port=int(em.get("smtp_port", 587)),
        username=em.get("username", ""),
        password_env=em.get("password_env", "CHOLLOS_EMAIL_PASSWORD"),
        sender=em.get("sender", em.get("username", "")),
        to=list(em.get("to", []) or []),
    )

    return cfg
