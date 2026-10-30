-- 01_caida_retencion_segundo.sql
-- Cruza la curva de retención con tomas y escenas para detectar caídas de audiencia
WITH puntos AS (
    SELECT
        rc.video_id,
        rc.plataforma,
        rc.segundo_o_pct,
        rc.audiencia_relativa,
        v.duracion_s,
        v.titulo,
        CASE
            WHEN rc.segundo_o_pct <= 100.0 AND v.duracion_s > 100.0 THEN ROUND((rc.segundo_o_pct / 100.0) * v.duracion_s, 1)
            ELSE ROUND(rc.segundo_o_pct, 1)
        END AS segundo_aprox,
        LAG(rc.audiencia_relativa) OVER (PARTITION BY rc.video_id, rc.plataforma ORDER BY rc.segundo_o_pct) AS aud_anterior
    FROM retencion_curva rc
    JOIN videos v ON rc.video_id = v.id
)
SELECT
    p.video_id,
    p.titulo,
    p.plataforma,
    p.segundo_aprox AS segundo_video,
    ROUND(p.audiencia_relativa, 3) AS retencion_actual,
    ROUND(p.audiencia_relativa - p.aud_anterior, 3) AS cambio_retencion,
    t.n_escena,
    t.fuente AS fuente_broll,
    t.modo AS modo_encuadre,
    t.movimiento,
    t.aparece_host,
    e.tipo AS tipo_escena,
    SUBSTR(e.texto, 1, 60) AS texto_escena
FROM puntos p
LEFT JOIN tomas t ON p.video_id = t.video_id
    AND p.segundo_aprox >= t.inicio_s
    AND p.segundo_aprox < t.fin_s
LEFT JOIN escenas e ON p.video_id = e.video_id
    AND e.n_escena = t.n_escena
WHERE p.aud_anterior IS NOT NULL
ORDER BY (p.audiencia_relativa - p.aud_anterior) ASC
LIMIT 50;
