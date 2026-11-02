-- puntos_de_fuga.sql
-- Cruza la curva de retención con las escenas y momentos del video para saber exactamente
-- en qué segundo se va la gente, cuánta audiencia cae y qué estaba pasando en pantalla.
-- Incluye n_videos y bandera muestra_chica (< 3 videos o < 500 vistas).

WITH retencion_calculada AS (
    SELECT
        r.video_id,
        r.fecha_corte,
        r.segundo_relativo,
        r.pct_audiencia,
        ROUND(
            r.pct_audiencia - LAG(r.pct_audiencia) OVER (
                PARTITION BY r.video_id, r.fecha_corte
                ORDER BY r.segundo_relativo
            ),
            2
        ) AS caida_pct
    FROM retencion r
),
video_totales AS (
    SELECT
        video_id,
        COUNT(DISTINCT video_id) AS n_videos,
        SUM(vistas) AS total_vistas
    FROM metricas_diarias
    GROUP BY video_id
)
SELECT
    v.canal,
    v.titulo,
    rc.video_id,
    rc.segundo_relativo AS segundo_fuga,
    rc.pct_audiencia AS retencion_momento,
    rc.caida_pct,
    COALESCE(e.n_escena, 0) AS n_escena,
    COALESCE(SUBSTR(e.texto, 1, 70), 'Sin texto de escena registrado') AS narracion_en_segundo,
    COALESCE(e.broll_fuente, 'desconocido') AS broll_en_pantalla,
    COALESCE(vt.n_videos, 1) AS n_videos,
    CASE
        WHEN COALESCE(vt.n_videos, 1) < 3 OR COALESCE(vt.total_vistas, 0) < 500 THEN 1
        ELSE 0
    END AS muestra_chica
FROM retencion_calculada rc
JOIN videos v ON rc.video_id = v.video_id
LEFT JOIN video_totales vt ON v.video_id = vt.video_id
LEFT JOIN escenas e ON rc.video_id = e.video_id
    AND rc.segundo_relativo >= e.inicio_s
    AND rc.segundo_relativo < e.fin_s
WHERE rc.caida_pct IS NOT NULL
ORDER BY rc.caida_pct ASC
LIMIT 30;
