-- Esquema de Métricas YouTube para Docu Factory y Novelas Express MX
-- Ubicación: sql/schema.sql
-- Base de datos: data/metricas.db

PRAGMA foreign_keys = ON;

-- 1. Tabla de Videos
CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY,
    canal TEXT NOT NULL,
    titulo TEXT NOT NULL,
    formato TEXT CHECK(formato IN ('short', 'largo_original', 'recopilacion', 'novela_cap')),
    tema TEXT,
    serie TEXT,
    capitulo INTEGER,
    duracion_s REAL DEFAULT 0,
    fecha_publicacion TEXT,
    hora_publicacion TEXT,
    voz TEXT,
    estilo_visual TEXT
);

-- 2. Métricas Diarias por Video
CREATE TABLE IF NOT EXISTS metricas_diarias (
    video_id TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    fecha TEXT NOT NULL,
    vistas INTEGER DEFAULT 0,
    minutos_vistos REAL DEFAULT 0.0,
    duracion_media_s REAL DEFAULT 0.0,
    pct_visto_medio REAL DEFAULT 0.0,
    likes INTEGER DEFAULT 0,
    comentarios INTEGER DEFAULT 0,
    suscriptores_ganados INTEGER DEFAULT 0,
    PRIMARY KEY(video_id, fecha)
);

-- 3. Curva de Retención de Audiencia
CREATE TABLE IF NOT EXISTS retencion (
    video_id TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    fecha_corte TEXT NOT NULL,
    segundo_relativo REAL NOT NULL,
    pct_audiencia REAL NOT NULL,
    PRIMARY KEY(video_id, fecha_corte, segundo_relativo)
);

-- 4. Fuentes de Tráfico
CREATE TABLE IF NOT EXISTS trafico (
    video_id TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    fecha TEXT NOT NULL,
    fuente TEXT NOT NULL,
    vistas INTEGER DEFAULT 0,
    PRIMARY KEY(video_id, fecha, fuente)
);

-- 5. Escenas y Cronología del Video (para cruzar con la curva de retención)
CREATE TABLE IF NOT EXISTS escenas (
    video_id TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    n_escena INTEGER NOT NULL,
    inicio_s REAL NOT NULL,
    fin_s REAL NOT NULL,
    texto TEXT,
    broll_fuente TEXT,
    PRIMARY KEY(video_id, n_escena)
);

-- Índices de aceleración para consultas analíticas
CREATE INDEX IF NOT EXISTS idx_videos_canal ON videos(canal);
CREATE INDEX IF NOT EXISTS idx_videos_formato ON videos(formato);
CREATE INDEX IF NOT EXISTS idx_videos_serie_cap ON videos(serie, capitulo);
CREATE INDEX IF NOT EXISTS idx_metricas_fecha ON metricas_diarias(fecha);
CREATE INDEX IF NOT EXISTS idx_retencion_video ON retencion(video_id, fecha_corte);
CREATE INDEX IF NOT EXISTS idx_trafico_video ON trafico(video_id, fecha);
CREATE INDEX IF NOT EXISTS idx_escenas_video_tiempo ON escenas(video_id, inicio_s, fin_s);
