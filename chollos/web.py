"""Panel web ligero para ver los chollos detectados.

Sin dependencias externas: usa http.server de la librería estándar y lee de la
misma base de datos SQLite. Rutas:

    /               → página HTML con los chollos ordenados por descuento
    /api/chollos    → los mismos datos en JSON

Uso:  python -m chollos web --port 8000
"""

from __future__ import annotations

import html
import json
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .storage import Storage


def _rows_to_dicts(rows) -> list[dict]:
    return [dict(r) for r in rows]


def _page(stats: dict, chollos: list[dict]) -> str:
    last = stats.get("last_observation") or "—"
    cards = f"""
      <div class="cards">
        <div class="card"><div class="num">{len(chollos)}</div><div class="lbl">chollos</div></div>
        <div class="card"><div class="num">{stats['quotes']}</div><div class="lbl">precios observados</div></div>
        <div class="card"><div class="num">{stats['watches']}</div><div class="lbl">búsquedas</div></div>
        <div class="card"><div class="num small">{html.escape(str(last))}</div><div class="lbl">última observación</div></div>
      </div>
    """

    if not chollos:
        body = ('<p class="empty">Aún no hay chollos. Ejecuta '
                '<code>python -m chollos scan</code> (o <code>--provider demo</code>).</p>')
    else:
        trs = []
        for c in chollos:
            disc = (c.get("discount_pct") or 0) * 100
            name = html.escape(str(c.get("name") or "?"))
            url = html.escape(str(c.get("url") or ""))
            city = html.escape(str(c.get("city") or ""))
            reason = html.escape(str(c.get("reason") or ""))
            detail = html.escape(str(c.get("detail") or ""))
            name_cell = f'<a href="{url}" target="_blank" rel="noopener">{name}</a>' if url else name
            trs.append(f"""
              <tr>
                <td class="disc"><span class="badge">-{disc:.0f}%</span></td>
                <td>{name_cell}<div class="sub">{city} · {c.get('checkin','')} → {c.get('checkout','')}</div></td>
                <td class="price">{c.get('price_per_night',0):.0f} {html.escape(str(c.get('currency','')))}<div class="sub">total {c.get('price_total',0):.0f}</div></td>
                <td class="base">{c.get('baseline_per_night',0):.0f}</td>
                <td><span class="tag tag-{reason}">{reason}</span><div class="sub">{detail}</div></td>
              </tr>""")
        body = f"""
          <table>
            <thead><tr>
              <th>Desc.</th><th>Hotel</th><th>Precio/noche</th><th>Normal</th><th>Motivo</th>
            </tr></thead>
            <tbody>{''.join(trs)}</tbody>
          </table>
        """

    return f"""<!doctype html>
<html lang="es"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Chollos · panel</title>
<style>
  :root {{ color-scheme: light dark; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
          margin: 0; background: #f6f7f9; color: #16181d; }}
  header {{ padding: 24px 20px 8px; }}
  h1 {{ margin: 0; font-size: 1.4rem; }}
  .muted {{ color: #6b7280; font-size: .85rem; margin-top: 4px; }}
  main {{ padding: 8px 20px 40px; max-width: 1000px; margin: 0 auto; }}
  .cards {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 16px 0 24px; }}
  .card {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 12px;
           padding: 14px 18px; min-width: 130px; flex: 1; }}
  .num {{ font-size: 1.6rem; font-weight: 700; }}
  .num.small {{ font-size: .95rem; font-weight: 600; word-break: break-all; }}
  .lbl {{ color: #6b7280; font-size: .78rem; text-transform: uppercase; letter-spacing: .03em; }}
  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff;
           border: 1px solid #e5e7eb; border-radius: 12px; overflow: hidden; }}
  th, td {{ text-align: left; padding: 12px 14px; border-bottom: 1px solid #eef0f2; vertical-align: top; }}
  th {{ font-size: .72rem; text-transform: uppercase; letter-spacing: .04em; color: #6b7280; background: #fafbfc; }}
  tr:last-child td {{ border-bottom: none; }}
  .sub {{ color: #6b7280; font-size: .78rem; margin-top: 3px; }}
  .price, .base {{ font-variant-numeric: tabular-nums; white-space: nowrap; }}
  .badge {{ background: #16a34a; color: #fff; padding: 3px 9px; border-radius: 999px;
            font-weight: 700; font-size: .82rem; white-space: nowrap; }}
  .tag {{ font-size: .72rem; padding: 2px 8px; border-radius: 6px; background: #eef2ff; color: #4338ca; }}
  .tag-historico {{ background:#fef3c7; color:#92400e; }}
  .tag-umbral_absoluto {{ background:#fee2e2; color:#991b1b; }}
  a {{ color: #2563eb; text-decoration: none; font-weight: 600; }}
  a:hover {{ text-decoration: underline; }}
  code {{ background: #eef0f2; padding: 2px 6px; border-radius: 5px; }}
  .empty {{ color:#6b7280; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background:#0f1115; color:#e6e8ec; }}
    .card, table {{ background:#171a21; border-color:#262a33; }}
    th {{ background:#1b1f27; color:#9aa2b1; }}
    td, th {{ border-color:#262a33; }}
    .muted, .lbl, .sub {{ color:#9aa2b1; }}
    code {{ background:#262a33; }}
  }}
</style></head>
<body>
  <header>
    <h1>🔥 Chollos de hotel</h1>
    <div class="muted">Candidatos a error de precio · ordenados por descuento</div>
  </header>
  <main>
    {cards}
    <div class="table-wrap">{body}</div>
  </main>
</body></html>"""


class _Handler(BaseHTTPRequestHandler):
    db_path = "data/chollos.db"

    def log_message(self, *args):  # silencia el log por request
        pass

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        with Storage(self.db_path) as st:
            stats = st.stats()
            chollos = _rows_to_dicts(st.top_chollos(limit=200))

        if self.path.startswith("/api/chollos"):
            payload = json.dumps({"stats": stats, "chollos": chollos},
                                 ensure_ascii=False, default=str).encode("utf-8")
            self._send(200, payload, "application/json; charset=utf-8")
        elif self.path in ("/", "/index.html"):
            self._send(200, _page(stats, chollos).encode("utf-8"),
                       "text/html; charset=utf-8")
        else:
            self._send(404, b"No encontrado", "text/plain; charset=utf-8")

    do_HEAD = do_GET


def serve(db_path: str, host: str = "127.0.0.1", port: int = 8000) -> None:
    handler = partial(_Handler)
    handler.db_path = db_path  # atributo de clase compartido
    _Handler.db_path = db_path
    server = ThreadingHTTPServer((host, port), _Handler)
    print(f"Panel en http://{host}:{port}  (Ctrl+C para parar)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nParado.")
    finally:
        server.server_close()
