-- 06_costo_por_vista_y_sub.sql
-- Eficiencia económica por video: costo de voz + IA vs vistas y suscriptores ganados
SELECT
    v.id AS video_id,
    v.formato,
    v.titulo,
    ROUND(COALESCE(v.costo_voz_usd, 0.0) + COALESCE(v.costo_ia_usd, 0.0), 4) AS costo_total_usd,
    COALESCE(v.costo_voz_usd, 0.0) AS costo_voz_usd,
    COALESCE(v.costo_ia_usd, 0.0) AS costo_ia_usd,
    COALESCE(SUM(a.vistas), 0) AS vistas_totales,
    COALESCE(SUM(a.suscriptores_ganados), 0) AS subs_totales,
    CASE
        WHEN COALESCE(SUM(a.vistas), 0) > 0 THEN
            ROUND((COALESCE(v.costo_voz_usd, 0.0) + COALESCE(v.costo_ia_usd, 0.0)) / SUM(a.vistas), 6)
        ELSE NULL
    END AS costo_por_vista_usd,
    CASE
        WHEN COALESCE(SUM(a.suscriptores_ganados), 0) > 0 THEN
            ROUND((COALESCE(v.costo_voz_usd, 0.0) + COALESCE(v.costo_ia_usd, 0.0)) / SUM(a.suscriptores_ganados), 4)
        ELSE NULL
    END AS costo_por_sub_usd
FROM videos v
LEFT JOIN analiticas_diarias a ON v.id = a.video_id
GROUP BY v.id
ORDER BY vistas_totales DESC, costo_total_usd ASC;
