-- 05_trafico_reels_a_largo.sql
-- Cruce de videos largos con reels del mismo tema y fuentes de tráfico
SELECT
    vl.id AS video_largo_id,
    vl.slug AS slug_largo,
    vl.titulo AS titulo_largo,
    vr.id AS reel_id,
    vr.slug AS slug_reel,
    COALESCE(al.vistas, 0) AS vistas_largo,
    COALESCE(ar.vistas, 0) AS vistas_reel,
    al.fuentes_trafico AS fuentes_trafico_largo
FROM videos vl
JOIN videos vr ON (vl.tema = vr.tema OR vl.slug LIKE '%' || vr.slug || '%' OR vr.slug LIKE '%' || vl.slug || '%')
    AND vl.formato = 'largo'
    AND vr.formato IN ('reel', 'short', '9:16')
LEFT JOIN analiticas_diarias al ON vl.id = al.video_id
LEFT JOIN analiticas_diarias ar ON vr.id = ar.video_id
ORDER BY vistas_largo DESC;
