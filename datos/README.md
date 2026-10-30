# Módulo de Datos y Analíticas de Docu Factory

Este módulo registra cada aspecto de la producción de video (guion, ritmo, tomas, audio, miniaturas, títulos y curaduría de clips) en una base de datos relacional SQLite (`datos/docufactory.db`) y lo cruza con las analíticas reales de desempeño (YouTube Analytics, YouTube Data API v3, Facebook y TikTok) segundo a segundo.

---

## 1. Esquema Relacional (`datos/schema.sql`)

La base de datos se estructura en 13 tablas interconectadas con claves foráneas e integridad referencial (`ON DELETE CASCADE`):

| Tabla | Propósito |
|---|---|
| `videos` | Ficha técnica principal del proyecto (slug, formato, duración, voz, costos). |
| `guion` | Métricas del texto narrado: legibilidad, ritmo, estructura dramática y tipo de gancho. |
| `escenas` | Desglose por bloque narrativo (gancho, desarrollo, clímax, cierre, palabras/minuto). |
| `tomas` | Tiempos reales de cada corte de video en el render final, autor, licencia, encuadre y brillo. |
| `ritmo` | Densidad de montaje: cortes por minuto, duración media de tomas y subtitulado. |
| `audio` | Nivel de sonoridad LUFS real, pista musical, catálogo de efectos SFX y pausas. |
| `miniatura` | Análisis visual: palabras en texto de miniatura, detección facial, emoción y colores. |
| `titulo_features`| Características del titular: longitud, números (e.g. Top N), emojis y signos. |
| `produccion` | Control de calidad del agente Lente: tomas rechazadas, motivos y Content ID. |
| `publicaciones` | Enlaces públicos y plataforma de difusión (YouTube, Reels, TikTok). |
| `analiticas_diarias` | Rendimiento diario: vistas, retención %, pase de 3 segundos, likes, comentarios, CTR y fuentes. |
| `retencion_curva` | Curva segundo a segundo o percentil a percentil de retención de audiencia. |
| `comentarios` | Cosecha de comentarios, análisis de sentimiento (+/-/=) y peticiones de "Segunda Parte". |

---

## 2. Comandos CLI

### A. Registro y Reconstrucción de Proyectos (`datos/registrar.py`)

- **Reconstrucción histórica:** Inspecciona toda la carpeta `proyectos/` y extrae automáticamente las fichas técnicas, tomas, guiones, miniaturas y audio medido.
  ```bash
  python datos/registrar.py reconstruir
  ```

- **Registro manual o puntual:** Registra un proyecto específico por su slug:
  ```bash
  python datos/registrar.py registrar <slug_o_directorio>
  ```

### B. Descarga y Sincronización de Analíticas (`datos/analiticas.py actualizar`)

- **Sincronización multi-plataforma:** Conecta con las APIs de YouTube (utilizando `assets/credentials/token_youtube.json` sin alterar claves ni exponer tokens) para actualizar métricas diarias, curva de retención y comentarios clasificados:
  ```bash
  python datos/analiticas.py actualizar
  ```
  Opciones:
  - `--dias 30`: Rango de días a procesar (por defecto: 30).
  - `--plataforma {todas,youtube,facebook,tiktok}`: Filtrar por plataforma.
  - `--video <slug>`: Actualizar un video individual.

### C. Generación de Reportes y Exportación CSV (`datos/analiticas.py reporte`)

- **Generar informe consolidado:** Ejecuta todas las consultas analíticas de `datos/consultas/`, muestra tablas resumen en terminal y genera un reporte en `reportes/analiticas_YYYYMMDD.csv`:
  ```bash
  python datos/analiticas.py reporte
  ```

---

## 3. Consultas Analíticas Predefinidas (`datos/consultas/`)

1. **`01_caida_retencion_segundo.sql`:**
   Cruza la curva de retención con los tiempos exactos de las tomas y escenas para descubrir en qué toma, b-roll o frase se pierde audiencia.

2. **`02_retencion_por_fuente_voz_gancho.sql`:**
   Compara la retención media agrupando por tipo de gancho de guion, fuente de clips (Pexels, Pixabay, YouTube Commons), tipo de encuadre (fit vs. fill) y voz sintética.

3. **`03_ctr_miniatura_y_titulo.sql`:**
   Cruza el Click-Through Rate (CTR) y vistas con los atributos del título (longitud, uso de cifras) y de la miniatura (emoción facial, colores dominantes, cantidad de palabras).

4. **`04_mejor_hora_y_dia.sql`:**
   Analiza el impacto del momento de publicación desglosando métricas por día de la semana y franja horaria.

5. **`05_trafico_reels_a_largo.sql`:**
   Evalúa el efecto embudo: verifica si los Reels/Shorts del mismo tema derivaron tráfico hacia el documental de formato largo.

6. **`06_costo_por_vista_y_sub.sql`:**
   Calcula la eficiencia económica del canal dividiendo el costo total invertido en voz e IA entre las vistas obtenidas y suscriptores ganados.

---

## 4. Integración Automática en el Pipeline

El registro se ejecuta automáticamente de forma no bloqueante (si falla la base de datos o falta alguna métrica secundaria, se registra aviso en log sin abortar la producción ni la subida):

- **`make_video.py` / `make_tiktok.py`**:
  - Al completar el render (`cmd_renderizar`, `cmd_continuar`, `cmd_doblar`), invoca `registrar_proyecto_completo()`.
  - En la fase de curaduría de clips (`cmd_revisar`), guarda el conteo y motivos de tomas descartadas por el agente Lente en la tabla `produccion`.
- **`subir_video.py`**:
  - Al publicar con éxito en YouTube, Facebook Page, Facebook Perfil o TikTok, registra automáticamente el registro en la tabla `publicaciones`.
