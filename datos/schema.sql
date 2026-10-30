-- ============================================================================
-- Docu Factory — Esquema SQLite de Analíticas y Producción Segundo a Segundo
-- Base de datos: datos/docufactory.db (ignorada en git; esquema versionado)
-- ============================================================================

PRAGMA foreign_keys = ON;

-- 1. VIDEOS: Metadatos generales, costos y tiempos de producción
CREATE TABLE IF NOT EXISTS videos (
    id TEXT PRIMARY KEY,                       -- Slug único del video o id generado
    slug TEXT UNIQUE NOT NULL,                 -- Slug del proyecto
    formato TEXT NOT NULL,                     -- largo (16:9), reel (9:16), short
    tema TEXT NOT NULL,                        -- Tema o premisa del video
    tono TEXT DEFAULT 'misterio',              -- Tono: misterio, terror, epico, etc.
    duracion_s REAL DEFAULT 0.0,               -- Duración total en segundos
    voz TEXT DEFAULT 'es-US-AlonsoNeural',     -- Voz principal empleada
    voz_fallback INTEGER DEFAULT 0,            -- 1 si conmutó a voz de respaldo (Edge-TTS)
    fecha_render TEXT,                         -- Timestamp ISO del render final
    titulo TEXT,                               -- Título principal publicado
    descripcion TEXT,                          -- Descripción para redes/YouTube
    hashtags TEXT,                             -- Hashtags usados
    texto_miniatura TEXT,                      -- Texto de impacto en la miniatura
    fuente_tema TEXT DEFAULT 'otro',           -- brujula, radar, manual, otro
    tendencia_origen TEXT,                     -- Búsqueda o tendencia que inspiró el video
    fecha_especial TEXT,                       -- Si aplica a fecha histórica o efeméride
    costo_voz_usd REAL DEFAULT 0.0,            -- Estimación costo API TTS
    costo_ia_usd REAL DEFAULT 0.0,             -- Estimación costo tokens Gemini
    tiempo_render_s REAL DEFAULT 0.0,          -- Tiempo transcurrido en el render FFmpeg
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- 2. GUION: Métricas textuales, ganchos y retención de la narrativa
CREATE TABLE IF NOT EXISTS guion (
    video_id TEXT PRIMARY KEY REFERENCES videos(id) ON DELETE CASCADE,
    palabras_totales INTEGER DEFAULT 0,
    legibilidad REAL DEFAULT 0.0,              -- Flesch-Szigriszt o similar (0-100)
    segundos_hasta_misterio REAL DEFAULT 0.0,  -- Segundo donde arranca la revelación
    n_preguntas_abiertas INTEGER DEFAULT 0,    -- Preguntas retóricas / ganchos
    menciona_caso_real INTEGER DEFAULT 0,      -- 1 si cita personas/hechos reales
    lugares TEXT,                              -- Lista o JSON de lugares citados
    fechas TEXT,                               -- Lista o JSON de años/fechas citadas
    adelanta_siguiente INTEGER DEFAULT 0,      -- 1 si hace cliffhanger hacia el siguiente punto
    tipo_gancho TEXT DEFAULT 'pregunta'        -- pregunta, dato_perturbador, paradoja, revelacion
);

-- 3. ESCENAS: Desglose por escena o bloque narrativo
CREATE TABLE IF NOT EXISTS escenas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    n_escena INTEGER NOT NULL,
    inicio_s REAL NOT NULL,
    fin_s REAL NOT NULL,
    tipo TEXT DEFAULT 'desarrollo',            -- gancho, puesto_top, desarrollo, cierre
    texto TEXT,
    palabras_por_minuto REAL DEFAULT 0.0,
    tiene_pregunta INTEGER DEFAULT 0,
    tiene_cifra INTEGER DEFAULT 0,
    emocion_voz TEXT DEFAULT 'neutral'
);

