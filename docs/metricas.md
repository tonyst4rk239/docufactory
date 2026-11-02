# Capa de Métricas y Analíticas SQL: Código OcultoTV y Novelas Express MX

Este módulo implementa una capa de datos analítica en SQLite para tomar decisiones editoriales y de producción basadas en métricas reales de YouTube Data API v3 y YouTube Analytics API v2.

Permite comparar formatos, series, capítulos, temáticas y horarios de publicación entre **Código OcultoTV** (Docu Factory) y **Novelas Express MX**, distinguiendo con rigor estadístico entre conclusiones respaldadas y señales preliminares.

---

## 1. Estructura y Esquema de Datos (`sql/schema.sql`)

La base de datos reside en `data/metricas.db` (en `.gitignore`) y se inicializa automáticamente a partir de `sql/schema.sql`:

- **`videos`**: Catálogo maestro de videos.
  - `video_id` (PK): Identificador alfanumérico de YouTube.
  - `canal`: Nombre del canal (`Código OcultoTV`, `Novelas Express MX`, etc.).
  - `titulo`: Título original publicado.
  - `formato`: Uno de `'short'`, `'largo_original'`, `'recopilacion'`, `'novela_cap'`.
  - `tema`: Temática o asunto central.
  - `serie`: Nombre de la serie o novela (en formato `novela_cap`).
  - `capitulo`: Número entero del capítulo/episodio.
  - `duracion_s`: Duración en segundos.
  - `fecha_publicacion` / `hora_publicacion`: Marca temporal de estreno en YouTube.
  - `voz` / `estilo_visual`: Metadatos de producción audiovisual.
- **`metricas_diarias`**: Rendimiento día a día por video.
  - `(video_id, fecha)` (PK compuesto).
  - `vistas`, `minutos_vistos`, `duracion_media_s`, `pct_visto_medio`, `likes`, `comentarios`, `suscriptores_ganados`.
- **`retencion`**: Curva de retención segundo a segundo.
  - `(video_id, fecha_corte, segundo_relativo)` (PK compuesto).
  - `pct_audiencia`: Porcentaje relativo de audiencia retenida.
- **`trafico`**: Fuentes de tráfico diarias (búsqueda, sugeridos, feed de shorts, etc.).
  - `(video_id, fecha, fuente)` (PK compuesto).
  - `vistas`.

---

## 2. Inferencia de Formato y Etiquetas Manuales

El script infiere automáticamente los formatos y metadatos:
1. **`short`**: Si la duración es $\le 60$ s o contiene `#shorts` / `#short`.
2. **`novela_cap`**: Si el canal contiene "novela"/"kdrama" o el título incluye expresiones como `Capítulo N`, `Cap. N` o `Episodio N`. Extrae automáticamente el número de capítulo y el nombre de la serie.
3. **`recopilacion`**: Si el título contiene términos como `Maratón`, `Compilación`, `Recopilación`, `Top N` o `Episodios Completos`.
4. **`largo_original`**: Videos largos que no corresponden a compilaciones ni novelas episódicas.

### Corrección Manual con CSV (`data/etiquetas_videos.csv`)

Cualquier valor inferido puede corregirse sin tocar código agregando una fila en `data/etiquetas_videos.csv`:
```csv
video_id,formato,tema,serie,capitulo,voz,estilo_visual
dQw4w9WgXcQ,recopilacion,Misterios Antiguos,,,Alonso,cinematica
abc123xyz78,novela_cap,Amor en Seúl,Amor en Seúl,5,Jenny,anime
```
Si una celda está en blanco, se conserva el valor inferido por defecto.

---

## 3. Recolección de Datos (`src/metricas/recolectar.py`)

Extrae métricas vía API y ejecuta **upserts idempotentes** (puedes correrlo múltiples veces sin generar duplicados).

### Uso básico:
```bash
# Recolectar últimos 3 días (por defecto)
python src/metricas/recolectar.py

# Filtrar por canal específico
python src/metricas/recolectar.py --canal "Código OcultoTV"
python src/metricas/recolectar.py --canal "Novelas Express MX"

# Definir fecha de inicio personalizada
python src/metricas/recolectar.py --desde 2026-10-01

# Especificar rutas alternativas
python src/metricas/recolectar.py --db data/metricas.db --csv-etiquetas data/etiquetas_videos.csv
```

