"""Motor de Configuración y Filtros de Edición Cinematográfica (FFmpeg).

Lee `config/edicion.yaml` y construye los filtros visuales y sonoros para:
  - Grado de color por mood (eq + colorbalance)
  - Viñeta sutil (vignette=PI/5) + grano ligero FFmpeg (noise=alls=8:allf=t)
  - Mezcla de overlays de video (polvo, grano, light leak, glitch, vhs) con blend=screen (15-25%)
  - Movimiento suave tipo Ken Burns (zoompan 1.00 -> 1.08) en clips estáticos o cortos
  - Transiciones xfade (fade, fadeblack, smoothleft y glitch con rgbashift en cambios de puesto Top #N)
  - Flash + glitch rgbashift + riser (1-2s antes) + impact al aparecer cada tarjeta TOP #N
  - Ducking de música bajo la voz con sidechaincompress manteniendo -16 LUFS
  - Subtítulos Karaoke palabra por palabra y zoom punch para Reels 9:16
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Optional

import yaml

from . import config

# ---------------------------------------------------------------------------
# Mapa tono -> grado de color (fuente única para 16:9 y 9:16)
# ---------------------------------------------------------------------------
GRADOS_POR_TONO: dict[str, dict[str, Any]] = {
    # Frío y desaturado
    "misterio": {"saturation": 0.85, "contrast": 1.06, "brightness": -0.01,
                 "colorbalance": "rs=-0.03:gs=0.00:bs=0.05:rm=-0.02:gm=0.00:bm=0.03",
                 "curves": "master='0/0.02 0.18/0.18 0.50/0.50 0.85/0.86 1/1'"},
    "terror": {"saturation": 0.72, "contrast": 1.14, "brightness": -0.03,
               "colorbalance": "rs=-0.05:gs=0.02:bs=0.07:rm=-0.03:gm=0.02:bm=0.04",
               "curves": "master='0/0 0.20/0.16 0.50/0.47 0.85/0.84 1/0.97'"},
    # Vivos, cálidos / luminosos (saturación >= 1.1)
    "humor": {"saturation": 1.35, "contrast": 1.06, "brightness": 0.05,
              "colorbalance": "rs=0.04:gs=0.02:bs=-0.03:rm=0.04:gm=0.02:bm=-0.03",
              "curves": "master='0/0.03 0.25/0.30 0.50/0.56 0.85/0.90 1/1'"},
    "curiosidad": {"saturation": 1.25, "contrast": 1.08, "brightness": 0.03,
                   "colorbalance": "rs=0.02:gs=0.01:bs=-0.01:rm=0.03:gm=0.01:bm=-0.02:rh=0.03",
                   "curves": "master='0/0.02 0.25/0.28 0.50/0.53 0.85/0.88 1/1'"},
    # Rojo cálido de alto contraste
    "polemica": {"saturation": 1.25, "contrast": 1.20, "brightness": 0.00,
                 "colorbalance": "rs=0.08:gs=-0.01:bs=-0.06:rm=0.08:gm=-0.02:bm=-0.06:rh=0.05"},
    # Teal & orange con contraste
    "epico": {"saturation": 1.18, "contrast": 1.18, "brightness": -0.01,
              "colorbalance": "rs=-0.08:gs=0.00:bs=0.10:rm=0.03:bm=-0.03:rh=0.10:gh=0.03:bh=-0.10"},
    # Cálido suave
    "drama": {"saturation": 1.02, "contrast": 1.04, "brightness": 0.01,
              "colorbalance": "rs=0.03:bs=-0.01:rm=0.05:gm=0.01:bm=-0.03:rh=0.03",
              "curves": "master='0/0.03 0.25/0.26 0.50/0.51 0.85/0.86 1/0.98'"},
    # Neutro y limpio
    "investigacion": {"saturation": 1.05, "contrast": 1.05, "brightness": 0.01, "colorbalance": ""},
}

# Alias aceptados en guion.estilo_color (además de los nombres de tono)
ALIAS_ESTILO_COLOR: dict[str, str] = {
    "frio": "misterio", "desaturado": "misterio", "oscuro": "terror",
    "vivo": "humor", "calido": "drama", "brillante": "curiosidad",
    "rojo": "polemica", "teal_orange": "epico", "neutro": "investigacion", "limpio": "investigacion",
}


def resolver_grado(tono: Optional[str] = None, estilo_color: Any = None,
                   tonos_map: Optional[dict[str, dict[str, Any]]] = None) -> dict[str, Any]:
    """Devuelve el grado {saturation, contrast, brightness, colorbalance, curves}.
    Prioridad: guion.estilo_color (nombre de preset o dict con overrides) > guion.tono > misterio."""
    tonos_map = tonos_map or GRADOS_POR_TONO
    base_nombre = (tono or "misterio").strip().lower()
    grado = dict(tonos_map.get(base_nombre) or GRADOS_POR_TONO.get(base_nombre) or GRADOS_POR_TONO["misterio"])
    if isinstance(estilo_color, str) and estilo_color.strip():
        n = estilo_color.strip().lower()
        n = ALIAS_ESTILO_COLOR.get(n, n)
        if n in tonos_map or n in GRADOS_POR_TONO:
            grado = dict(tonos_map.get(n) or GRADOS_POR_TONO[n])
    elif isinstance(estilo_color, dict):
        n = str(estilo_color.get("base") or "").strip().lower()
        n = ALIAS_ESTILO_COLOR.get(n, n)
        if n in tonos_map or n in GRADOS_POR_TONO:
            grado = dict(tonos_map.get(n) or GRADOS_POR_TONO[n])
        for k in ("saturation", "contrast", "brightness", "colorbalance", "curves"):
            if k in estilo_color and estilo_color[k] is not None:
                grado[k] = estilo_color[k]
    return grado


DEFAULT_EDICION_CONFIG: dict[str, Any] = {
    "formatos": {
        "horizontal_16_9": {
            "fps": 30,
            "resolucion": [1920, 1080],
            "color_grading": True,
            "vignette": True,
            "film_grain_ffmpeg": True,
            "video_overlay": True,
            "ken_burns": True,
            "transiciones_xfade": True,
            "top_rank_fx": True,
            "audio_ducking_sidechain": True,
        },
        "vertical_9_16": {
            "fps": 30,
            "resolucion": [1080, 1920],
            "duracion_corte_min_s": 2.0,
            "duracion_corte_max_s": 3.0,
            "color_grading": True,
            "vignette": True,
            "film_grain_ffmpeg": True,
            "video_overlay": True,
            "zoom_punch": True,
            "subtitulos_karaoke": True,
            "audio_ducking_sidechain": True,
        },
    },
    "color_grading": {
        "enabled": True,
        "moods": {
            "misterio": {
                "saturation": 0.88,
                "contrast": 1.05,
                "brightness": 0.00,
                "colorbalance": "rs=-0.02:gs=0.01:bs=0.03:rm=-0.01:gm=0.01:bm=0.02",
                "curves": "master='0/0.02 0.18/0.19 0.50/0.51 0.85/0.86 1/1'",
            },
            "tension": {
                "saturation": 0.82,
                "contrast": 1.10,
                "brightness": -0.01,
                "colorbalance": "rs=-0.03:gs=0.01:bs=0.05:rm=-0.02:gm=0.01:bm=0.03",
                "curves": "master='0/0.01 0.20/0.20 0.50/0.51 0.85/0.86 1/1'",
            },
            "epica": {
                "saturation": 1.12,
                "contrast": 1.16,
                "brightness": -0.01,
                "colorbalance": "rs=0.08:gs=0.02:bs=-0.08:rm=0.10:gm=0.03:bm=-0.06:rh=0.06",
            },
            "curiosidad": {
                "saturation": 0.94,
                "contrast": 1.10,
                "brightness": -0.01,
                "colorbalance": "rs=-0.03:bs=0.06:rm=0.04:bm=0.04:rh=0.05",
            },
            "calma": {
                "saturation": 0.90,
                "contrast": 1.04,
                "brightness": 0.01,
                "colorbalance": "rm=0.04:gm=0.01:bm=0.03",
            },
        },
    },
    # Grado por TONO del video (guion.tono; Pluma puede forzar otro con guion.estilo_color).
    # Mapa ÚNICO usado por 16:9 (src/render.py) y 9:16 (src_tiktok/render_tt.py).
    "color_grading_tonos": GRADOS_POR_TONO,
    "textura_visual": {
        "vignette": {"enabled": True, "angle": "PI/5"},
        "film_grain_ffmpeg": {"enabled": True, "alls": 8, "allf": "t"},
        "video_overlay": {
            "enabled": True,
            "blend_mode": "screen",
            "opacity": 0.18,
            "por_mood": {
                "misterio": ["dust_overlay", "film_grain", "vhs"],
                "tension": ["film_grain", "glitch", "vhs"],
                "epica": ["light_leak", "dust_overlay", "film_grain"],
                "curiosidad": ["dust_overlay", "light_leak", "film_grain"],
                "calma": ["dust_overlay", "light_leak"],
            },
        },
    },
    "ken_burns": {
        "enabled": True,
        "zoom_inicial": 1.00,
        "zoom_final": 1.08,
        "aplicar_en_estaticos": True,
        "aplicar_en_clips_cortos": True,
    },
    "transiciones": {
        "enabled": True,
        "duracion_s": 0.35,
        "tipos_normales": ["fade", "fadeblack", "smoothleft"],
        "en_cambio_top": "glitch",
        "sfx_whoosh": True,
    },
    "top_rank_fx": {
        "enabled": True,
        "riser_enabled": True,
        "riser_lead_s": 1.5,
        "riser_volume": 0.65,
        "impact_enabled": True,
        "impact_volume": 0.85,
        "flash_glitch_enabled": True,
        "flash_duracion_s": 0.35,
        "rgbashift_rh": -6,
        "rgbashift_bh": 6,
        "flash_brightness": 0.12,
        "card_delay_post_glitch_s": 0.35,
        "card_duracion_s": 3.5,
        "card_font_size_top": 184,
        "card_font_size_titulo": 116,
        "card_back_colour": "&H58000000",
    },
    "audio": {
        "ducking_sidechain": {
            "enabled": True,
            "musica_volumen_base": 0.28,
            "threshold": 0.035,
            "ratio": 5.0,
            "attack_ms": 35,
            "release_ms": 450,
            "makeup": 1.0,
        },
        "lufs_target": -16.0,
    },
    "reels_9_16": {
        "cortes_rapidos": {"enabled": True, "min_s": 2.0, "max_s": 3.0},
        "karaoke": {
            "enabled": True,
            "font_size": 112,
            "palabras_por_linea": 3,
            "color_activo": "&H0000FFFF&",
            "color_inactivo": "&H00FFFFFF&",
            "color_keyword": "&H00FFFF00&",
        },
        "zoom_punch": {"enabled": True, "factor": 1.08, "duracion_s": 0.35},
    },
}

_AVISOS_OVERLAY_EMITIDOS: set[str] = set()


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def cargar_config_edicion() -> dict[str, Any]:
    """Carga `config/edicion.yaml` fusionándolo con los valores por defecto."""
    ruta = config.CONFIG_EDICION_YAML
    if ruta.exists():
        try:
            datos = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
            if isinstance(datos, dict):
                return _deep_merge(DEFAULT_EDICION_CONFIG, datos)
        except Exception as e:
            print(f"⚠️ Aviso: Error leyendo {ruta} ({e}), usando configuración de edición por defecto.")
    return copy.deepcopy(DEFAULT_EDICION_CONFIG)


# Overlays retirados del pool: muestran texto legible (p. ej. 27706 es código fuente C# de Unity) que
# se lee sobre fondos oscuros al mezclarse en screen. Se excluyen aunque el archivo siga en la carpeta.
OVERLAYS_BLOQUEADOS: frozenset[str] = frozenset({"glitch_pixabay_27706.mp4"})


def listar_archivos_overlay(carpeta: Path, bloqueados: Optional[set[str]] = None) -> list[Path]:
    """Lista videos de overlay (.mp4, .mov, .webm) válidos en una carpeta, sin los bloqueados."""
    if not carpeta.exists() or not carpeta.is_dir():
        return []
    fuera = {b.lower() for b in (OVERLAYS_BLOQUEADOS | set(bloqueados or ()))}
    archivos: list[Path] = []
    for ext in ("*.mp4", "*.mov", "*.webm"):
        archivos.extend(sorted(carpeta.glob(ext)))
    return [a for a in archivos if a.is_file() and a.stat().st_size > 10_000 and a.name.lower() not in fuera]


def resolver_overlay_por_mood(
    mood: str = "misterio",
    idx_escena: int = 1,
    es_inicio_top: bool = False,
    cfg: Optional[dict[str, Any]] = None,
    silencioso: bool = False,
) -> tuple[Optional[Path], str]:
    """Selecciona un video de overlay acorde al mood (o glitch si abre un puesto Top).
    Si falta el tipo preferido, degrada con elegancia a otro overlay disponible o a None (solo FFmpeg noise)."""
    cfg = cfg or cargar_config_edicion()
    ov_cfg = cfg.get("textura_visual", {}).get("video_overlay", {})
    if not ov_cfg.get("enabled", True):
        return None, "desactivado"

    por_mood = ov_cfg.get("por_mood", {})
    preferidos = list(por_mood.get(mood, ["dust_overlay", "film_grain"]))
    if es_inicio_top and "glitch" not in preferidos[:1]:
        preferidos = ["glitch", "vhs"] + preferidos

    # Añadir el resto de tipos conocidos como fallback
    for t in config.OVERLAY_TIPOS:
        if t not in preferidos:
            preferidos.append(t)

    for i, tipo in enumerate(preferidos):
        archivos = listar_archivos_overlay(config.OVERLAYS_DIR / tipo, set(ov_cfg.get("bloqueados", []) or []))
        if archivos:
            elegido = archivos[(idx_escena - 1) % len(archivos)]
            if i > 0 and not silencioso:
                tipo_ideal = preferidos[0]
                clave = f"overlay:{tipo_ideal}->{tipo}"
                if clave not in _AVISOS_OVERLAY_EMITIDOS:
                    _AVISOS_OVERLAY_EMITIDOS.add(clave)
                    print(f"   ⚠️ Overlay '{tipo_ideal}' sin archivos -> usando fallback '{tipo}' ({elegido.name})")
            return elegido, tipo

    if not silencioso and "overlay:none" not in _AVISOS_OVERLAY_EMITIDOS:
        _AVISOS_OVERLAY_EMITIDOS.add("overlay:none")
        print("   ℹ️ Sin archivos en assets/overlays/ -> degradando con elegancia a grano y viñeta generados por FFmpeg.")
    return None, "ffmpeg_grain"


def construir_filtro_color_textura(
    mood: str = "misterio",
    formato: str = "horizontal_16_9",
    es_inicio_top: bool = False,
    cfg: Optional[dict[str, Any]] = None,
    tono: Optional[str] = None,
    estilo_color: Any = None,
) -> str:
    """Construye la cadena de filtros FFmpeg para grado de color por mood, viñeta, grano y flash/glitch en Top #N."""
    cfg = cfg or cargar_config_edicion()
    fmt_cfg = cfg.get("formatos", {}).get(formato, {})
    partes: list[str] = []

    # 1. Grado de color por mood (eq + colorbalance + curves para preservar sombras)
    cg_cfg = cfg.get("color_grading", {})
    if fmt_cfg.get("color_grading", True) and cg_cfg.get("enabled", True):
        # El TONO del guion manda (antes 'misterio' caía al grado por mood, siempre frío/desaturado)
        tonos_map = {**GRADOS_POR_TONO, **(cfg.get("color_grading_tonos") or {})}
        m_cfg = resolver_grado(tono, estilo_color, tonos_map)
        sat = float(m_cfg.get("saturation", 0.88))
        con = float(m_cfg.get("contrast", 1.05))
        bri = float(m_cfg.get("brightness", 0.00))
        partes.append(f"eq=saturation={sat:.2f}:contrast={con:.2f}:brightness={bri:.2f}")
        cb = (m_cfg.get("colorbalance") or "").strip()
        if cb:
            partes.append(f"colorbalance={cb}")
        curves_expr = (m_cfg.get("curves") or "").strip()
        if curves_expr:
            partes.append(f"curves={curves_expr}")

    # 2. Flash + Glitch (rgbashift) al inicio de cada puesto TOP #N
    top_fx = cfg.get("top_rank_fx", {})
    if es_inicio_top and fmt_cfg.get("top_rank_fx", True) and top_fx.get("enabled", True) and top_fx.get("flash_glitch_enabled", True):
        dur_fl = float(top_fx.get("flash_duracion_s", 0.35))
        rh = int(top_fx.get("rgbashift_rh", -6))
        bh = int(top_fx.get("rgbashift_bh", 6))
        fl_bri = float(top_fx.get("flash_brightness", 0.12))
        partes.append(f"rgbashift=rh={rh}:bh={bh}:enable=between(t\\,0\\,{dur_fl:.2f})")
        partes.append(f"eq=brightness={fl_bri:.2f}:contrast=1.18:enable=between(t\\,0\\,{min(0.25, dur_fl):.2f})")

    # 3. Viñeta sutil (vignette=PI/5)
    vig_cfg = cfg.get("textura_visual", {}).get("vignette", {})
    if fmt_cfg.get("vignette", True) and vig_cfg.get("enabled", True):
        angulo = vig_cfg.get("angle", "PI/5")
        partes.append(f"vignette={angulo}")

    # 4. Grano cinematográfico ligero (noise=alls=8:allf=t)
    gr_cfg = cfg.get("textura_visual", {}).get("film_grain_ffmpeg", {})
    if fmt_cfg.get("film_grain_ffmpeg", True) and gr_cfg.get("enabled", True):
        alls = int(gr_cfg.get("alls", 8))
        allf = gr_cfg.get("allf", "t")
        partes.append(f"noise=alls={alls}:allf={allf}")

    partes.append("format=yuv420p")
    return ",".join(partes)


