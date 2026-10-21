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
