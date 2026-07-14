"""Render de chollos por consola (texto plano, sin dependencias)."""

from __future__ import annotations

from typing import Iterable

from ..models import Chollo


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def render_chollos(chollos: list[Chollo]) -> str:
    if not chollos:
        return "No se han detectado chollos en este escaneo."

    lines = [f"🔥 {len(chollos)} chollo(s) detectado(s):", ""]
    for i, ch in enumerate(chollos, 1):
        q = ch.quote
        lines.append(
            f"{i}. {q.name}  [{q.stars or '?'}*]  {q.city or ''}".rstrip()
        )
        lines.append(
            f"   {q.price_per_night:.0f} {q.currency}/noche  ·  "
            f"total {q.price_total:.0f} {q.currency} ({q.nights} noche/s)  ·  "
            f"-{_fmt_pct(ch.discount_pct)} vs normal  ·  score {ch.score:.0f}"
        )
        lines.append(f"   motivo: {ch.reason} — {ch.detail}")
        lines.append(f"   {q.checkin} → {q.checkout}")
        if q.url:
            lines.append(f"   {q.url}")
        lines.append("")
    return "\n".join(lines).rstrip()


def render_report(rows: Iterable) -> str:
    rows = list(rows)
    if not rows:
        return "Aún no hay chollos registrados. Ejecuta `chollos scan`."

    header = f"{'FECHA':10}  {'HOTEL':38}  {'€/NOCHE':>8}  {'DESC':>5}  MOTIVO"
    out = [header, "-" * len(header)]
    for r in rows:
        name = (r["name"] or "")[:38]
        ci = (r["checkin"] or "")[:10]
        out.append(
            f"{ci:10}  {name:38}  {r['price_per_night']:>8.0f}  "
            f"{r['discount_pct'] * 100:>4.0f}%  {r['reason']}"
        )
    return "\n".join(out)
