# Dónde esperar para conseguir Black: investigación previa al diseño

Fecha: 2026-09-17 · Estado: **investigación, sin código** · Autor: Claude con cuatro agentes de investigación, verificación manual de las afirmaciones que deciden el diseño.

Anexos (evidencia completa, en inglés, con URL y fecha de consulta por afirmación):

- [A. Mecánica de Uber Black, exportación de datos, DEN](2026-09-17-black-demand-appendix-a-uber-mechanics.md)
- [B. Apps de la competencia para conductores](2026-09-17-black-demand-appendix-b-driver-apps-benchmark.md)
- [C. Fuentes de datos para Denver](2026-09-17-black-demand-appendix-c-data-sources.md)
- [D. Mapa, modelo y límites de la PWA](2026-09-17-black-demand-appendix-d-map-and-model.md)

## 1. Resultado

**Recomendación: construir el enfoque B, "tu historial más proxies", en dos fases.** Fase 1 sin mapa: importar tu exportación de Uber, registrar ofertas y esperas con un toque, y un planificador semanal de mejores bloques de horas. Fase 2: el mapa de hexágonos en vivo, alimentado por lo mismo. Coste obligatorio de la versión 1: **0 $/mes**. Opcional: entre 19 y 78 $/mes por horarios de vuelos en vivo a 7 días.

Lo que lo justifica, en una frase cada uno:

- Nadie en el mercado, ni Uber en lo que documenta al conductor, te da la probabilidad de **oferta Black neta de competencia**; eso solo sale de tus propios registros.
- La exportación de datos de tu cuenta de conductor trae el **producto de cada viaje** y, si incluye el archivo de estados en línea, **dónde y cuánto esperaste** cada vez. Es el arranque del modelo, no un proxy.
- La PWA no puede grabar tu GPS mientras Uber está en primer plano, así que el registro tiene que ser de un toque; es barato y es lo único que mide lo que importa.

## 2. Lo que pediste y la vara de medir

Pediste una herramienta que te diga dónde posicionarte para maximizar la probabilidad de Black SUV, Black y por último Comfort, con el aeropuerto como objetivo principal; que prediga con días de antelación qué días y horas trabajar; que use zonas de ingresos altos, hoteles de lujo, y el volumen de vuelos entrantes y salientes de DEN; y que lo muestre como un heatmap de Denver y alrededores. Y añadiste la condición que gobierna todo: **si no da una ventaja sobre lo que ya tienes en la app de Uber, no tiene sentido.**

Así que cada pieza de este informe pasa por la pregunta "¿qué te da esto que Uber no?". Lo que no la pasa, no entra.

## 3. Hallazgos que deciden el diseño

Cada uno con el nivel de evidencia. "Verificado" significa que leí la fuente original yo mismo, no un agente.

