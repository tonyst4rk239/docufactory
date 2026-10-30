-- 04_mejor_hora_y_dia.sql
-- Desempeño promedio según el día de la semana y la hora de publicación
SELECT
    CASE CAST(STRFTIME('%w', p.fecha_hora_publicacion) AS INTEGER)
        WHEN 0 THEN '0_Domingo'
        WHEN 1 THEN '1_Lunes'
        WHEN 2 THEN '2_Martes'
        WHEN 3 THEN '3_Miércoles'
        WHEN 4 THEN '4_Jueves'
        WHEN 5 THEN '5_Viernes'
        WHEN 6 THEN '6_Sábado'
    END AS dia_semana,
    STRFTIME('%H:00', p.fecha_hora_publicacion) AS hora_publicacion,
    p.plataforma,
    COUNT(DISTINCT p.video_id) AS total_publicaciones,
    ROUND(AVG(a.vistas), 0) AS vistas_promedio,
    ROUND(AVG(a.retencion_promedio_pct), 2) AS retencion_media_pct,
    ROUND(AVG(a.likes), 0) AS likes_promedio,
    ROUND(AVG(a.comentarios), 0) AS comentarios_promedio
FROM publicaciones p
JOIN analiticas_diarias a ON p.video_id = a.video_id AND p.plataforma = a.plataforma
WHERE p.fecha_hora_publicacion IS NOT NULL
GROUP BY dia_semana, hora_publicacion, p.plataforma
ORDER BY vistas_promedio DESC, retencion_media_pct DESC;
