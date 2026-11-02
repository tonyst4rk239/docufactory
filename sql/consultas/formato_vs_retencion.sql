-- formato_vs_retencion.sql
-- Promedio ponderado por vistas de pct_visto_medio y duración media por formato y canal en las últimas 4 semanas (date('now')).
-- Incluye n_videos y bandera muestra_chica (< 3 videos o < 500 vistas).

SELECT
    v.canal,
    v.formato,
    COUNT(DISTINCT v.video_id) AS n_videos,
    SUM(m.vistas) AS total_vistas,
    ROUND(AVG(m.vistas), 2) AS promedio_vistas,
    ROUND(SUM(m.minutos_vistos) / 60.0, 2) AS total_horas,
    ROUND(SUM(m.pct_visto_medio * m.vistas) / NULLIF(SUM(m.vistas), 0), 2) AS promedio_pct_visto,
    ROUND(SUM(m.duracion_media_s * m.vistas) / NULLIF(SUM(m.vistas), 0), 2) AS duracion_media_s,
    CASE
        WHEN COUNT(DISTINCT v.video_id) < 3 OR COALESCE(SUM(m.vistas), 0) < 500 THEN 1
        ELSE 0
    END AS muestra_chica
FROM videos v
JOIN metricas_diarias m ON v.video_id = m.video_id
WHERE m.fecha >= date('now', '-28 days')
GROUP BY v.canal, v.formato
ORDER BY v.canal, promedio_pct_visto DESC;