| # | Hallazgo | Evidencia |
|---|---|---|
| 1 | **Uber te deja recibir solo Black.** "When you're online, you can choose to receive only Uber Black trip requests. Or you can also accept UberX and/or UberXL trips." Rating mínimo 4,85 sobre los últimos 500 viajes. | Verificado, uber.com/drive/services/uberblack |
| 2 | **La exportación de datos de conductor trae el producto por viaje** (`product_type_name`, `global_product_name`), hora de solicitud, inicio y bajada, tarifa, surge, y si fue viaje de aeropuerto (`is_airport_trip`). En el formato actual **no trae coordenadas** del viaje. | Verificado: esquema de 73 columnas de una exportación de Los Ángeles 2022–2025 |
| 3 | **Existe un archivo "Driver Online Offline"** con segmentos `open` (en línea esperando), `enroute`, `ontrip` y `offline`, cada uno con latitud y longitud de inicio y fin, hora y duración. Es exactamente la "exposición": dónde y cuánto esperaste. | Verificado en una muestra de París 2021. **No confirmado en exportaciones de EE. UU. de 2025**: la de Los Ángeles usó solo viajes, pagos y valoraciones. Hay que ver la tuya |
| 4 | **La API oficial de conductor no sirve**: acceso "limitado" y el esquema de viajes no tiene campo de producto. | Verificado, developer.uber.com |
| 5 | **Las apps del mercado no tienen demanda por producto.** Gridwise y Solo, las únicas vivas con posicionamiento, usan medianas de la multitud de 4 semanas más vuelos y eventos. Se conectan compartiendo credenciales vía Argyle; Uber y Lyft han amenazado con desactivar cuentas por herramientas de terceros. | Anexo B, fuentes múltiples |
| 6 | **El heatmap de Uber**: su blog de ingeniería (18-nov-2025) dice que predice ganancias por hora en hexágonos H3 de resolución 9, se actualiza cada 10 minutos y agrupa conductores por "línea de negocio y tipo de vehículo" con una categorización propia. La documentación al conductor no menciona ningún filtro por producto. Son dos fuentes que no se contradicen pero no cierran la pregunta. Lo que sí es un hecho: **con ese mapa en pantalla pasas horas en downtown sin Black.** Mida lo que mida, no mide tu tasa de oferta Black neta de competencia. | Verificado el blog; documentación al conductor por agente |
| 7 | **DEN**: cola FIFO en el Commercial Hold Lot, recogida en nivel 5 isla 5, Rematch tras dejar pasajero y ExpressMatch. **Ninguna mención a Black ni a colas por producto.** | Verificado, página de DEN para conductores de Uber |
| 8 | **Saturación de Black en Denver**: "at least 75 online" en cualquier momento y "at least 50 or 60" en DIA, "one or two rides per day" (conductor de Denver, ene-2024). | **Fuente única de foro**, Reddit inaccesible. Tratar como indicio, no como dato |
| 9 | **Reserve**: los conductores ven viajes programados "up to a week ahead", con 45 minutos en línea antes para productos premium, y respeta tus filtros. Es una señal de demanda a días vista que **ya tienes** en la app. | Verificado, FAQ de Reserve |
| 10 | **Google retiró su heatmap de Maps JS** (depreciado mayo 2025, fuera de servicio mayo 2026) y recomienda deck.gl. | Verificado, developers.google.com/maps/deprecations |
| 11 | **Una PWA instalada no puede grabar GPS en segundo plano** ni en iOS ni en Android mientras otra app está delante. | Anexo D, caniuse + WebKit + Chromium |

Dos consecuencias de los hallazgos 1 y 8 que conviene decir antes de diseñar nada:

- Si hoy recibes pings de X y Comfort, o no tienes activado el filtro "solo Black" o lo desactivas para no quedarte parado. **Necesito saber cuál de las dos** porque cambia lo que significan tus registros. Mi asunción de trabajo: lo desactivas a ratos.
- Con 50 o 60 Black en el lote de DEN y sin cola separada por producto, "esperar en el lote a un Black" puede ser la peor estrategia de aeropuerto. Tu exportación lo dirá con números: `is_airport_trip` × producto × hora.

## 4. Los datos

### 4.1 Los tuyos (lo que hay hoy en Black Volt)

Medido en producción el 17-sep:

| Fuente | Qué hay |
|---|---|
| Reservas privadas Black Volt | 78 viajes, abril a septiembre, sin coordenadas. Origen más frecuente DEN (18), Parker (14), Lone Tree (12). Destino DEN en 35 de 78 |
| Capturas de Uber en "My Stats" | 21 semanas de totales: viajes, ganancias y horas en línea por semana. Ningún viaje individual |

Ninguna de las dos fuentes tiene un viaje de Uber con lugar y hora. Por eso la exportación de Uber es el primer paso.

### 4.2 La exportación de tu cuenta de conductor de Uber

Se pide desde la página de ayuda "Request your personal Uber data" (enlace directo, tarda horas o días). Contiene "Details on each trip, including start and end times, distance traveled and fare information" y analíticos de dispositivo de los últimos 30 días.

Archivos vistos en exportaciones reales:

| Archivo | Columnas que importan | Visto en |
|---|---|---|
| `driver_lifetime_trips-0.csv` | `product_type_name`, `request/begintrip/dropoff_timestamp_local`, `is_airport_trip`, `is_scheduled_trip`, tarifa desglosada, `surge_multiplier`, `city_name` | EE. UU. 2025 (73 columnas), París 2021 |
| `Driver Online Offline.csv` | `earner_state` (open/enroute/ontrip/offline), `begin_lat`, `begin_lng`, `end_lat`, `end_lng`, `begin/end_timestamp_local`, `duration_ms` | París 2021 (1.526 segmentos) |
| `Driver Dispatches Offered and Accepted.csv` | por ventana: `dispatches`, `rejections`, `accepts`, `expireds`, `minutes_online`, `minutes_active` | París 2021. Sin producto ni lugar |
| `driver_app_analytics-0.csv` | `lat`, `lng`, `gps_time_ms`, `driver_status` | EE. UU. 2022. Solo 30 días |
| `Lost Time details (Driver).csv` | minutos sin tarea entre viajes con coordenadas | EE. UU. 2022 (formato antiguo) |

