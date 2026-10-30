-- 03_ctr_miniatura_y_titulo.sql
-- Relación de elementos de la miniatura y título con CTR y vistas
SELECT
    v.id AS video_id,
    v.titulo,
    tf.largo AS caracteres_titulo,
    tf.tiene_numero,
    tf.tiene_signos,
    m.n_palabras AS palabras_miniatura,
    m.tiene_cara,
    m.emocion_cara,
    m.tiene_rec,
    m.colores_dominantes,
    COALESCE(a.ctr_miniatura, 0.0) AS ctr_pct,
    COALESCE(a.vistas, 0) AS vistas,
    COALESCE(a.likes, 0) AS likes
FROM videos v
LEFT JOIN titulo_features tf ON v.id = tf.video_id
LEFT JOIN miniatura m ON v.id = m.video_id
LEFT JOIN analiticas_diarias a ON v.id = a.video_id
ORDER BY ctr_pct DESC, vistas DESC;
