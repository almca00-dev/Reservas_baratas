# Vuelos (pendiente — módulo enchufable)

El conector de Booking.com disponible **no cubre vuelos**, solo alojamientos y
atracciones. Por eso los vuelos quedan fuera de esta primera versión, pero la
arquitectura ya está lista para añadirlos sin tocar el motor de detección.

## Qué haría falta

Una fuente de precios de vuelos con API. Opciones habituales:

- **Amadeus for Developers** (Flight Offers Search) — tier gratuito.
- **Kiwi.com / Tequila API**.
- **Skyscanner (RapidAPI)**.
- **Duffel**.

Todas requieren darte de alta y obtener una clave.

## Cómo integrarlo

El sistema ya separa "de dónde salen los precios" (proveedor) de "cómo se
detecta el chollo" (motor). Para vuelos:

1. Definir el equivalente a `WatchItem`/`PriceQuote` para vuelos (origen,
   destino, fechas, aerolínea, precio) — o reutilizar `PriceQuote` mapeando
   `hotel_id`→ruta y `stars`→cabina/aerolínea.
2. Crear un `FlightsProvider(PriceProvider)` en `chollos/providers/` que llame
   a la API elegida y devuelva las cotizaciones.
3. Las estrategias de detección aplican igual:
   - **Histórica**: precio de una ruta/fecha frente a su mediana histórica.
   - **Comparativa**: precio frente a otras fechas/aerolíneas de la misma ruta.
   - Los *error fares* de vuelos suelen ser caídas del 70–90% respecto al
     precio típico de la ruta.

El almacenamiento, los avisos (consola/email) y la CLI se reutilizan tal cual.