def construir_filtro_ken_burns(
    duracion: float,
    ancho: int = 1920,
    alto: int = 1080,
    fps: int = 30,
    cfg: Optional[dict[str, Any]] = None,
) -> str:
    """Construye un movimiento suave tipo Ken Burns (zoompan lento 1.00 -> 1.08) para clips estáticos o cortos."""
    cfg = cfg or cargar_config_edicion()
    kb = cfg.get("ken_burns", {})
    z_ini = float(kb.get("zoom_inicial", 1.00))
    z_fin = float(kb.get("zoom_final", 1.08))
    frames = max(30, int(round(duracion * fps)))
    paso = max(0.0001, (z_fin - z_ini) / float(frames))
    w_pre = int(round(ancho * 1.15))
    h_pre = int(round(alto * 1.15))
    return (
        f"scale={w_pre}:{h_pre}:force_original_aspect_ratio=increase,"
        f"crop={w_pre}:{h_pre},"
        f"zoompan=z='min(zoom+{paso:.6f},{z_fin:.3f})':d=1:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={ancho}x{alto}:fps={fps},"
        f"setsar=1,format=yuv420p"
    )


def construir_filtro_zoom_punch_vertical(
    duracion: float,
    ancho: int = 1080,
    alto: int = 1920,
    fps: int = 30,
    cfg: Optional[dict[str, Any]] = None,
) -> str:
    """Construye el filtro de recorte vertical 9:16 con zoom punch dinámico en la palabra clave."""
    cfg = cfg or cargar_config_edicion()
    zp = cfg.get("reels_9_16", {}).get("zoom_punch", {})
    fmt_cfg = cfg.get("formatos", {}).get("vertical_9_16", {})
    if not (fmt_cfg.get("zoom_punch", True) and zp.get("enabled", True)):
        return f"scale={ancho}:{alto}:force_original_aspect_ratio=increase,crop={ancho}:{alto},fps={fps}"

    factor = float(zp.get("factor", 1.08))
    w_pre = int(round(ancho * 1.12))
    h_pre = int(round(alto * 1.12))
    # Zoom punch: entra en el frame 5 (~0.16s) al aparecer la palabra clave y mantiene tensión
    return (
        f"scale={w_pre}:{h_pre}:force_original_aspect_ratio=increase,"
        f"crop={w_pre}:{h_pre},"
        f"zoompan=z='if(between(on,4,18),{factor:.3f},min(zoom+0.0008,1.05))':d=1:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={ancho}x{alto}:fps={fps},"
        f"setsar=1,format=yuv420p"
    )
