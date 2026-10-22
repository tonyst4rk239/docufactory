# Esquema JSON de Guion Externo (`docs/esquema_guion.md`)

En **Docu Factory v3**, la redacción del guion la realiza **Pluma** (agente guionista) y **Doyou** (orquestador) entrega el archivo `.json` directamente al pipeline mediante el comando `importar`. Python valida el esquema campo por campo, sintetiza la voz (`es-US-AlonsoNeural` en 16:9 / `es-MX-JorgeNeural` en 9:16), descarga y filtra el B-roll, y renderiza los videos duales.

---

## Comandos de Importación

```bash
# Documental horizontal 16:9 (valida JSON, genera guion_doblaje.md y ejecuta continuar)
python make_video.py importar ejemplos/guion_ejemplo.json --auto

# Reel / Short vertical 9:16
python make_tiktok.py importar ejemplos/guion_ejemplo.json --auto

# Solo validar JSON y generar guion_doblaje.md / guion_montaje.txt sin renderizar
python make_video.py importar ejemplos/guion_ejemplo.json --solo-guion

# Reutilizar carpeta existente del mismo tema en lugar de crear slug con timestamp
python make_video.py importar ejemplos/guion_ejemplo.json --auto --reusar
```

---

## Estructura General del JSON (Nivel Raíz)

| Campo | Tipo | Obligatorio | Descripción |
| :--- | :--- | :---: | :--- |
| `titulo` *(o `titulo_trabajo`)* | `string` | **Sí** | Título principal del documental o Reel. Se utiliza para generar el `slug` del proyecto. |
| `formato` | `"16:9"` \| `"9:16"` | **Sí** | Relación de aspecto objetivo: `"16:9"` (Documental horizontal) o `"9:16"` (Reel/Short vertical). |
| `mood` | `string` | **Sí** | Atmósfera general: `"misterio"`, `"tension"`, `"epica"`, `"curiosidad"`, `"calma"` (también acepta `"terror"` y `"crimen"`, que mapean el grado y audio oscuro y bloquean poses festivas/financieras). |
| `top_n` | `int` \| `null` | Sí (en 16:9) | Número de puestos del ranking en cuenta regresiva (`3`, `5`, `7`...). En Reels `9:16` puede ser `null`. |
| `minutos` | `float` | Opcional | Duración objetivo en minutos (ej. `1.0`, `8.5`). Si se omite, se calcula automáticamente a razón de ~142 palabras/minuto. |
| `resumen` | `string` | Opcional | Sinopsis breve del episodio. |
| `youtube_metadata` *(o `metadatos_youtube`)* | `object` | **Sí** | Objeto con `titulos` (`list[str]`), `descripcion` (`str`) y `tags` (`list[str]`) para `publicacion/paquete_youtube.txt`. |
| `capitulos` | `list[object]` | **Sí** | Lista de capítulos con `escena_id` (`int`), `titulo` (`str`) y `timestamp` (`str`, opcional). |
| `hook` | `string` | Opcional | Frase gancho inicial (usada especialmente en formato `9:16`). |
| `bucle_loop_frase` | `string` | Opcional | Frase final de cierre en bucle para formato `9:16`. |
| `fuentes_video` | `list[object]` | Opcional | Videos fuente del episodio: `{url, credito, descripcion, articulo}`. Solo documenta; los fragmentos se declaran por escena en `clips_fuente`. |
| `escenas` | `list[object]` | **Sí** | Lista ordenada de escenas del montaje (mínimo 1 escena). |

---

## Objeto `youtube_metadata`

| Campo | Tipo | Descripción |
| :--- | :--- | :--- |
| `titulos` | `list[str]` | De 1 a 3 opciones de título de alto CTR para YouTube. |
| `descripcion` | `string` | Descripción persuasiva del video (1 a 3 párrafos). |
| `tags` | `list[str]` | Lista de etiquetas SEO (ej. `["misterios sin resolver", "documental", "historia oscura"]`). |

---

## Objeto `capitulos[]`