-- 4. TOMAS: Tiempos REALES de cada plano en la línea de tiempo final
CREATE TABLE IF NOT EXISTS tomas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    n_escena INTEGER NOT NULL,
    inicio_s REAL NOT NULL,                    -- Segundo real de entrada en el video final
    fin_s REAL NOT NULL,                       -- Segundo real de salida en el video final
    archivo TEXT,                              -- Nombre del archivo de B-roll o evidencia
    sha1 TEXT,                                 -- Hash SHA1 para detectar tomas reutilizadas
    fuente TEXT DEFAULT 'pixabay',             -- pixabay, pexels, commons, real, ia, fallback
    autor TEXT,                                -- Crédito o autor del metraje
    licencia TEXT DEFAULT 'libre',             -- CC0, CC-BY, Pixabay, Pexels, FairUse
    modo TEXT DEFAULT 'fill',                  -- fill, fit, panel_evidencia, ken_burns
    brillo_medio REAL DEFAULT 0.0,             -- Luminancia media signalstats YAVG (0-255)
    movimiento TEXT DEFAULT 'estatico',        -- estatico, zoom_lento, pan, zoom_punch
    aparece_host INTEGER DEFAULT 0             -- 1 si el avatar 2D está en pantalla
);

-- 5. RITMO: Velocidad de corte y presencia visual
CREATE TABLE IF NOT EXISTS ritmo (
    video_id TEXT PRIMARY KEY REFERENCES videos(id) ON DELETE CASCADE,
    cortes_por_minuto REAL DEFAULT 0.0,
    duracion_media_toma_s REAL DEFAULT 0.0,
    apariciones_host TEXT,                     -- JSON array con los segundos donde aparece el host
    subtitulos_resaltados INTEGER DEFAULT 0    -- 1 si usa karaoke con palabras clave resaltadas
);

-- 6. AUDIO: Masterización sonora, pausas y atmósfera
CREATE TABLE IF NOT EXISTS audio (
    video_id TEXT PRIMARY KEY REFERENCES videos(id) ON DELETE CASCADE,
    lufs REAL DEFAULT -16.0,                   -- LUFS integrado medido con loudnorm
    musica TEXT,                               -- Pista musical principal o mood
    efectos TEXT,                              -- Lista o JSON de SFX usados (riser, whoosh, etc.)
    n_pausas INTEGER DEFAULT 0,                -- Pausas narrativas dramáticas
    pausa_media_s REAL DEFAULT 0.0
);

-- 7. MINIATURA: Características visuales de la portada
CREATE TABLE IF NOT EXISTS miniatura (
    video_id TEXT PRIMARY KEY REFERENCES videos(id) ON DELETE CASCADE,
    archivo TEXT,                              -- Ruta relativa del archivo de miniatura
    n_palabras INTEGER DEFAULT 0,              -- Palabras de texto en la miniatura
    colores_dominantes TEXT,                   -- JSON array de colores dominantes (hex)
    tiene_cara INTEGER DEFAULT 0,              -- 1 si incluye cara o avatar
    emocion_cara TEXT DEFAULT 'neutral',       -- sorprendido, pensativo, esceptico, etc.
    tiene_rec INTEGER DEFAULT 0                -- 1 si tiene sello REC, CONFIDENCIAL, etc.
);

-- 8. TITULO_FEATURES: Atributos virales del título
CREATE TABLE IF NOT EXISTS titulo_features (
    video_id TEXT PRIMARY KEY REFERENCES videos(id) ON DELETE CASCADE,
    largo INTEGER DEFAULT 0,                   -- Caracteres totales
    tiene_numero INTEGER DEFAULT 0,            -- 1 si incluye números (e.g. Top 5)
    pct_mayusculas REAL DEFAULT 0.0,           -- Porcentaje de letras en mayúsculas
    tiene_emoji INTEGER DEFAULT 0,             -- 1 si contiene emojis
    tiene_signos INTEGER DEFAULT 0             -- 1 si contiene ?, !, etc.
);

