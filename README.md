# Buscador de chollos (errores de precio) — hoteles

Herramienta que vigila precios de alojamientos en Booking, aprende el precio
"normal" de cada hotel y **avisa cuando aparece un precio anómalamente bajo**,
candidato a un error de tarifa (reservar por 10 € lo que cuesta 100 €).

> **Expectativas realistas.** No existe forma de "forzar" un error de precio.
> Lo que hace esta herramienta es lo mismo que servicios tipo *Secret Flying*
> o *Jack's Flight Club*: monitorizar y detectar anomalías para que reacciones
> rápido. Que el hotel **honre** una reserva a precio erróneo no está garantizado.

## Cómo detecta chollos

Dos estrategias complementarias (`chollos/detector.py`):

1. **Histórica** — compara el precio actual de una estancia contra su propio
   precio normal (mediana de observaciones anteriores). Detecta caídas bruscas.
   Necesita historial, que se va acumulando en cada escaneo.
2. **Comparativa** — compara el precio/noche de un hotel contra la mediana de
   sus vecinos de la misma categoría (estrellas) en esa búsqueda. Detecta
   precios absurdos **desde el primer escaneo**, sin historial.

Más un **umbral absoluto** opcional (avisa por debajo de X €/noche) y un
**suelo** que descarta precios corruptos (p. ej. 0,50 €).

Todos los umbrales se configuran en `config.yaml`.

## Instalación

```bash
pip install -r requirements.txt
python -m chollos init          # crea config.yaml y la base de datos
```

## Uso

```bash
# Ver la detección en acción con datos de demostración (incluye un error inyectado)
python -m chollos scan --provider demo

# Escanear con datos reales (ver "Fuente de datos" más abajo)
python -m chollos scan

# Ver los últimos chollos guardados
python -m chollos report
```

Edita `config.yaml` para definir tu **watchlist** (destinos, fechas, ocupación)
y las reglas de detección.

## Fuente de datos (importante)

El conector oficial de **Booking.com** solo está disponible **dentro de una
sesión de Claude**, no para un script que corre solo. Por eso el sistema usa
una capa de **proveedores** intercambiable (`chollos/providers/`):

| Proveedor        | Estado | Uso |
|------------------|--------|-----|
| `AmadeusProvider`  | ✅ activo | **API real de hoteles** (Amadeus Self-Service). Funciona sola, sin snapshots. Requiere clave gratuita. |
| `SnapshotProvider` | ✅ activo | Lee snapshots JSON con el formato de Booking desde `snapshots/`. |
| `DemoProvider`     | ✅ activo | Datos sintéticos con un error inyectado, para probar/demostrar. |
| `BookingApiProvider` | 🔌 hueco | Para la Demand API de Booking o un proveedor RapidAPI. |

### Amadeus (recomendado, API real)

Fuente de datos real que permite que la herramienta funcione sola (con `cron`),
sin depender de snapshots.

1. Alta gratuita en <https://developers.amadeus.com>.
2. Crea una app en *My Self-Service Workspace* y copia **API Key** y **API Secret**.
3. Guárdalas en variables de entorno (nunca en el YAML):
   ```bash
   export AMADEUS_API_KEY="tu_api_key"
   export AMADEUS_API_SECRET="tu_api_secret"
   ```
4. En `config.yaml`, cada búsqueda debería llevar su `city_code` (código IATA de
   ciudad, p. ej. `BCN`, `ROM`, `PAR`); si falta, se intenta resolver desde
   `destination`. Ajusta `sources.amadeus` (entorno `test`/`production` y
   `max_hotels`).
5. Ejecuta:
   ```bash
   python -m chollos scan --provider amadeus
   ```

> **test vs production.** El entorno `test` es gratis pero con datos limitados y
> cacheados (ideal para montar y probar). Para precios reales en vivo hay que
> pasar la app a `production` en el panel de Amadeus (sigue teniendo cuota
> gratuita mensual) y poner `hostname: production`.

### Flujo con snapshots (recomendado hoy)

1. Pide a Claude (con el conector de Booking activo) que busque tus destinos
   y guarde los resultados como snapshot. La función auxiliar
   `chollos.providers.snapshot.save_snapshot(...)` deja el fichero con el
   formato correcto en `snapshots/`.
2. Ejecuta `python -m chollos scan`. El motor ingiere el snapshot más reciente
   de cada búsqueda, guarda el historial y detecta chollos.
3. Repite periódicamente (p. ej. con `cron`): cada snapshot nuevo alimenta la
   detección histórica.

En `fixtures/booking_barcelona_real.json` tienes un snapshot **real** de ejemplo
(cópialo a `snapshots/` para probar el flujo con datos verdaderos).

### Programar escaneos (cron)

```cron
# Cada 3 horas (con Amadeus; exporta antes AMADEUS_API_KEY y AMADEUS_API_SECRET)
0 */3 * * * cd /ruta/Reservas_baratas && /usr/bin/python3 -m chollos scan --provider amadeus >> data/scan.log 2>&1
```

## Avisos por email (Gmail)

En `config.yaml`, sección `notifications.email`:

```yaml
notifications:
  email:
    enabled: true
    username: "tucorreo@gmail.com"
    to: ["tucorreo@gmail.com"]
    password_env: CHOLLOS_EMAIL_PASSWORD
```

Gmail exige una **contraseña de aplicación** (no tu contraseña normal):
Cuenta de Google → Seguridad → Verificación en 2 pasos → Contraseñas de
aplicaciones. Guárdala en una variable de entorno (nunca en el YAML):

```bash
export CHOLLOS_EMAIL_PASSWORD="xxxx xxxx xxxx xxxx"
```

Por defecto solo se envían por email los **chollos nuevos** (no repite avisos
del mismo precio). Usa `--email-all` para enviar todos.

## Vuelos

Aún no implementado, pero **la misma cuenta de Amadeus incluye la API de
vuelos** (Flight Offers Search), así que el siguiente paso natural es un
`FlightsProvider` que reutilice las credenciales ya configuradas. La
arquitectura está preparada: basta un proveedor que cumpla `PriceProvider` y el
resto del sistema (almacenamiento, detección, avisos) funciona igual. Ver
`flights/README.md`.

## Estructura

```
chollos/
  models.py            # PriceQuote, WatchItem, Chollo
  config.py            # carga de config.yaml
  storage.py           # SQLite: histórico de precios + chollos
  detector.py          # estrategias de detección
  engine.py            # orquestación fetch → store → detect → notify
  cli.py               # interfaz de línea de comandos
  providers/           # fuentes de datos (snapshot, demo, booking_api)
  notifier/            # avisos (consola, email)
fixtures/              # snapshot real de ejemplo
tests/                 # pytest
```

## Tests

```bash
python -m pytest -q
```

## Aviso legal

Uso personal e informativo. El scraping directo de Booking va contra sus
términos de uso; usa el conector oficial o una API con licencia. Detectar un
precio no obliga al proveedor a mantenerlo.