| Campo | Tipo | Descripción |
| :--- | :--- | :--- |
| `escena_id` | `int` | ID de la escena donde inicia este capítulo (`1`, `2`, `5`...). El pipeline calcula el segundo exacto sumando la duración real del TTS. |
| `titulo` | `string` | Nombre visible del capítulo en la barra de YouTube (ej. `"Puesto #3: La Señal Wow!"`). |
| `timestamp` | `string` (opc.) | Marca de tiempo orientativa (ej. `"00:00"`). |

---

## Estructura por Escena (`escenas[]`)

| Campo | Tipo | Obligatorio | Descripción |
| :--- | :--- | :---: | :--- |
| `id` | `int` | **Sí** | Número secuencial de la escena (`1`, `2`, `3`...). |
| `acto` | `string` | Opcional | `"gancho"`, `"contexto"`, `"conflicto"`, `"profundizacion"`, `"giro"`, `"resolucion"` o `"cta"`. Se infiere automáticamente si se omite. |
| `puesto` | `int` \| `null` | **Sí** | Número del puesto actual del ranking (`N` hasta `1`) o `null` en introducción/cierre. |
| `puesto_titulo` | `string` \| `null` | **Sí** | Título corto en **MAYÚSCULAS** (2 a 5 palabras, sin el `#N`) **únicamente en la primera escena que abre cada puesto**; `null` en escenas de continuación, intro o cierre. Dispara la tarjeta `.ass` (`TOP #N`), el riser previo, el impact y el glitch. |
| `voz` *(o `narracion`)* | `string` | **Sí** | Texto de locución en español neutro. Soporta etiquetas de pausa SSML como `<break time="400ms"/>` o `<break time="0.6s"/>`, que el motor TTS convierte en pausas naturales de respiración sin pronunciar etiquetas XML ni mostrarlas en subtítulos. |
| `pose` *(o `pose_host`)* | `string` | **Sí** | Pose del presentador 2D: `"explicando"`, `"pensativo"`, `"sorprendido"`, `"esceptico"`, `"duda"`, `"senalando"`, `"aprobando"`, `"dinero"`. |
| `host_visible` | `bool` | Opcional | `true` para mostrar el avatar del host en pantalla, `false` para B-roll a pantalla completa. Por defecto `true`. |
| `host_lado` | `"izquierda"` \| `"derecha"` | Opcional | Lado de la pantalla donde aparece el host en 16:9 (por defecto `"izquierda"`). |
| `broll_queries_en` | `list[str]` | **Sí** | Lista de **2 a 3 consultas en inglés** (3 a 5 palabras cada una, concretas y filmables) para buscar en Pexels, Pixabay y YouTube (de más específica a plano alternativo). |
| `broll_mood_keywords` | `list[str]` | **Sí** | Lista de 2 a 4 palabras de atmósfera en inglés para puntuar los candidatos (ej. `["dark", "cinematic", "night", "archival"]`). |
| `broll_avoid_keywords` | `list[str]` | **Sí** | Lista de 3 a 6 términos en inglés que deben **rechazarse** si aparecen en los metadatos/tags del clip (ej. `["escalator", "sunny", "beach", "cartoon", "happy"]`). |
| `broll_descripcion` | `string` | Opcional | Descripción en español del plano ideal para la guía de montaje. |
| `music_mood` *(o `musica`)* | `string` | **Sí** | Carpeta de música de fondo para la escena: `"misterio"`, `"tension"`, `"epica"`, `"curiosidad"`, `"calma"`. |
| `sfx` | `string` | **Sí** | Efecto de sonido puntual: `"ninguno"`, `"whoosh"`, `"impacto"`, `"riser"`, `"tension"`, `"revelacion"`, `"glitch"`, `"ambiente"`, `"digital"`, `"click"`, `"transicion"`. |
| `texto_pantalla` | `string` | Opcional | Se autogenera como `"#N: PUESTO_TITULO"` en los inicios de puesto si se deja vacío. |
| `texto_destacado` | `string` | Opcional (9:16) | 1 a 2 palabras clave en MAYÚSCULAS para activar el *zoom punch* y el color destacado del karaoke en Reels `9:16`. |
| `clips_fuente` | `list[object]` | Opcional | Fragmentos **reales** (videos virales de redes) con prioridad sobre el B-roll libre. Ver sección *Clips reales*. |
| `capitulo` | `string` \| `null` | Opcional | Nombre del capítulo si esta escena inicia uno (también puede definirse en la lista raíz `capitulos`). |

