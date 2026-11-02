-- top_temas.sql
-- Temas ordenados por retención media con un mínimo de vistas (evita ruido con pocas vistas).
-- Incluye n_videos y bandera muestra_chica (< 3 videos o < 500 vistas).

SELECT
    COALESCE(v.tema, 'Sin Tema') AS tema,
    v.canal,
    COUNT(DISTINCT v.video_id) AS n_videos,
    SUM(m.vistas) AS total_vistas,
    ROUND(AVG(m.vistas), 2) AS promedio_vistas,
    ROUND(SUM(m.minutos_vistos) / 60.0, 2) AS total_horas,
    ROUND(AVG(m.pct_visto_medio), 2) AS retencion_media,
    CASE
        WHEN COUNT(DISTINCT v.video_id) < 3 OR COALESCE(SUM(m.vistas), 0) < 500 THEN 1
        ELSE 0
    END AS muestra_chica
FROM videos v
JOIN metricas_diarias m ON v.video_id = m.video_id
WHERE v.tema IS NOT NULL AND TRIM(v.tema) != ''
GROUP BY v.tema, v.canal
HAVING SUM(m.vistas) >= 50
ORDER BY retencion_media DESC, total_vistas DESC;