Si tu exportación trae el archivo de estados, el modelo nace con meses de "esperé aquí tantos minutos y acepté una oferta aquí". Si no lo trae, el respaldo es pedir la exportación cada mes para acumular los 30 días de GPS, más el registro de un toque.

Lo que la exportación **no** puede dar: las ofertas Black que rechazaste o que no llegaron. Eso solo se captura en vivo.

### 4.3 Proxies estáticos (dónde vive y se aloja el dinero)

| Capa | Fuente | Coste | Nota |
|---|---|---|---|
| Ingreso mediano y % de hogares > 200 k$ por tract | Census ACS 2020–2024, variables `B19013_001E`, `B19001_017E`, `B19001_001E`; polígonos `cb_2025_08_tract_500k` | 0 $ | La clave de API ya es obligatoria; sin ella devuelve HTML en silencio |
| Hoteles de lujo | Lista curada a mano con AAA Diamond y Forbes: 5◆ Four Seasons y Ritz-Carlton; 4◆ Brown Palace, Oxford, Crawford, Limelight (antes Kimpton Born), Halcyon, Thompson, Clio (antes JW Marriott Cherry Creek), Monaco, Le Méridien, Gaylord Rockies, Inverness, Omni Interlocken, St Julien Boulder, Populus, Kimpton Claret | 0 $ | OSM tiene 366 hoteles en el metro y **cero** con etiqueta de estrellas; no sirve como filtro de lujo. Coordenadas desde OSM o dirección pública, no desde Places (su política solo permite guardar `place_id`) |
| Aviación privada | FBOs: Signature APA-South y North, Modern Aviation, Denver jetCenter (Centennial); Signature y Sheltair (Rocky Mountain Metro); Signature DEN | 0 $ | A mano |
| Otros generadores | DTC, LoDo, RiNo, Cherry Creek Shopping Center, Anschutz, clubes privados, colegios privados (directorio CDE) | 0 $ | A mano |
| Zonas afluentes ya curadas en el repo | `TARGET_ZONES` en `uber_research.py`: Cherry Hills, DTC, Castle Pines, Lone Tree, Highlands Ranch, Cherry Creek, Wash Park, LoDo, Boulder, Golden, con puntuación de afluencia 1–3 | 0 $ | Reusar |

### 4.4 Señales que cambian con el tiempo

| Capa | Fuente | Coste | Horizonte |
|---|---|---|---|
| Vuelos DEN, línea base por hora × día de la semana × mes | BTS On-Time (salidas y llegadas programadas por vuelo, último mes junio 2026, retraso de unas 6 semanas). Solo aerolíneas de EE. UU. y vuelos domésticos; el banco internacional se dimensiona con T-100 | 0 $ | Perfil típico, estable semana a semana |
| Vuelos DEN, programados en vivo 7 días | FlightAware AeroAPI `/schedules` (hasta 1 año adelante; cálculo del agente ≈ 78 $/mes tirando semanalmente ~13.500 vuelos). Probar antes AeroDataBox (19 $/mes) para ver si llega a +7 días | 19–78 $ | Refina la línea base en cambios de temporada |
| Volumen mensual de pasajeros DEN | PDFs mensuales de flydenver.com (bloquea robots; descarga manual) | 0 $ | Factor de escala |
| Eventos | Ticketmaster y SeatGeek ya integrados en `events_scan.py`; Convention Center, Red Rocks y DCPA sin feed, hay que raspar su HTML; National Western 9–24 ene 2027 fijo | 0 $ | 7 días y más |
| Clima | NWS `api.weather.gov` (horario, 7 días, sin restricción comercial). Open-Meteo gratuito es solo no comercial; Black Volt es una LLC | 0 $ | 7 días |
| Reserve | Lo ves en la app hasta 7 días antes. No hay API; se registra a mano si quieres que cuente | 0 $ | 7 días |
| Datos públicos de viajes TNC | **No existen para Denver ni Colorado.** Chicago y NYC publican viajes pero sin nivel de producto | — | — |

