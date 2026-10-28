"""Ken Burns para fotos fijas (Commons, códices) armadas como clips de B-roll.

Causa del "foto estática" que marcó Lente v2 (7.2, 10.1, 20.5, 24.6, 25.1): la amplitud del movimiento era fija
(zoom 1.00->1.14, paneo con zoom 1.12-1.15) y se repartía sobre todo el clip, que dura el corte + 1.5 s de margen.
El render sólo muestra el corte, así que en tomas de 4-6 s lo visible era un desplazamiento de ~4-9 % del cuadro
(~15 px/s): técnicamente se mueve, pero a ojo, y para un tracker anclado al host fijo, parece una foto quieta.

Aquí la amplitud se calcula para que lo VISIBLE (los frames del corte) recorra al menos MIN_VISIBLE del cuadro.
"""
from __future__ import annotations

MOVIMIENTOS = ("zin", "zout", "pan_lr", "pan_rl", "pan_ud", "pan_du")
MIN_VISIBLE = 0.12   # fracción mínima de cambio visible (zoom relativo o recorrido del paneo)
ZOOM_MAX = 1.40


def _fraccion_visible(n_frames: int, frames_visibles: int | None) -> float:
    if not frames_visibles or frames_visibles >= n_frames:
        return 1.0
    return max(frames_visibles, 1) / n_frames


def zoom_total(mov: str, n_frames: int, frames_visibles: int | None = None) -> float:
    """Zoom (máximo) del clip para que lo visible cambie al menos MIN_VISIBLE."""
    if mov not in MOVIMIENTOS:
        raise ValueError(f"movimiento desconocido: {mov}")
    f = _fraccion_visible(n_frames, frames_visibles)
    if mov in ("zin", "zout"):
        return min(ZOOM_MAX, 1.0 + MIN_VISIBLE / f)
    # paneo: recorrido total = (1 - 1/z) del cuadro; lo visible es esa fracción * f
    return min(ZOOM_MAX, 1.0 / max(1e-6, 1.0 - MIN_VISIBLE / f))


def cambio_visible(mov: str, n_frames: int, frames_visibles: int | None = None) -> float:
    """Cambio visible durante el corte: zoom relativo (zin/zout) o recorrido como fracción del cuadro (paneos)."""
    z = zoom_total(mov, n_frames, frames_visibles)
    f = _fraccion_visible(n_frames, frames_visibles)
    if mov in ("zin", "zout"):
        return (z - 1.0) * f
    return (1.0 - 1.0 / z) * f


def expr_zoompan(mov: str, n_frames: int, ancho: int, alto: int, frames_visibles: int | None = None, fps: int = 30) -> str:
    """Filtro zoompan de FFmpeg para el movimiento pedido, salida ancho x alto."""
    z = zoom_total(mov, n_frames, frames_visibles)
    a = z - 1.0
    t = f"(on/{n_frames})"
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if mov == "zin":
        zz, x, y = f"1.0+{a:.4f}*{t}", cx, cy
    elif mov == "zout":
        zz, x, y = f"{z:.4f}-{a:.4f}*{t}", cx, cy
    elif mov == "pan_lr":
        zz, x, y = f"{z:.4f}", f"(iw-iw/zoom)*{t}", cy
    elif mov == "pan_rl":
        zz, x, y = f"{z:.4f}", f"(iw-iw/zoom)*(1-{t})", cy
    elif mov == "pan_ud":
        zz, x, y = f"{z:.4f}", cx, f"(ih-ih/zoom)*{t}"
    else:
        zz, x, y = f"{z:.4f}", cx, f"(ih-ih/zoom)*(1-{t})"
    return f"zoompan=z='{zz}':x='{x}':y='{y}':d={n_frames}:s={ancho}x{alto}:fps={fps}"