---

## Reglas de Validación Estricta

1. **Bloqueo de pose `"dinero"` en temas oscuros**:
   - Si el guion tiene `mood` (o `music_mood`) en `"misterio"`, `"terror"`, `"crimen"` o `"tension"`, el validador **rechazará** cualquier escena que tenga `"pose": "dinero"` indicando exactamente el índice de la escena (`escenas[i].pose`).
2. **Pausas SSML y Presupuesto de Duración**:
   - En `16:9`, calcula aproximadamente **140–145 palabras habladas por minuto** (sin contar etiquetas `<break time="..."/>`).
   - En `9:16`, usa micro-escenas de 2 a 3 segundos (6 a 10 palabras por escena).
3. **Tarjetas `TOP #N`**:
   - La primera escena de cada puesto debe incluir `puesto` (entero) y `puesto_titulo` (en mayúsculas). La tarjeta `.ass` aparecerá automáticamente `0.35 s` después del efecto glitch/transición con tamaño legible y fondo semitransparente.

---

## Clips reales (`clips_fuente`) — panel "EVIDENCIA"

Cada escena puede declarar fragmentos del video viral original. El pipeline los descarga **primero** con `yt-dlp`
(YouTube, TikTok, X/Twitter, Facebook, Instagram, streams `.m3u8` de medios y cualquier sitio soportado; usa
`YTDLP_COOKIES` si está configurado), descarga **solo el rango pedido** (nunca el video completo) y lo transforma:

- panel al ~70 % (`clips_reales.escala_panel`) sobre el mismo video desenfocado y oscurecido,
- zoom lento, marco amarillo, etiqueta superior (`EVIDENCIA` por defecto) y crédito `Fuente: <credito>`,
- caja de resalte opcional (`resaltar`),
- el panel y los textos se colocan en el lado opuesto al host (`host_lado`), sin solaparlo.

| Campo | Tipo | Obligatorio | Descripción |
| :--- | :--- | :---: | :--- |
| `url` | `string` | **Sí** | URL http(s) del video original. |
| `inicio` | `float` | Opcional | Segundo de inicio del fragmento (por defecto `0`). |
| `duracion` | `float` | Opcional | 3 a 6 s (se recorta a ese rango; por defecto `4`). |
| `credito` | `string` | Recomendado | Autor/cuenta/medio visible en pantalla (ej. `"TikTok @soymac69"`). |
| `etiqueta` | `string` | Opcional | Texto de la etiqueta del panel (por defecto `"EVIDENCIA"`). |
| `resaltar` | `[x, y, w, h]` | Opcional | Caja roja de resalte en fracciones 0-1 del fragmento. |
| `estilo` | `string` | Opcional | `evidencia` (panel con marco, por defecto), `completo` (pantalla completa con viñeta; vertical centrado en la zona libre), `dividido` (ORIGINAL vs ACERCAMIENTO de `resaltar`), `congelado` (reproduce ~45 % y congela el cuadro con resalte). El crédito `Fuente:` siempre queda visible. Si la escena abre con tarjeta TOP/texto, la 1.ª toma real se fuerza a `completo` y ≥ 4 s para que la tarjeta no caiga sobre un panel. |
| `recorte` | `[x, y, w, h]` | Opcional | Recorte previo en fracciones 0-1 para quitar barras, subtítulos o gráficos del medio original. Las tomas oscuras (YAVG < `clips_reales.yavg_realce`) se aclaran automáticamente. |

Los clips reales **no** pasan por el filtro anti-creador del B-roll libre, pero quedan registrados con
`fuente: "real"` en `b_roll/broll_reporte.md` (sección *Tomas por Escena*) y en `b_roll/revision.json` (`tomas[]`).
Si una descarga falla, se registra como rechazo y la escena se rellena con B-roll libre.