## 5. Cómo funcionaría el modelo, en lenguaje llano

Lo que se estima es una **tasa**: ofertas Black por minuto de espera en cada hexágono y hora de la semana. De ahí sale la probabilidad de recibir al menos una en N minutos. Con dos vistas:

1. **Ahora**: mapa de hexágonos H3 de resolución 8 (unos 530 m de lado, una zona que cruzas en un minuto) para las próximas 3 horas, recalculado cada 15 minutos.
2. **Esta semana**: cuadrícula de 7 días × 24 horas por zona, con los mejores bloques de 2 horas o más y el motivo ("DEN 47 llegadas 21:00–22:00", "Ball Arena 19:00").

Cómo aprende:

- **Arranque**: un prior construido con los proxies (hoteles, tracts ricos, bancos de vuelos, eventos). Se muestra etiquetado como "sin datos propios todavía".
- **Con tus datos**: cada minuto que esperas en un hexágono suma exposición; cada oferta Black que te llega suma un evento. La estimación de cada celda es una mezcla ponderada del prior y tus datos (Gamma-Poisson empírico), y el peso de tus datos crece con las horas registradas. Cada celda lleva su confianza: "x % viene de tus datos, y horas registradas". Las celdas con poca base se pintan rayadas, no se esconden.
- **Ranking**: no por probabilidad bruta sino por probabilidad menos el coste de llegar, como hace DiDi en su sistema de reposicionamiento.
- **Más adelante**: con miles de horas registradas, gradient boosting con festivos, temporada de esquí y clima. Antes de eso memorizaría.

**La pieza sin la cual no hay modelo es el registro de ofertas con producto.** Los cuatro botones de un toque (en línea, aquí, oferta recibida, fuera) deben llevar en "oferta" el producto: Black SUV, Black, Comfort, X. Sin ese toque extra, la cantidad central no se puede medir.

Esto es lo que ninguna app hace y Uber no te muestra: **tus** ofertas Black por minuto de **tu** espera, que ya descuentan a los otros 75 conductores.

## 6. Tecnología

| Decisión | Elección | Por qué |
|---|---|---|
| Mapa | MapLibre GL JS 6.x con teselas de OpenFreeMap (sin clave, sin límite, atribución) y un extracto PMTiles de Colorado en el VPS como respaldo | Google retiró su heatmap; MapLibre tiene capa de calor y de relleno nativas; ninguna clave de navegador que exponer. Places y Directions se quedan en el servidor y fuera de ese mapa, que es lo que exigen los términos de Google |
| Rejilla | H3 resolución 8, suavizado con vecinos k=1, agrupado a resolución 7 al alejar | Es la rejilla de Uber; 2.000 celdas pesan 9 KB comprimidas como lista compacta, y el navegador dibuja los polígonos con `h3-js` |
| Cálculo | Tarea programada en proceso aparte cada 15 min; resultados en Postgres para auditoría y en Redis para servir | Un solo cálculo, no uno por worker de la API |
| Registro | Botones de un toque con `getCurrentPosition`; auto-registro cada 60 s con wake lock mientras la PWA está en pantalla parado | Lo único que funciona en iPhone y Android sin app nativa |
| Importación | Subida del ZIP de Uber al dashboard, parser tolerante a los dos formatos vistos | Reusa el patrón de `platform_stats.py` |

Frontend y backend siguen los patrones del repo: FastAPI + SQLAlchemy async + Alembic, Next.js 14 con i18n EN y ES, nav del driver en `DriverTabBar`.

## 7. Tres enfoques y una recomendación

| | A. Solo planificador | **B. Tu historial más proxies** | C. Señales en vivo |
|---|---|---|---|
| Qué es | Importar la exportación de Uber, perfil por hora de la semana de tus Black, proxies de vuelos y eventos; sin mapa, sin registro | A más: mapa de hexágonos, registro de ofertas y esperas con producto, prior de proxies corregido por tus datos, cola de DEN registrada | B más: surge raspado de uber.com cada 15 min con `pricing-scout`, horarios de vuelos de pago, app nativa con GPS en segundo plano |
| Qué te da que Uber no | Qué días y horas trabajar, con tus datos de Black | Lo anterior y **dónde** esperar con probabilidad neta de competencia, decisión de destino, aviso de si vale ir al lote de DEN | Lo anterior y surge por producto en vivo |
| Coste | 0 $/mes | 0 $/mes; 19–78 $ opcional por vuelos en vivo | Igual más cuenta de desarrollador Apple, revisión de Google Play, y riesgo de cuenta |
| Trade-off | Barato y útil en una semana, pero no responde "dónde", que es la mitad de lo que pediste | Responde todo lo pedido; exige disciplina de registro durante semanas antes de que el mapa sea mejor que el prior | Más señal, pero el raspado de Uber viola su norma ("access Uber data in any way isn't allowed") y una app nativa es otro producto |