-- 9. PRODUCCION: Curaduría de Lente y Content ID
CREATE TABLE IF NOT EXISTS produccion (
    video_id TEXT PRIMARY KEY REFERENCES videos(id) ON DELETE CASCADE,
    tomas_rechazadas_lente INTEGER DEFAULT 0,  -- Total de tomas descartadas en revisión
    motivos_rechazo TEXT,                      -- JSON array con los motivos de rechazo
    reclamos_content_id INTEGER DEFAULT 0      -- 1 si recibió reclamo en YouTube
);

-- 10. PUBLICACIONES: Subidas multi-plataforma
CREATE TABLE IF NOT EXISTS publicaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    plataforma TEXT NOT NULL,                  -- youtube, fb_pagina, fb_perfil, tiktok
    url TEXT,                                  -- Enlace público o directo
    fecha_hora_publicacion TEXT,               -- Timestamp de la publicación
    estado TEXT DEFAULT 'publico',             -- publico, oculto, no_listado, borrado
    video_platform_id TEXT                     -- ID propio de la plataforma (ej. 11 chars YT)
);

-- 11. ANALITICAS_DIARIAS: Métricas día a día por video y plataforma
CREATE TABLE IF NOT EXISTS analiticas_diarias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    plataforma TEXT NOT NULL,
    fecha TEXT NOT NULL,                       -- Formato YYYY-MM-DD
    vistas INTEGER DEFAULT 0,
    retencion_promedio_pct REAL DEFAULT 0.0,
    pct_pasa_3s REAL DEFAULT 0.0,              -- Porcentaje que no scrollea en los primeros 3s
    likes INTEGER DEFAULT 0,
    comentarios INTEGER DEFAULT 0,
    compartidos INTEGER DEFAULT 0,
    ctr_miniatura REAL DEFAULT 0.0,            -- CTR porcentaje (YouTube)
    suscriptores_ganados INTEGER DEFAULT 0,
    fuentes_trafico TEXT,                      -- JSON con distribución de tráfico
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(video_id, plataforma, fecha)
);

-- 12. RETENCION_CURVA: Curva de retención segundo a segundo o percentil
CREATE TABLE IF NOT EXISTS retencion_curva (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    plataforma TEXT NOT NULL,
    segundo_o_pct REAL NOT NULL,               -- Segundo exacto o percentil de 0.0 a 1.0
    audiencia_relativa REAL NOT NULL,          -- Retención relativa (1.0 = 100%)
    UNIQUE(video_id, plataforma, segundo_o_pct)
);

-- 13. COMENTARIOS: Cosecha y análisis de feedback de la audiencia
CREATE TABLE IF NOT EXISTS comentarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    plataforma TEXT NOT NULL,
    fecha TEXT,
    texto TEXT NOT NULL,
    sentimiento TEXT DEFAULT 'neutro',         -- positivo, negativo, neutro, intrigado
    pide_segunda_parte INTEGER DEFAULT 0,      -- 1 si pide parte 2 / continuación
    tema_sugerido TEXT,                        -- Si propone un nuevo tema en el comentario
    comment_id TEXT UNIQUE                     -- ID único del comentario en la plataforma
);

-- Índices para consultas de alta velocidad y cruce de datos
CREATE INDEX IF NOT EXISTS idx_escenas_video ON escenas(video_id);
CREATE INDEX IF NOT EXISTS idx_tomas_video ON tomas(video_id);
CREATE INDEX IF NOT EXISTS idx_tomas_tiempo ON tomas(video_id, inicio_s, fin_s);
CREATE INDEX IF NOT EXISTS idx_publicaciones_video ON publicaciones(video_id, plataforma);
CREATE INDEX IF NOT EXISTS idx_analiticas_video_fecha ON analiticas_diarias(video_id, fecha);
CREATE INDEX IF NOT EXISTS idx_retencion_video ON retencion_curva(video_id, segundo_o_pct);
CREATE INDEX IF NOT EXISTS idx_comentarios_video ON comentarios(video_id);
