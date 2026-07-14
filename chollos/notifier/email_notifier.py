"""Aviso de chollos por email (SMTP, p. ej. Gmail).

Para Gmail necesitas una "contraseña de aplicación" (no tu contraseña normal):
Cuenta de Google → Seguridad → Verificación en 2 pasos → Contraseñas de
aplicaciones. Guárdala en la variable de entorno indicada en `password_env`
(por defecto CHOLLOS_EMAIL_PASSWORD). Nunca la escribas en el YAML.
"""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ..config import EmailConfig
from ..models import Chollo


def _html(chollos: list[Chollo]) -> str:
    items = []
    for ch in chollos:
        q = ch.quote
        items.append(
            "<li style='margin-bottom:12px'>"
            f"<b>{q.name}</b> [{q.stars or '?'}*] — {q.city or ''}<br>"
            f"<span style='color:#0a0;font-size:1.1em'>{q.price_per_night:.0f} {q.currency}/noche</span> "
            f"(total {q.price_total:.0f} {q.currency}, {q.nights} noche/s) · "
            f"<b>-{ch.discount_pct * 100:.0f}%</b> vs precio normal<br>"
            f"<small>{ch.reason}: {ch.detail}</small><br>"
            f"{q.checkin} → {q.checkout}<br>"
            f"<a href='{q.url}'>Ver en Booking</a>"
            "</li>"
        )
    return (
        "<h2>🔥 Chollos detectados</h2>"
        "<p>Posibles errores de precio. Revísalos y reserva rápido si te interesan "
        "(no está garantizado que el hotel los honre).</p>"
        f"<ul>{''.join(items)}</ul>"
    )


def _text(chollos: list[Chollo]) -> str:
    from .cli import render_chollos
    return render_chollos(chollos)


class EmailNotifier:
    def __init__(self, config: EmailConfig):
        self.cfg = config

    def is_ready(self) -> tuple[bool, str]:
        c = self.cfg
        if not c.enabled:
            return False, "email deshabilitado en la configuración"
        if not c.username or not c.to:
            return False, "faltan username o destinatarios (to)"
        if not c.password:
            return False, f"falta la contraseña en la variable de entorno {c.password_env}"
        return True, "ok"

    def send(self, chollos: list[Chollo]) -> None:
        ready, reason = self.is_ready()
        if not ready:
            raise RuntimeError(f"No se puede enviar email: {reason}")
        if not chollos:
            return

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🔥 {len(chollos)} chollo(s) de hotel detectado(s)"
        msg["From"] = self.cfg.sender or self.cfg.username
        msg["To"] = ", ".join(self.cfg.to)
        msg.attach(MIMEText(_text(chollos), "plain", "utf-8"))
        msg.attach(MIMEText(_html(chollos), "html", "utf-8"))

        with smtplib.SMTP(self.cfg.smtp_host, self.cfg.smtp_port) as server:
            server.starttls()
            server.login(self.cfg.username, self.cfg.password)
            server.sendmail(msg["From"], self.cfg.to, msg.as_string())
