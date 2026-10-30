-- 02_retencion_por_fuente_voz_gancho.sql
-- Comparativa de retención promedio por fuente de B-roll, voz, encuadre y tipo de gancho
SELECT
    'fuente_broll' AS dimension,
    COALESCE(t.fuente, 'sin_tomas') AS valor,
    COUNT(DISTINCT v.id) AS total_videos,
    COUNT(t.id) AS total_tomas,
    ROUND(AVG(a.retencion_promedio_pct), 2) AS retencion_media_pct,
    ROUND(AVG(a.vistas), 0) AS vistas_promedio
FROM tomas t
JOIN videos v ON t.video_id = v.id
LEFT JOIN analiticas_diarias a ON v.id = a.video_id
GROUP BY t.fuente

UNION ALL

SELECT
    'modo_encuadre' AS dimension,
    COALESCE(t.modo, 'desconocido') AS valor,
    COUNT(DISTINCT v.id) AS total_videos,
    COUNT(t.id) AS total_tomas,
    ROUND(AVG(a.retencion_promedio_pct), 2) AS retencion_media_pct,
    ROUND(AVG(a.vistas), 0) AS vistas_promedio
FROM tomas t
JOIN videos v ON t.video_id = v.id
LEFT JOIN analiticas_diarias a ON v.id = a.video_id
GROUP BY t.modo

UNION ALL

SELECT
    'voz' AS dimension,
    COALESCE(v.voz, 'desconocida') AS valor,
    COUNT(DISTINCT v.id) AS total_videos,
    0 AS total_tomas,
    ROUND(AVG(a.retencion_promedio_pct), 2) AS retencion_media_pct,
    ROUND(AVG(a.vistas), 0) AS vistas_promedio
FROM videos v
LEFT JOIN analiticas_diarias a ON v.id = a.video_id
GROUP BY v.voz

UNION ALL

SELECT
    'tipo_gancho' AS dimension,
    COALESCE(g.tipo_gancho, 'no_definido') AS valor,
    COUNT(DISTINCT v.id) AS total_videos,
    0 AS total_tomas,
    ROUND(AVG(a.retencion_promedio_pct), 2) AS retencion_media_pct,
    ROUND(AVG(a.vistas), 0) AS vistas_promedio
FROM guion g
JOIN videos v ON g.video_id = v.id
LEFT JOIN analiticas_diarias a ON v.id = a.video_id
GROUP BY g.tipo_gancho

ORDER BY dimension, retencion_media_pct DESC;