---

## 4. Generación de Reportes Ejecutivos (`src/metricas/reporte.py`)

Ejecuta todas las consultas analíticas de `sql/consultas/` y redacta un reporte consolidado en `reportes/metricas_AAAA-MM-DD.md`.

```bash
python src/metricas/reporte.py
```

### Criterio Estadístico: "Muestra Chica"
Para evitar tomar decisiones apresuradas basadas en 5 o 10 vistas, todas las consultas calculan la bandera `muestra_chica`:
$$\text{muestra\_chica} = 1 \iff (n\_videos < 3 \lor total\_vistas < 500)$$

El generador de reportes divide el análisis en dos bloques explícitos:
1. **Conclusiones con Confianza**: Patrones validados con al menos 3 videos y más de 500 vistas (`muestra_chica = 0`).
2. **Señales Débiles**: Tendencias exploratorias con baja muestra (`muestra_chica = 1`), que sirven como hipótesis pero no como prueba definitiva.

---

## 5. Consultas SQL Disponibles (`sql/consultas/`)

- **`formato_vs_retencion.sql`**: Promedio de retención (`pct_visto_medio`), vistas y horas acumuladas por formato y canal en las últimas 4 semanas.
- **`top_temas.sql`**: Temáticas ordenadas por retención media con filtro de volumen mínimo ($\ge 50$ vistas).
- **`ab_largos.sql`**: Comparativa A/B semana por semana entre `largo_original` y `recopilacion`.
- **`novelas_por_capitulo.sql`**: Retención por serie y capítulo, calculando la caída de retención y vistas contra el capítulo inmediato anterior mediante funciones de ventana (`LAG() OVER`).
- **`horario.sql`**: Rendimiento agrupado por día de la semana y hora de estreno.

---

## 6. Cómo Agregar una Consulta Nueva

Para añadir una nueva dimensión o análisis al pipeline:

### Paso 1: Crear el archivo SQL en `sql/consultas/`
Crea `sql/consultas/<nombre_de_consulta>.sql`.

> **Requisito indispensable:** La consulta DEBE incluir las columnas `n_videos` y `muestra_chica`:
> ```sql
> SELECT
>     v.estilo_visual,
>     COUNT(DISTINCT v.video_id) AS n_videos,
>     SUM(m.vistas) AS total_vistas,
>     ROUND(AVG(m.pct_visto_medio), 2) AS retencion_media,
>     CASE
>         WHEN COUNT(DISTINCT v.video_id) < 3 OR COALESCE(SUM(m.vistas), 0) < 500 THEN 1
>         ELSE 0
>     END AS muestra_chica
> FROM videos v
> JOIN metricas_diarias m ON v.video_id = m.video_id
> WHERE v.estilo_visual IS NOT NULL
> GROUP BY v.estilo_visual
> ORDER BY retencion_media DESC;
> ```

### Paso 2: Registrar en `src/metricas/reporte.py`
En `src/metricas/reporte.py`, agrega el nombre de tu consulta a la lista `orden_consultas` y asigna un título descriptivo en `titulos_bloques`:
```python
orden_consultas = [
    "formato_vs_retencion",
    "top_temas",
    "ab_largos",
    "novelas_por_capitulo",
    "horario",
    "estilo_visual",  # <--- Tu nueva consulta
]

titulos_bloques = {
    ...
    "estilo_visual": "6. Rendimiento por Estilo Visual",
}
```

Opcionalmente, puedes añadir una regla de síntesis en la función `sintetizar_analisis()` para que genere viñetas automáticas en "Conclusiones con Confianza" o "Señales Débiles".

---

## 7. Pruebas Unitarias

El suite de pruebas valida la lógica sin requerir conexión a internet ni credenciales reales:
```bash
python -m unittest tests/test_metricas.py
```
Prueba:
- Inferencia de formatos (`short`, `largo_original`, `recopilacion`, `novela_cap`).
- Idempotencia de `upsert_video`, `upsert_metrica_diaria`, `upsert_retencion`, `upsert_trafico`.
- Cálculo de `muestra_chica` y diferencias `LAG()` en base temporal en memoria.
- Generación de reportes Markdown con tablas y secciones divididas.
