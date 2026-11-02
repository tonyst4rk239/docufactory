-- horario.sql
-- Rendimiento de retención y vistas según día de la semana y hora de publicación.
-- Incluye n_videos y bandera muestra_chica (< 3 videos o < 500 vistas).

SELECT
    CASE CAST(STRFTIME('%w', v.fecha_publicacion) AS INTEGER)
        WHEN 0 THEN '0_Domingo'
        WHEN 1 THEN '1_Lunes'
        WHEN 2 THEN '2_Martes'
        WHEN 3 THEN '3_Miércoles'
        WHEN 4 THEN '4_Jueves'
        WHEN 5 THEN '5_Viernes'
        WHEN 6 THEN '6_Sábado'
        ELSE 'Desconocido'
    END AS dia_semana,
    CASE
        WHEN v.hora_publicacion IS NOT NULL AND LENGTH(v.hora_publicacion) >= 2 THEN
            SUBSTR(v.hora_publicacion, 1, 2) || ':00'
        ELSE 'Sin hora'
    END AS hora_publicacion,
    v.canal,
    COUNT(DISTINCT v.video_id) AS n_videos,
    SUM(m.vistas) AS total_vistas,
    ROUND(AVG(m.vistas), 2) AS promedio_vistas,
    ROUND(AVG(m.pct_visto_medio), 2) AS retencion_media,
    CASE
        WHEN COUNT(DISTINCT v.video_id) < 3 OR COALESCE(SUM(m.vistas), 0) < 500 THEN 1
        ELSE 0
    END AS muestra_chica
FROM videos v
JOIN metricas_diarias m ON v.video_id = m.video_id
WHERE v.fecha_publicacion IS NOT NULL
GROUP BY dia_semana, hora_publicacion, v.canal
ORDER BY dia_semana, hora_publicacion, v.canal;
