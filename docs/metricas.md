# Capa de Métricas y Analíticas SQL: Código OcultoTV y Novelas Express MX

Este módulo implementa una capa de datos analítica en SQLite para tomar decisiones editoriales y de producción basadas en métricas reales de YouTube Data API v3 y YouTube Analytics API v2.

Permite comparar formatos, series, capítulos, temáticas y horarios de estreno entre **Código OcultoTV** (Docu Factory) y **Novelas Express MX**, distinguiendo con rigor estadístico entre conclusiones respaldadas y señales preliminares.

---

## 1. Estructura y Esquema de Datos (`sql/schema.sql`)

La base de datos reside en `data/metricas.db` (en `.gitignore`) y se inicializa automáticamente a partir de `sql/schema.sql`:

- **`videos`**: Catálogo maestro de videos.
  - `video_id` (PK): Identificador alfanumérico de YouTube.
  - `canal`: Nombre del canal (`Código OcultoTV`, `Novelas Express MX`).
  - `titulo`: Título publicado en YouTube.
  - `formato`: Uno de `'short'`, `'largo_original'`, `'recopilacion'`, `'novela_cap'`.
  - `tema`: Categoría tematica (`leyenda`, `paranormal`, `religión`, `crimen`, `reality`, `historia`, `novela`).
  - `serie`: Nombre de la serie o drama (en formato `novela_cap`).
  - `capitulo`: Número entero del capítulo/episodio.
  - `duracion_s`: Duración en segundos.
  - `fecha_publicacion` / `hora_publicacion`: Timestamp convertido a hora local de **Mérida** (`America/Merida`).
  - `voz` / `estilo_visual`: Metadatos de producción audiovisual.
- **`metricas_diarias`**: Rendimiento real diario por video (sin datos inventados).
  - `(video_id, fecha)` (PK compuesto).
  - `vistas`, `minutos_vistos`, `duracion_media_s`, `pct_visto_medio`, `likes`, `comentarios`, `suscriptores_ganados`.
- **`retencion`**: Curva de retención segundo a segundo.
  - `(video_id, fecha_corte, segundo_relativo)` (PK compuesto).
  - `pct_audiencia`: Porcentaje relativo de audiencia retenida.
- **`trafico`**: Fuentes de tráfico diarias (búsqueda, sugeridos, feed de shorts, etc.).
  - `(video_id, fecha, fuente)` (PK compuesto).
  - `vistas`.
- **`escenas`**: Línea de tiempo de escenas y guion de proyectos locales (`video_id, n_escena, inicio_s, fin_s, texto, broll_fuente`) para cruzar segundo a segundo con la curva de retención.

---

## 2. Multi-Canal y Verificación de Identidad

El sistema soporta múltiples canales con tokens OAuth independientes:

| Canal | Archivo de Token OAuth | Verificación Estricta |
|---|---|---|
| **Código OcultoTV** | `assets/credentials/token_youtube.json` | Token por defecto del canal principal |
| **Novelas Express MX** | `assets/credentials/token_youtube_novelas.json` | **Channel ID obligatorio:** `UC8O5Zv0nsHRfaXij9uJNYbg` |

Si se intenta cosechar o autorizar Novelas con una cuenta de Google cuyo Channel ID no coincida con `UC8O5Zv0nsHRfaXij9uJNYbg`, el proceso **aborta inmediatamente con un error claro**.

### Autorización OAuth de Canales (`src/metricas/autorizar_canal.py`)
Para generar o renovar el token de cualquiera de los canales con los permisos de lectura y analíticas (`youtube.readonly` y `yt-analytics.readonly`):

```bash
# Autorizar canal Novelas Express MX (valida Channel ID y guarda en token_youtube_novelas.json)
python src/metricas/autorizar_canal.py --canal novelas

# Autorizar canal Código OcultoTV (guarda en token_youtube.json)
python src/metricas/autorizar_canal.py --canal codigo

# Opcional: especificar ruta personalizada de token o client_secrets
python src/metricas/autorizar_canal.py --canal novelas --token assets/credentials/token_youtube_novelas.json
```

---

## 3. Reglas Estrictas de Formato y Categorización de Temas

### Formatos Audiovisuales
1. **`recopilacion`**: **ÚNICAMENTE** si está indicado en `data/etiquetas_videos.csv` o si el título incluye explícitamente la etiqueta `[Recopilación]` (o `[Recopilacion]`). **Nunca por "Top N"**.
2. **`novela_cap`**: En el canal **Novelas Express MX**, se clasifica **ANTES** de la regla de Short ($\le 180$ s). Extrae la serie y el capítulo del título (`Ep N` / `Cap N`).
3. **`short`**: Si la duración es $\le 180$ s o si el video es vertical (aspect ratio 9:16 o `#shorts` en el título) en canales que no son Novelas.
4. **`largo_original`**: Todo video de formato horizontal mayor a 180 s que no sea una recopilación etiquetada.

### Temas y Categorización
El tema se obtiene de la columna `tema` en `data/etiquetas_videos.csv`. Si viene vacía o no existe registro en el CSV, se clasifica mediante un diccionario de palabras clave en una de las siguientes categorías (nunca se usa el título bruto como tema):
- `muerte_mx` (`mictlan`, `muertos`, `ofrenda`, `cementerio`, `catrina`, `xolo`, `ánimas`).
- `religión` (incluye `\bpapas?\b`, `biblia`, `vaticano`, `iglesia`).
- `leyenda`, `paranormal`, `crimen`, `reality`, `historia`, `novela`.

