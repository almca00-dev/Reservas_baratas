"""Interfaz de línea de comandos del buscador de chollos.

Ejemplos:
    python -m chollos init                 # crea config.yaml a partir del ejemplo
    python -m chollos scan                 # escanea usando snapshots
    python -m chollos scan --provider demo # escanea con datos de demostración
    python -m chollos report               # muestra los últimos chollos guardados
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys

from .config import Config, load_config
from .engine import Engine
from .notifier.cli import render_chollos, render_report
from .providers.amadeus import AmadeusProvider
from .providers.base import PriceProvider
from .providers.demo import DemoProvider
from .providers.snapshot import SnapshotProvider
from .storage import Storage

DEFAULT_CONFIG = "config.yaml"
EXAMPLE_CONFIG = "config.example.yaml"


def _build_provider(name: str, config: Config) -> PriceProvider:
    if name == "demo":
        return DemoProvider()
    if name == "snapshot":
        return SnapshotProvider(config.snapshots_dir)
    if name == "amadeus":
        am = config.amadeus
        return AmadeusProvider(
            api_key=am.api_key,
            api_secret=am.api_secret,
            hostname=am.hostname,
            max_hotels=am.max_hotels,
            currency=config.currency,
        )
    raise SystemExit(f"Proveedor desconocido: {name} (usa 'snapshot', 'demo' o 'amadeus')")


def cmd_init(args: argparse.Namespace) -> int:
    if os.path.exists(DEFAULT_CONFIG) and not args.force:
        print(f"Ya existe {DEFAULT_CONFIG} (usa --force para sobrescribir).")
    elif os.path.exists(EXAMPLE_CONFIG):
        shutil.copy(EXAMPLE_CONFIG, DEFAULT_CONFIG)
        print(f"Creado {DEFAULT_CONFIG} a partir de {EXAMPLE_CONFIG}.")
    else:
        print(f"No se encuentra {EXAMPLE_CONFIG}.", file=sys.stderr)
        return 1

    cfg = load_config(DEFAULT_CONFIG)
    Storage(cfg.db_path).close()
    os.makedirs(cfg.snapshots_dir, exist_ok=True)
    print(f"Base de datos lista en {cfg.db_path}.")
    print(f"Carpeta de snapshots: {cfg.snapshots_dir}/")
    print("Edita config.yaml (watchlist y notificaciones) y ejecuta: python -m chollos scan")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    try:
        provider = _build_provider(args.provider, cfg)
    except Exception as exc:  # noqa: BLE001 - error de configuración del proveedor
        print(f"No se pudo iniciar el proveedor '{args.provider}': {exc}", file=sys.stderr)
        return 2
    with Storage(cfg.db_path) as storage:
        engine = Engine(cfg, provider, storage)
        result = engine.scan()

        for w in result.warnings:
            print(f"⚠️  {w}", file=sys.stderr)

        print(f"\nCotizaciones guardadas: {result.quotes_saved}")
        print(f"Chollos detectados: {len(result.chollos)} "
              f"(nuevos: {len(result.new_chollos)})\n")
        print(render_chollos(result.chollos))

        target = result.new_chollos if not args.email_all else result.chollos
        if cfg.email.enabled and target:
            ok, msg = engine.notify_email(target)
            print(f"\n📧 {msg}" if ok else f"\n📧 email no enviado: {msg}",
                  file=sys.stderr)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    with Storage(cfg.db_path) as storage:
        rows = storage.recent_chollos(limit=args.limit)
        print(render_report(rows))
    return 0


def cmd_check_amadeus(args: argparse.Namespace) -> int:
    """Comprueba que las credenciales de Amadeus conectan y hay acceso a hoteles."""
    from .providers.amadeus import AmadeusError

    cfg = load_config(args.config)
    city = args.city
    try:
        provider = AmadeusProvider(
            api_key=cfg.amadeus.api_key,
            api_secret=cfg.amadeus.api_secret,
            hostname=cfg.amadeus.hostname,
            max_hotels=cfg.amadeus.max_hotels,
            currency=cfg.currency,
        )
    except AmadeusError as exc:
        print(f"❌ {exc}")
        return 2

    print(f"Entorno: {cfg.amadeus.hostname}  ·  ciudad de prueba: {city}\n")

    # 1) Token (valida las credenciales)
    try:
        provider._get_token()
        print("✅ Credenciales válidas: token obtenido correctamente.")
    except AmadeusError as exc:
        print(f"❌ Credenciales rechazadas: {exc}")
        print("   Revisa API Key / API Secret y que el entorno (test/production) "
              "coincida con el tipo de claves.")
        return 2

    # 2) Acceso a HOTELES (Hotel List)
    try:
        hotels = provider.hotel_list(city)
    except AmadeusError as exc:
        print(f"❌ Sin acceso a la API de hoteles (Hotel List): {exc}")
        print("   Tu cuenta obtuvo token, pero el catálogo de hoteles no responde.")
        return 3
    print(f"✅ API de hoteles disponible: {len(hotels)} hoteles en {city}.")

    if not hotels:
        print("⚠️  No devolvió hoteles para esa ciudad (prueba otra con --city, p. ej. PAR).")
        return 0

    # 3) Precios reales (Hotel Search) para una muestra
    from .models import WatchItem
    sample_ids = [h["hotelId"] for h in hotels if h.get("hotelId")][:5]
    watch = WatchItem(name="check", checkin=args.checkin, checkout=args.checkout,
                      city_code=city, currency=cfg.currency)
    try:
        offers = provider.hotel_offers(sample_ids, watch)
    except AmadeusError as exc:
        print(f"⚠️  Hotel List funciona, pero Hotel Search falló: {exc}")
        return 0
    with_price = [o for o in offers if (o.get("offers"))]
    print(f"✅ Precios (Hotel Search): {len(with_price)} hoteles con oferta "
          f"para {args.checkin} → {args.checkout}.")
    print("\n🎉 Tu cuenta tiene acceso a hoteles. Ya puedes usar: "
          "python -m chollos scan --provider amadeus")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="chollos", description="Buscador de chollos (errores de precio) en hoteles.")
    p.add_argument("--config", default=DEFAULT_CONFIG, help="Ruta al fichero de configuración YAML.")
    sub = p.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Crea config.yaml y la base de datos.")
    p_init.add_argument("--force", action="store_true", help="Sobrescribe config.yaml si ya existe.")
    p_init.set_defaults(func=cmd_init)

    p_scan = sub.add_parser("scan", help="Obtiene precios, detecta chollos y avisa.")
    p_scan.add_argument("--provider", default="snapshot",
                        choices=["snapshot", "demo", "amadeus"],
                        help="Fuente de datos (por defecto: snapshot).")
    p_scan.add_argument("--email-all", action="store_true",
                        help="Envía por email todos los chollos, no solo los nuevos.")
    p_scan.set_defaults(func=cmd_scan)

    p_report = sub.add_parser("report", help="Muestra los últimos chollos guardados.")
    p_report.add_argument("--limit", type=int, default=50)
    p_report.set_defaults(func=cmd_report)

    p_check = sub.add_parser("check-amadeus",
                             help="Verifica credenciales y acceso a hoteles en Amadeus.")
    p_check.add_argument("--city", default="BCN", help="Código IATA de ciudad para la prueba.")
    p_check.add_argument("--checkin", default="2026-09-05")
    p_check.add_argument("--checkout", default="2026-09-07")
    p_check.set_defaults(func=cmd_check_amadeus)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
