-- ab_largos.sql
-- Comparación A/B de 'largo_original' contra 'recopilacion' semana por semana.
-- Incluye n_videos y bandera muestra_chica (< 3 videos o < 500 vistas).

SELECT
    STRFTIME('%Y-W%W', m.fecha) AS semana,
    v.canal,
    v.formato,
    COUNT(DISTINCT v.video_id) AS n_videos,
    SUM(m.vistas) AS total_vistas,
    ROUND(AVG(m.vistas), 2) AS promedio_vistas,
    ROUND(SUM(m.minutos_vistos) / 60.0, 2) AS total_horas,
    ROUND(AVG(m.pct_visto_medio), 2) AS promedio_pct_visto,
    CASE
        WHEN COUNT(DISTINCT v.video_id) < 3 OR COALESCE(SUM(m.vistas), 0) < 500 THEN 1
        ELSE 0
    END AS muestra_chica
FROM videos v
JOIN metricas_diarias m ON v.video_id = m.video_id
WHERE v.formato IN ('largo_original', 'recopilacion')
GROUP BY semana, v.canal, v.formato
ORDER BY semana DESC, v.canal, v.formato;