**Recomiendo B, en dos fases.** La fase 1 es A más el registro de un toque, sin mapa; entrega valor en la primera semana y empieza a acumular la exposición que la fase 2 necesita. La fase 2 añade el mapa cuando haya datos que pintar. Razones:

- Pasa la vara "ventaja sobre Uber" en las cuatro cosas que Uber no da: tu tasa neta de oferta Black, planificación a 7 días, decisión de destino y cola de DEN.
- Cuesta 0 $/mes en lo obligatorio y no toca tu cuenta de Uber: nada de credenciales compartidas, nada de automatizar su app.
- El riesgo principal, que el mapa tarde semanas en valer más que el prior, se mitiga porque la fase 1 ya vale por sí sola.

C queda como ampliación futura si en un mes de registros la exposición es demasiado fina para mover el modelo.

## 8. Riesgos y lo que no sabemos

- **El archivo de estados en línea puede no venir en tu exportación.** Se verá al pedirla. Sin él, el arranque es más lento: 30 días de GPS por exportación mensual más registro manual.
- **Sesgo de supervivencia**: la exportación solo tiene los viajes que hiciste. Donde nunca esperaste no hay datos; el prior cubre eso hasta que lo pises.
- **Disciplina de registro**: si no tocas "oferta recibida" cada vez, el modelo mide otra cosa. El auto-registro de 60 s cubre la espera, no las ofertas.
- **Evidencia de foros**: la saturación de Black en Denver viene de un hilo de 2024; Reddit fue inaccesible. Tus números lo confirmarán o no.
- **Cambio horario**: la cuadrícula semanal se calcula en hora de Denver; un día de 23 y otro de 25 horas rompen una 7×24 ingenua.
- **Licencias**: tres fuentes gratuitas son solo para uso no comercial (Open-Meteo, Protomaps, MapTiler). Se evitan las tres.

## 9. Tus acciones ahora

1. **Pedir la exportación de tus datos de Uber** desde la página de ayuda "Request your personal Uber data". Cuando llegue el ZIP, súbemelo o dime qué archivos trae; en particular si hay uno con `earner_state` y `begin_lat`.
2. **Confirmar cómo usas el filtro de producto**: ¿tienes "solo Black" activado siempre, a ratos, o nunca?
3. **Elegir enfoque**: B en dos fases es la recomendación. Con tu aprobación paso al diseño por secciones y luego a la especificación.

## 10. Fuentes clave

Las verificadas por mí el 2026-09-17:

- Filtro solo Black y rating: https://www.uber.com/us/en/drive/services/uberblack/
- API de conductor limitada y sin producto: https://developer.uber.com/docs/drivers/references/api/v1/partners-trips-get
- Heatmap de Uber, hex-9, 10 min, categorización por tipo de vehículo: https://www.uber.com/us/en/blog/enhancing-ubers-guidance-heatmap-with-deep-probabilistic-models/
- DEN para conductores de Uber: https://www.uber.com/global/en/r/airports/den/driver-information
- Reserve hasta 7 días: https://help.uber.com/en/driving-and-delivering/article/reserve-faq?nodeId=edd655fe-d600-44bf-97cf-e917fbd6cc72
- Pedir tus datos: https://help.uber.com/driving-and-delivering/article/request-your-personal-uber-data?nodeId=fbf08e68-65ba-456b-9bc6-1369eb9d2c44
- Esquema de la exportación de Los Ángeles (73 columnas): https://github.com/evgeniimatveev/uber-driver-analytics (sql/schema.sql)
- Muestras de exportación (París 2021 con "Driver Online Offline", EE. UU. 2022): https://github.com/digipower-academy/hestialabs-experiences (packages/lib/data-samples)
- Retirada del heatmap de Google Maps: https://developers.google.com/maps/deprecations

El resto, con URL y fecha por afirmación, en los anexos A–D.
