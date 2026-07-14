"""Motor: orquesta obtención de precios → almacenamiento → detección → aviso."""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import Config
from .detector import Detector
from .models import Chollo
from .notifier.email_notifier import EmailNotifier
from .providers.base import PriceProvider
from .storage import Storage


@dataclass
class ScanResult:
    quotes_saved: int = 0
    chollos: list[Chollo] = field(default_factory=list)
    new_chollos: list[Chollo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class Engine:
    def __init__(self, config: Config, provider: PriceProvider, storage: Storage):
        self.config = config
        self.provider = provider
        self.storage = storage
        self.detector = Detector(config.detection)

    def scan(self) -> ScanResult:
        result = ScanResult()
        if not self.config.watchlist:
            result.warnings.append("La watchlist está vacía. Añade búsquedas en config.yaml.")
            return result

        for watch in self.config.watchlist:
            try:
                quotes = self.provider.fetch(watch)
            except NotImplementedError as exc:
                result.warnings.append(f"[{watch.name}] proveedor no disponible: {exc}")
                continue
            except Exception as exc:  # noqa: BLE001 - reportamos y seguimos
                result.warnings.append(f"[{watch.name}] error al obtener precios: {exc}")
                continue

            if not quotes:
                result.warnings.append(
                    f"[{watch.name}] sin cotizaciones "
                    f"(¿falta un snapshot en '{self.config.snapshots_dir}'?)."
                )
                continue

            # Detectar ANTES de guardar, para que el histórico no incluya la
            # observación actual al calcular el baseline.
            chollos = self.detector.detect_batch(quotes, self.storage.history_prices)
            result.quotes_saved += self.storage.save_quotes(quotes)

            for ch in chollos:
                result.chollos.append(ch)
                if self.storage.record_chollo(ch):
                    result.new_chollos.append(ch)

        result.chollos.sort(key=lambda c: c.score, reverse=True)
        result.new_chollos.sort(key=lambda c: c.score, reverse=True)
        return result

    def notify_email(self, chollos: list[Chollo]) -> tuple[bool, str]:
        notifier = EmailNotifier(self.config.email)
        ready, reason = notifier.is_ready()
        if not ready:
            return False, reason
        if not chollos:
            return False, "no hay chollos nuevos que enviar"
        notifier.send(chollos)
        return True, f"email enviado a {', '.join(self.config.email.to)}"