### Zona Horaria de Publicación (`America/Merida`)
Los timestamps de estreno en UTC (`publishedAt`) se convierten a la zona horaria `America/Merida` (UTC-6) antes de registrar `fecha_publicacion` y `hora_publicacion`. De este modo, los reportes por día de la semana y hora reflejan el momento local real de la audiencia.

### Escritura Atómica de Tokens
Al refrescar o guardar tokens OAuth, se escribe a un archivo temporal y luego se renombra atómicamente, sin tocar nunca `token_youtube.bak.json`.

---

## 4. Recolección de Datos (`src/metricas/recolectar.py`)

Extrae métricas reales vía API y ejecuta **upserts idempotentes**.

> **Política de Integridad:** Se eliminó cualquier respaldo con datos inventados (como asumir 40% visto o 0.4x de duración). Si YouTube Analytics falla para un video, **no se guarda la fila en `metricas_diarias`**, se registra el error en un resumen final y el script finaliza con código de error distinto de cero (`sys.exit(1)`).

### Uso básico:
```bash
# Recolectar últimos 3 días de Código OcultoTV
python src/metricas/recolectar.py

# Recolectar canal Novelas Express MX
python src/metricas/recolectar.py --canal "Novelas Express MX"

# Definir fecha de inicio personalizada
python src/metricas/recolectar.py --canal "Novelas Express MX" --desde 2026-10-01

# Usar token personalizado
python src/metricas/recolectar.py --canal "Novelas Express MX" --token assets/credentials/token_youtube_novelas.json
```

---

## 5. Consultas SQL Analíticas Ponderadas (`sql/consultas/`)

Todas las consultas en `sql/consultas/` **ponderan la retención y la duración por vistas**:
$$\text{retencion\_media} = \frac{\sum (\text{pct\_visto\_medio} \times \text{vistas})}{\text{NULLIF}(\sum \text{vistas}, 0)}$$
$$\text{duracion\_media\_s} = \frac{\sum (\text{duracion\_media\_s} \times \text{vistas})}{\text{NULLIF}(\sum \text{vistas}, 0)}$$

Además, utilizan la fecha actual `date('now')` como referencia temporal, la función `FECHA_LOCAL('%G-%V', m.fecha)` para semanas ISO (sin sobrescribir `strftime` nativo de SQLite) y filtros de calidad:

- **`formato_vs_retencion.sql`**: Rendimiento ponderado por formato y canal en las últimas 4 semanas (`date('now', '-28 days')`).
- **`top_temas.sql`**: Categorías temáticas ordenadas por retención ponderada con filtro de volumen mínimo ($\ge 50$ vistas).
- **`ab_largos.sql`**: Comparativa A/B semana a semana ISO (`FECHA_LOCAL('%G-%V', m.fecha)`) entre `largo_original` y `recopilacion`.
- **`novelas_por_capitulo.sql`**: Retención ponderada por serie y capítulo, calculando la caída contra el capítulo previo mediante `LAG() OVER (PARTITION BY serie, canal ORDER BY capitulo)`.
- **`horario.sql`**: Rendimiento ponderado agrupado por día de la semana y hora de estreno en Mérida.
- **`puntos_de_fuga.sql`**: Cruce segundo a segundo entre la curva de retención y la línea de tiempo de escenas (`escenas`), detectando en qué segundo cayó la audiencia y qué escena o B-roll estaba en pantalla.
  - Filtra videos con `total_vistas >= 200`.
  - Ignora el segundo 0 y puntos anómalos $> 100\%$.
  - Empata video y proyecto exclusivamente por el `video_id` guardado al subir (`publicacion*.json` o similar), nunca por título parecido, y nunca un Short con un proyecto largo.

Todas las consultas calculan la bandera `muestra_chica` ($1$ si $n\_videos < 3$ o $total\_vistas < 500$, $0$ si es muestra confiable).

---

## 6. Generación de Reportes Ejecutivos (`src/metricas/reporte.py`)

Ejecuta todas las consultas analíticas y redacta un reporte Markdown en `reportes/metricas_AAAA-MM-DD.md` dividiendo los resultados en:
1. **Conclusiones con Confianza** (`muestra_chica = 0`)
2. **Señales Débiles** (`muestra_chica = 1`)

```bash
python src/metricas/reporte.py
```

---

## 7. Cómo Agregar una Consulta Nueva

1. Crea `sql/consultas/<nombre_de_consulta>.sql`.
2. Incluye siempre la ponderación por vistas (`SUM(pct_visto_medio*vistas)/NULLIF(SUM(vistas),0)`), la columna `n_videos` y la bandera `muestra_chica`.
3. Registra el nombre en `orden_consultas` y `titulos_bloques` en `src/metricas/reporte.py`.

---

## 8. Pruebas Unitarias

El suite valida todas las reglas sin llamar a APIs externas:
```bash
python -m unittest tests/test_metricas.py
```
Prueba:
- Validación y rechazo de Channel ID incorrecto para Novelas Express MX.
- Omisión estricta de filas cuando Analytics falla (sin datos inventados).
- Ponderación matemática por vistas frente a promedio simple.
- Conversión horaria a `America/Merida` (zoneinfo).
- Categorización de temas por palabras clave (sin usar títulos brutos).
- Reglas estrictas de formato (Shorts $\le 180$ s/vertical, `[Recopilación]`, `novela_cap` exclusivo de Novelas).
- Semanas ISO (`%G-%V`) y cruce de retención vs escenas (`puntos_de_fuga.sql`).
