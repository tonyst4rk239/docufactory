-- novelas_por_capitulo.sql
-- Retención ponderada por vistas por serie y capítulo, y la caída entre capítulos consecutivos.
-- Incluye n_videos y bandera muestra_chica (< 3 videos o < 500 vistas).

WITH capitulos_agg AS (
    SELECT
        COALESCE(v.serie, 'Serie Desconocida') AS serie,
        v.capitulo,
        v.canal,
        COUNT(DISTINCT v.video_id) AS n_videos,
        SUM(m.vistas) AS total_vistas,
        ROUND(AVG(m.vistas), 2) AS promedio_vistas,
        ROUND(SUM(m.pct_visto_medio * m.vistas) / NULLIF(SUM(m.vistas), 0), 2) AS retencion_media,
        ROUND(SUM(m.duracion_media_s * m.vistas) / NULLIF(SUM(m.vistas), 0), 2) AS duracion_media_s,
        CASE
            WHEN COUNT(DISTINCT v.video_id) < 3 OR COALESCE(SUM(m.vistas), 0) < 500 THEN 1
            ELSE 0
        END AS muestra_chica
    FROM videos v
    JOIN metricas_diarias m ON v.video_id = m.video_id
    WHERE (v.formato = 'novela_cap' OR v.serie IS NOT NULL) AND v.capitulo IS NOT NULL
    GROUP BY serie, v.capitulo, v.canal
)
SELECT
    serie,
    capitulo,
    canal,
    n_videos,
    total_vistas,
    promedio_vistas,
    retencion_media,
    duracion_media_s,
    ROUND(
        retencion_media - LAG(retencion_media) OVER (PARTITION BY serie, canal ORDER BY capitulo),
        2
    ) AS caida_retencion_vs_anterior,
    ROUND(
        total_vistas - LAG(total_vistas) OVER (PARTITION BY serie, canal ORDER BY capitulo),
        0
    ) AS caida_vistas_vs_anterior,
    muestra_chica
FROM capitulos_agg
ORDER BY serie, canal, capitulo;