```json
"clips_fuente": [
  {"url": "https://www.tiktok.com/@soymac69/video/7201181925028023558", "inicio": 2, "duracion": 6, "credito": "TikTok @soymac69"}
]
```

Ejemplo completo: `ejemplos/guion_ejemplo_clips_reales.json`.

---

## Retención: tomas de 3-5 s por escena

Cada escena se divide en tomas de `tomas.corte_min_s`-`tomas.corte_max_s` segundos (`config/edicion.yaml`, por
defecto 3-5 s). Los clips reales ocupan las primeras tomas; el resto rota entre varios clips libres **distintos**
(máx. `tomas.max_clips_distintos_por_escena`, sin duplicados en todo el video y evitando series consecutivas de
Pixabay), buscados con consultas cortas de 2-3 palabras derivadas de `broll_queries_en`.
Manifiesto por escena: `b_roll/escena_XXX_tomas.json`. La revisión genera un cuadro por toma
(`b_roll/revision/escena_XXX_toma_NN.jpg`) y lo lista en `revision.json -> tomas[]`.

## Campos opcionales de estilo (raíz del guion) — v2026-10

Todos son opcionales y retrocompatibles: un guion sin ellos se ve exactamente como antes (tono `misterio`, con avatar).

| Campo | Tipo | Default | Valores |
|---|---|---|---|
| `tono` | string | `"misterio"` | `misterio`, `polemica`, `investigacion`, `humor`, `epico`, `drama`, `curiosidad`, `terror` |
| `usar_avatar` | bool | `true` | `false` = el host NO aparece en ninguna escena del video ni en la miniatura (ignora `host_visible`) |
| `miniatura` | objeto | `null` | `{titulo, subtitulo, sello, pose, layout}`, todos opcionales |

**`tono`** define el grado de color del render (16:9 y 9:16) y el estilo de la miniatura (paletas, sellos, poses, fuentes):
- `misterio`: grado oscuro/desaturado actual por `music_mood` (sin cambios).
- `terror`: más oscuro y frío, sombras aplastadas.
- `polemica`: saturado y cálido/rojo, con punch.
- `investigacion`: neutro frío, saturación natural.
- `humor`: brillante y muy saturado.
- `epico`: alto contraste teal-orange.
- `drama`: cálido suave, contraste medio.
- `curiosidad`: limpio, saturación ligeramente alta.
Fuera de `misterio`/`terror` los clips reales no se desaturan. Se aceptan alias con acento (`polémica`, `investigación`, `épico`). Un valor desconocido es error de validación.

**`miniatura`**, por campo:
- `titulo`: texto de la miniatura. Se recomiendan de 2 a 6 palabras. Si falta, sale de `youtube_metadata.titulos[0]` acortado a 40 caracteres o menos.
- `subtitulo`: banner pequeño bajo el título. Vacío = sin banner.
- `sello`: `REC` | `CONFIDENCIAL` | `POLÉMICA` | `EXCLUSIVA` | `ninguno` (o texto libre corto).
- `pose`: una pose de `assets/host` (`aprobando`, `dinero`, `duda`, `esceptico`, `explicando`, `pensativo`, `senalando`, `sorprendido`).
- `layout`: `avatar_derecha` | `avatar_izquierda` | `avatar_centro` | `sin_avatar`.

Lo que no se especifica se elige de forma determinista con el slug como semilla y el tono, evitando repetir el layout y la posición de título, la paleta, la fuente, el sello y la pose de la miniatura anterior (`proyectos/_miniaturas_historial.json`). El texto nunca cubre al avatar.

```json
{
  "titulo_trabajo": "La Granja VIP: la temporada donde nadie cuida a nadie",
  "tono": "polemica",
  "usar_avatar": true,
  "miniatura": {"titulo": "CLORO EN LA COMIDA", "sello": "POLÉMICA", "layout": "avatar_izquierda", "pose": "esceptico"},
  "escenas": [ ... ]
}
```
