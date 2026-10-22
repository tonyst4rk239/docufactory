"""Retención por tomas + clips reales transformados ('EVIDENCIA').

- Cada escena se divide en tomas de `corte_min_s`-`corte_max_s` (config/edicion.yaml -> tomas).
- Los fragmentos reales declarados en `clips_fuente` se descargan primero con yt-dlp (solo el rango
  3-6 s, nunca el video completo; admite YTDLP_COOKIES y cualquier sitio soportado), y se transforman
  en un panel 'EVIDENCIA' (~70 %, sobre fondo desenfocado/oscurecido, zoom lento, crédito en pantalla).
- El resto del tiempo se rellena con B-roll libre distinto (sin duplicados en todo el video), buscado
  con consultas cortas de 2-3 palabras derivadas de `broll_queries_en`.
- Manifiesto por escena: b_roll/escena_XXX_tomas.json
"""
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

from . import config
from .layout import ALTO, ANCHO, caja_host, zona_texto

DEF_TOMAS = {"enabled": True, "corte_min_s": 3.0, "corte_max_s": 5.0, "max_clips_distintos_por_escena": 6}
DEF_REALES = {
    "duracion_min_s": 3.0, "duracion_max_s": 6.0, "escala_panel": 0.70, "etiqueta": "EVIDENCIA",
    "zoom_lento": 0.06, "oscurecer_fondo": -0.22, "desenfoque_fondo": 22,
}
MAX_DURACION_RESPALDO_S = 600
_STOP = {"the", "a", "an", "of", "in", "on", "at", "with", "and", "or", "to", "for", "by", "from",
         "into", "over", "under", "close", "up", "shot", "footage", "video", "cinematic", "4k", "hd"}


def cfg_tomas(cfg: Optional[dict] = None) -> dict:
    if cfg is None:
        try:
            from .edicion import cargar_config_edicion
            cfg = cargar_config_edicion()
        except Exception:
            cfg = {}
    return {**DEF_TOMAS, **(cfg.get("tomas") or {})}


def cfg_reales(cfg: Optional[dict] = None) -> dict:
    if cfg is None:
        try:
            from .edicion import cargar_config_edicion
            cfg = cargar_config_edicion()
        except Exception:
            cfg = {}
    return {**DEF_REALES, **(cfg.get("clips_reales") or {})}


# ----------------------------------------------------------------------------- planificación
def planificar_cortes(duracion: float, corte_min: float = 3.0, corte_max: float = 5.0,
                      fijos: Optional[list[float]] = None) -> list[float]:
    """Divide la duración de la escena en tomas. `fijos` (clips reales) van primero."""
    cortes: list[float] = []
    restante = float(duracion)
    for f in fijos or []:
        if restante <= 0.05:
            break
        d = min(float(f), restante)
        cortes.append(round(d, 3))
        restante -= d
    if restante > 0.05:
        n = max(1, math.ceil(restante / corte_max))
        while n > 1 and restante / n < corte_min:
            n -= 1
        cortes += [round(restante / n, 3)] * n
    # Ajuste final para que la suma sea exacta
    if cortes:
        cortes[-1] = round(cortes[-1] + (duracion - sum(cortes)), 3)
    return cortes


def consultas_cortas(queries: list[str], mood: str = "misterio") -> list[str]:
    """Consultas de 2-3 palabras significativas derivadas de broll_queries_en (sin duplicados)."""
    salida: list[str] = []
    for q in queries or []:
        pal = [w for w in re.findall(r"[A-Za-z0-9]+", (q or "").lower()) if w not in _STOP and len(w) > 2]
        variantes = []
        if len(pal) >= 3:
            variantes += [" ".join(pal[:3]), " ".join(pal[:2]), " ".join(pal[-2:])]
        elif pal:
            variantes.append(" ".join(pal))
        for v in variantes:
            if v and v not in salida:
                salida.append(v)
    respaldo = {"misterio": "dark fog night", "tension": "dark shadows night", "epica": "storm clouds",
                "curiosidad": "old archive", "calma": "night sky"}.get(mood, "dark night")
    if respaldo not in salida:
        salida.append(respaldo)
    return salida


def _id_pixabay(key_o_url: str) -> Optional[int]:
    m = re.search(r"pixabay:(\d+)", key_o_url or "") or re.search(r"/video/\d{4}/\d{2}/\d{2}/(\d+)", key_o_url or "")
    return int(m.group(1)) if m else None


def misma_serie(key: str, usados: set[str], tolerancia: int = 6) -> bool:
    """Pixabay publica series del mismo autor con IDs consecutivos (ej. 63970/63974): se evitan."""
    pid = _id_pixabay(key)
    if pid is None:
        return False
    for u in usados:
        uid = _id_pixabay(u)
        if uid is not None and uid != pid and abs(uid - pid) <= tolerancia:
            return True
    return False


# ----------------------------------------------------------------------------- utilidades ffmpeg
def _ffmpeg() -> str:
    return config.ffmpeg_bin("ffmpeg") or "ffmpeg"


def _run(cmd: list[str], timeout: int = 600) -> bool:
    try:
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=timeout)
        return r.returncode == 0
    except Exception:
        return False


def _ruta_filtro(ruta: Path) -> str:
    """Ruta segura para filtros FFmpeg en Windows y Linux (C\\:/... y comillas escapadas)."""
    return str(Path(ruta).resolve().as_posix()).replace(":", "\\:").replace("'", "\\'")


# ----------------------------------------------------------------------------- clips reales
def descargar_fragmento_real(url: str, inicio: float, duracion: float, destino: Path) -> tuple[bool, str]:
    """Descarga SOLO el rango [inicio, inicio+duracion] con yt-dlp y lo normaliza a MP4 sin audio."""
    try:
        import yt_dlp
        from yt_dlp.utils import download_range_func
    except Exception as e:  # pragma: no cover
        return False, f"yt-dlp no disponible: {e}"
    from .broll import opciones_ytdlp_base

    destino.parent.mkdir(parents=True, exist_ok=True)

    def _intento(por_rango: bool) -> tuple[bool, str]:
        tmpdir = Path(tempfile.mkdtemp(prefix="real_", dir=str(destino.parent)))
        try:
            opts = opciones_ytdlp_base()
            opts.update({
                "outtmpl": str(tmpdir / "frag.%(ext)s"),
                "format": "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b",
                "merge_output_format": "mp4",
                "noplaylist": True,
                "retries": 2,
                "socket_timeout": 30,
                "noprogress": True,
            })
            if por_rango:
                opts["download_ranges"] = download_range_func(None, [(float(inicio), float(inicio) + float(duracion))])
                opts["force_keyframes_at_cuts"] = True
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    if not por_rango:
                        info = ydl.extract_info(url, download=False) or {}
                        if float(info.get("duration") or 0) > MAX_DURACION_RESPALDO_S:
                            return False, f"video de {info.get('duration')} s: demasiado largo para respaldo"
                    ydl.download([url])
            except Exception as e:
                return False, str(e).splitlines()[0][:220]
            archivos = [f for f in tmpdir.iterdir() if f.is_file() and f.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov")
                        and f.stat().st_size > 10_000]
            if not archivos:
                return False, "yt-dlp no produjo un archivo de video válido"
            pre = [] if por_rango else ["-ss", f"{float(inicio):.2f}"]
            ok = _run([_ffmpeg(), "-y", *pre, "-i", str(archivos[0]), "-t", f"{duracion:.2f}", "-an",
                       "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(destino)])
            ok = ok and destino.exists() and destino.stat().st_size > 1000
            return ok, ("" if ok else "fallo al normalizar con ffmpeg")
        finally:
            # El archivo temporal (rango o completo) se elimina siempre: solo queda el fragmento de 3-6 s
            shutil.rmtree(tmpdir, ignore_errors=True)

    ok, err = _intento(por_rango=True)
    if not ok:
        # Algunos sitios (p. ej. X con HLS) no soportan cortes por rango: se descarga a temporal y se recorta
        ok2, err2 = _intento(por_rango=False)
        if ok2:
            return True, ""
        return False, f"{err} | respaldo: {err2}"
    return ok, err


def geometria_panel(pose: str, host_lado: str, host_visible: bool, escala: float = 0.70) -> tuple[int, int, int, int]:
    """(cx, cy, max_w, max_h) del panel EVIDENCIA, en el lado opuesto al host y sin solaparlo."""
    zona = zona_texto(caja_host(pose, host_lado, host_visible))
    max_w = int(min(ANCHO * escala, zona.w))
    max_h = int(min(ALTO * escala, ALTO - 2 * 150))
    cx = int(zona.x + zona.w / 2)
    cy = int(ALTO / 2 + 10)
    return cx, cy, max_w, max_h


ESTILOS_REALES = ("evidencia", "completo", "dividido", "congelado")


def luminancia_media(ruta: Path) -> Optional[float]:
    """YAVG medio (0-255) de un fragmento, con signalstats sobre ~4 cuadros por segundo."""
    try:
        r = subprocess.run([_ffmpeg(), "-hide_banner", "-i", str(ruta), "-vf", "fps=4,signalstats,metadata=print:key=lavfi.signalstats.YAVG",
                            "-f", "null", "-"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120, text=True)
        vals = [float(v) for v in re.findall(r"YAVG=([0-9.]+)", r.stdout)]
        return sum(vals) / len(vals) if vals else None
    except Exception:
        return None


def _filtro_previo(recorte: Optional[list[float]], yavg: Optional[float], cfg_r: dict) -> str:
    """Recorte opcional (quita marcos/textos del original) + realce de tomas oscuras (evita cuadros casi negros)."""
    partes = []
    if recorte and len(recorte) == 4:
        x, y, w, h = [max(0.0, min(1.0, float(v))) for v in recorte]
        w, h = max(0.05, min(w, 1 - x)), max(0.05, min(h, 1 - y))
        partes.append(f"crop=trunc(iw*{w:.4f}/2)*2:trunc(ih*{h:.4f}/2)*2:iw*{x:.4f}:ih*{y:.4f}")
    umbral = float(cfg_r.get("yavg_realce", 55))
    if yavg is not None and yavg < umbral:
        # Más realce cuanto más oscuro (gamma 1.15-1.8); nunca deja la toma casi negra
        g = min(1.8, 1.15 + (umbral - yavg) / 60.0)
        partes.append(f"eq=gamma={g:.2f}:brightness=0.03:contrast=1.04")
    return ",".join(partes)


def transformar_real(raw: Path, destino: Path, duracion: float, credito: str, etiqueta: str = "EVIDENCIA",
                     estilo: str = "evidencia", recorte: Optional[list[float]] = None,
                     pose: str = "explicando", host_lado: str = "izquierda", host_visible: bool = True,
                     resaltar: Optional[list[float]] = None, cfg: Optional[dict] = None) -> bool:
    """Transforma un fragmento real (3-6 s) en una toma con contexto y crédito SIEMPRE visible.

    Estilos:
      - evidencia: panel ~70 % con marco amarillo sobre fondo desenfocado, zoom lento.
      - completo:  pantalla completa (o vertical centrado sobre fondo desenfocado) con viñeta.
      - dividido:  comparación ORIGINAL | ACERCAMIENTO (zona de `resaltar` o centro) lado a lado.
      - congelado: reproduce ~45 % y congela el cuadro con resalte y rótulo 'CUADRO CONGELADO'.
    Todo se coloca en la zona opuesta al host (layout.zona_texto) para no solaparlo.
    """
    rc = cfg_reales(cfg)
    estilo = (estilo or "evidencia").lower()
    if estilo not in ESTILOS_REALES:
        estilo = "evidencia"
    D = max(0.5, float(duracion))
    z = float(rc["zoom_lento"])
    fuente = config.FONTS_DIR / "bold.ttf"
    zona = zona_texto(caja_host(pose, host_lado, host_visible))
    tmp = Path(tempfile.mkdtemp(prefix="ev_", dir=str(destino.parent)))
    try:
        (tmp / "etq.txt").write_text(f" {etiqueta.upper()} ", encoding="utf-8")
        (tmp / "cred.txt").write_text(f"Fuente: {credito or 'redes sociales'}", encoding="utf-8")
        (tmp / "frz.txt").write_text(" CUADRO CONGELADO ", encoding="utf-8")
        (tmp / "ori.txt").write_text(" ORIGINAL ", encoding="utf-8")
        (tmp / "zoom.txt").write_text(" ACERCAMIENTO ", encoding="utf-8")
        from .broll import obtener_dimensiones_video
        try:
            iw, ih, _ = obtener_dimensiones_video(raw)
        except Exception:
            iw, ih = 1920, 1080
        iw, ih = (iw or 1920), (ih or 1080)
        if recorte and len(recorte) == 4:
            iw = max(2, int(iw * max(0.05, float(recorte[2]))))
            ih = max(2, int(ih * max(0.05, float(recorte[3]))))
        pre = _filtro_previo(recorte, luminancia_media(raw), rc)
        pre_c = (pre + ",") if pre else ""
        ff = f":fontfile='{_ruta_filtro(fuente)}'" if fuente.exists() else ""
        etq = f"textfile='{_ruta_filtro(tmp / 'etq.txt')}'{ff}:fontsize=46:fontcolor=white:box=1:boxcolor=0xC81E1E@0.95:boxborderw=12"
        cred = f"textfile='{_ruta_filtro(tmp / 'cred.txt')}'{ff}:fontsize=34:fontcolor=white:box=1:boxcolor=black@0.65:boxborderw=10"
        hl_box = ""
        if resaltar and len(resaltar) == 4:
            fx, fy, fw, fh = [max(0.0, min(1.0, float(v))) for v in resaltar]
            hl_box = f"drawbox=x=iw*{fx:.3f}:y=ih*{fy:.3f}:w=iw*{fw:.3f}:h=ih*{fh:.3f}:color=red@0.9:t=6"
        fondo = (f"[a]{pre_c}scale={ANCHO}:{ALTO}:force_original_aspect_ratio=increase,crop={ANCHO}:{ALTO},"
                 f"boxblur={int(rc['desenfoque_fondo'])}:2,eq=brightness={float(rc['oscurecer_fondo']):.2f}:saturation=0.6,setsar=1[bg];")
        cx = int(zona.x + zona.w / 2)
        if estilo == "completo":
            # Pantalla completa si es horizontal; vertical/cuadrado centrado en la zona libre sobre fondo desenfocado
            esc = min(ANCHO / iw, ALTO / ih)
            qw, qh = max(2, int(iw * esc) // 2 * 2), max(2, int(ih * esc) // 2 * 2)
            ox = 0 if qw >= ANCHO - 4 else max(0, min(ANCHO - qw, cx - qw // 2))
            filtro = (
                f"[0:v]split[a][b];{fondo}"
                f"[b]{pre_c}scale={qw}:{qh},setsar=1,"
                f"scale=w='trunc({qw}*(1+{z}*t/{D:.2f})/2)*2':h='trunc({qh}*(1+{z}*t/{D:.2f})/2)*2':eval=frame,crop={qw}:{qh}"
                f"{(',' + hl_box) if hl_box else ''}[pn];"
                f"[bg][pn]overlay=x={ox}:y=(H-h)/2:shortest=1,vignette=angle=PI/4,"
                f"drawtext={etq}:x={cx}-text_w/2:y={ALTO - 190},"
                f"drawtext={cred}:x={cx}-text_w/2:y={ALTO - 110},"
                f"fps=30,format=yuv420p[v]"
            )
        elif estilo == "dividido":
            gap = 40
            bw = int((min(zona.w, ANCHO * 0.9) - gap) / 2) // 2 * 2
            bh = int(min(ALTO * 0.62, bw * ih / iw * 1.0 if iw >= ih else ALTO * 0.62)) // 2 * 2
            esc = min(bw / iw, bh / ih)
            qw, qh = max(2, int(iw * esc) // 2 * 2), max(2, int(ih * esc) // 2 * 2)
            if resaltar and len(resaltar) == 4:
                fx, fy, fw, fh = [max(0.0, min(1.0, float(v))) for v in resaltar]
                ccx, ccy = fx + fw / 2, fy + fh / 2
                zf = max(1.6, min(3.0, 1.0 / max(fw, fh, 0.2)))
            else:
                ccx, ccy, zf = 0.5, 0.5, 2.0
            cw, ch = 1.0 / zf, 1.0 / zf
            x0, y0 = max(0.0, min(1 - cw, ccx - cw / 2)), max(0.0, min(1 - ch, ccy - ch / 2))
            lx = cx - gap // 2 - qw
            rx = cx + gap // 2
            cy = ALTO // 2 - qh // 2 + 10
            filtro = (
                f"[0:v]split=3[a][b][c];{fondo}"
                f"[b]{pre_c}scale={qw}:{qh},setsar=1{(',' + hl_box) if hl_box else ''},"
                f"drawbox=x=0:y=0:w=iw:h=ih:color=0xFFD400@0.95:t=5[l];"
                f"[c]{pre_c}crop=iw*{cw:.3f}:ih*{ch:.3f}:iw*{x0:.3f}:ih*{y0:.3f},scale={qw}:{qh},setsar=1,"
                f"unsharp=5:5:0.8,drawbox=x=0:y=0:w=iw:h=ih:color=red@0.95:t=5[r];"
                f"[bg][l]overlay=x={lx}:y={cy}:shortest=1[t1];[t1][r]overlay=x={rx}:y={cy}:shortest=1,"
                f"drawtext=textfile='{_ruta_filtro(tmp / 'ori.txt')}'{ff}:fontsize=38:fontcolor=black:box=1:boxcolor=0xFFD400@0.95:boxborderw=10:x={lx}:y={cy}-62,"
                f"drawtext=textfile='{_ruta_filtro(tmp / 'zoom.txt')}'{ff}:fontsize=38:fontcolor=white:box=1:boxcolor=0xC81E1E@0.95:boxborderw=10:x={rx}:y={cy}-62,"
                f"drawtext={cred}:x={cx}-text_w/2:y={cy + qh + 26},"
                f"fps=30,format=yuv420p[v]"
            )
        else:
            pcx, pcy, pw, ph = geometria_panel(pose, host_lado, host_visible, float(rc["escala_panel"]))
            esc_fit = min(pw / iw, ph / ih)
            qw, qh = max(2, int(iw * esc_fit) // 2 * 2), max(2, int(ih * esc_fit) // 2 * 2)
            if estilo == "congelado":
                t1 = round(max(1.0, D * 0.45), 2)
                fr = 1.0 / 30
                cuerpo = (f"[b]{pre_c}scale={qw}:{qh},setsar=1,fps=30,split[b1][b2];"
                          f"[b1]trim=duration={t1},setpts=PTS-STARTPTS[p1];"
                          f"[b2]trim=start={max(0.0, t1 - fr):.3f}:duration={fr:.3f},setpts=PTS-STARTPTS,"
                          f"loop=loop={int((D - t1) * 30) + 2}:size=1,setpts=N/30/TB,trim=duration={D - t1:.2f}[p2];"
                          f"[p1][p2]concat=n=2:v=1:a=0,"
                          f"scale=w='trunc({qw}*(1+{z * 1.6}*max(0,t-{t1})/{D:.2f})/2)*2':h='trunc({qh}*(1+{z * 1.6}*max(0,t-{t1})/{D:.2f})/2)*2':eval=frame,"
                          f"crop={qw}:{qh},eq=saturation=0.75:enable='gte(t,{t1})'"
                          f"{(',' + hl_box + ':enable=' + chr(39) + f'gte(t,{t1})' + chr(39)) if hl_box else ''},")
                extra = (f"drawtext=textfile='{_ruta_filtro(tmp / 'frz.txt')}'{ff}:fontsize=36:fontcolor=black:box=1:"
                         f"boxcolor=white@0.92:boxborderw=10:x={pcx}+{qw}/2-text_w-18:y={pcy}-{qh}/2+18:enable='gte(t,{t1})',")
            else:
                cuerpo = (f"[b]{pre_c}scale={qw}:{qh},setsar=1,"
                          f"scale=w='trunc({qw}*(1+{z}*t/{D:.2f})/2)*2':h='trunc({qh}*(1+{z}*t/{D:.2f})/2)*2':eval=frame,"
                          f"crop={qw}:{qh}{(',' + hl_box) if hl_box else ''},")
                extra = ""
            filtro = (
                f"[0:v]split[a][b];{fondo}{cuerpo}"
                f"drawbox=x=0:y=0:w=iw:h=ih:color=0xFFD400@0.95:t=6[pn];"
                f"[bg][pn]overlay=x={pcx}-w/2:y={pcy}-h/2:eof_action=repeat,"
                f"drawtext={etq}:x={pcx}-{qw}/2:y={pcy}-{qh}/2-78,{extra}"
                f"drawtext={cred}:x={pcx}-text_w/2:y={pcy}+{qh}/2+26,"
                f"fps=30,format=yuv420p[v]"
            )
        ok = _run([_ffmpeg(), "-y", "-stream_loop", "-1", "-i", str(raw), "-filter_complex", filtro,
                   "-map", "[v]", "-t", f"{D:.2f}", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(destino)])
        return ok and destino.exists() and destino.stat().st_size > 1000
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def transformar_evidencia(raw: Path, destino: Path, duracion: float, credito: str, etiqueta: str = "EVIDENCIA",
                          pose: str = "explicando", host_lado: str = "izquierda", host_visible: bool = True,
                          resaltar: Optional[list[float]] = None, cfg: Optional[dict] = None) -> bool:
    """Compatibilidad: panel 'EVIDENCIA' clásico."""
    return transformar_real(raw, destino, duracion, credito, etiqueta, "evidencia", None, pose, host_lado,
                            host_visible, resaltar, cfg)


# ----------------------------------------------------------------------------- preparación por escena
def ruta_manifiesto(p, escena_id: int) -> Path:
    return p.ruta("b_roll", f"escena_{escena_id:03d}_tomas.json")


def cargar_manifiesto(p, escena_id: int) -> Optional[dict]:
    f = ruta_manifiesto(p, escena_id)
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None


def preparar_tomas_escena(p, esc, dur_audio: float, clips_usados: set[str], rechazos_esc: list[dict],
                          url_principal: str = "", cfg: Optional[dict] = None) -> dict:
    """Descarga clips reales + B-roll libre adicional y escribe el manifiesto de tomas de la escena."""
    from .broll import (
        _buscar_candidatos_pexels, _buscar_candidatos_pixabay, _puntuar_y_filtrar_candidatos,
        analizar_calidad_visual_clip, descargar_archivo_directo, es_video_valido, obtener_duracion_video,
    )

    ct, rc = cfg_tomas(cfg), cfg_reales(cfg)
    carpeta = p.ruta("b_roll")
    sin_host = bool(p.datos.get("sin_host", False))
    previo = cargar_manifiesto(p, esc.id) or {}
    previas = {t.get("archivo"): t for t in previo.get("tomas", [])}
    tomas: list[dict[str, Any]] = []

    # 1. Clips reales (prioridad)
    # Si la escena abre con tarjeta (TOP #N o texto_pantalla, franja superior ~0-3.9 s), la primera toma real
    # va a pantalla completa y dura >= 4 s: así la tarjeta nunca cae encima de un panel EVIDENCIA.
    tiene_tarjeta = bool((getattr(esc, "texto_pantalla", "") or "").strip() or (getattr(esc, "puesto_titulo", "") or "").strip())
    fin_tarjeta = float(rc.get("fin_tarjeta_s", 4.0))
    for j, cf in enumerate(getattr(esc, "clips_fuente", []) or [], 1):
        d = max(float(rc["duracion_min_s"]), min(float(rc["duracion_max_s"]), float(cf.duracion or 4.0)))
        estilo = (getattr(cf, "estilo", "") or "evidencia").lower()
        if tiene_tarjeta and not tomas:
            estilo, d = "completo", max(d, min(float(rc["duracion_max_s"]), fin_tarjeta))
        final = carpeta / f"escena_{esc.id:03d}_real_{j:02d}.mp4"
        firma = f"{cf.url}|{cf.inicio}|{d}|{estilo}|{getattr(cf, 'recorte', None)}|{cf.resaltar}"
        info = {"archivo": final.name, "fuente": "real", "url": cf.url, "inicio": float(cf.inicio or 0.0),
                "duracion": d, "credito": cf.credito or "redes sociales", "estilo": estilo, "firma": firma}
        if final.exists() and es_video_valido(final) and previas.get(final.name, {}).get("firma") == firma:
            tomas.append(info)
            continue
        raw = carpeta / f"escena_{esc.id:03d}_real_{j:02d}_raw.mp4"
        ok, err = descargar_fragmento_real(cf.url, float(cf.inicio or 0.0), d, raw)
        if ok:
            ok = transformar_real(raw, final, d, cf.credito, cf.etiqueta or rc["etiqueta"], estilo,
                                  getattr(cf, "recorte", None), esc.pose, esc.host_lado,
                                  bool(esc.host_visible) and not sin_host, cf.resaltar, cfg)
            err = "" if ok else f"fallo al transformar ({estilo})"
        raw.unlink(missing_ok=True)
        if ok:
            print(f"      🎞️ Escena {esc.id}: clip real {j} listo ({d:.1f}s, {cf.credito or cf.url})")
            tomas.append(info)
            clips_usados.add(cf.url)
        else:
            print(f"      ⚠️ Escena {esc.id}: clip real {j} no disponible ({err})")
            rechazos_esc.append({"fuente": "real", "candidato": cf.url, "url": cf.url, "motivo": f"Descarga real fallida: {err}"})

    dur_reales = sum(t["duracion"] for t in tomas)
    cortes = planificar_cortes(dur_audio, float(ct["corte_min_s"]), float(ct["corte_max_s"]), [t["duracion"] for t in tomas])
    n_stock = max(0, len(cortes) - len(tomas))

    # 2. B-roll libre: clip principal + clips distintos adicionales
    principal = carpeta / f"escena_{esc.id:03d}.mp4"
    stock: list[dict] = []
    if principal.exists() and es_video_valido(principal):
        stock.append({"archivo": principal.name, "fuente": "stock", "url": url_principal})
    for nombre, t in previas.items():
        if t.get("fuente") == "stock" and nombre != principal.name and (carpeta / nombre).exists() and t.get("url"):
            if t["url"] not in clips_usados or t["url"] == url_principal:
                stock.append(t)
                clips_usados.add(t["url"])

    objetivo = min(n_stock, int(ct["max_clips_distintos_por_escena"]))
    if len(stock) < objetivo:
        queries = consultas_cortas(list(getattr(esc, "broll_queries_en", []) or []) or [esc.broll_query_en], esc.music_mood)
        cands = _buscar_candidatos_pixabay(queries[:4]) + _buscar_candidatos_pexels(queries[:3])
        puntuados = _puntuar_y_filtrar_candidatos(cands, esc, float(ct["corte_max_s"]), clips_usados, rechazos_log=rechazos_esc)
        k = len(stock) + 1
        for c in puntuados:
            if len(stock) >= objetivo:
                break
            if c["key"] in clips_usados or c["url"] in clips_usados or misma_serie(c["key"], clips_usados):
                continue
            destino = carpeta / f"escena_{esc.id:03d}_t{k:02d}.mp4"
            if not descargar_archivo_directo(c.get("url_medium") or c["url"], destino):
                continue
            ok, motivo, _met = analizar_calidad_visual_clip(destino, formato="16:9", min_yavg=float(rc.get("min_yavg_relleno", 35.0)), es_fuente_youtube=False)
            if not ok:
                destino.unlink(missing_ok=True)
                rechazos_esc.append({"fuente": c["fuente"], "candidato": c["key"], "url": c["url"], "motivo": f"Toma extra: {motivo}"})
                continue
            clips_usados.update({c["key"], c["url"]})
            stock.append({"archivo": destino.name, "fuente": "stock", "url": c["url"], "key": c["key"],
                          "consulta": c.get("query_origen", ""), "tags": c.get("tags", "")[:80]})
            k += 1

    for t in stock:
        t.setdefault("duracion_archivo", round(obtener_duracion_video(carpeta / t["archivo"]), 2))
    manifiesto = {"escena": esc.id, "duracion": round(dur_audio, 3), "cortes": cortes,
                  "tomas": tomas + stock, "segundos_reales": round(dur_reales, 2)}
    ruta_manifiesto(p, esc.id).write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2), "utf-8")
    return manifiesto


# ----------------------------------------------------------------------------- render
def planificar_segmentos(manifiesto: dict, duracion: float, cfg: Optional[dict] = None) -> list[dict]:
    """Asigna (archivo, offset, duración) a cada corte: reales primero, luego rotación de B-roll libre."""
    ct = cfg_tomas(cfg)
    tomas = manifiesto.get("tomas") or []
    reales = [t for t in tomas if t.get("fuente") == "real"]
    stock = [t for t in tomas if t.get("fuente") != "real"]
    cortes = planificar_cortes(duracion, float(ct["corte_min_s"]), float(ct["corte_max_s"]), [t["duracion"] for t in reales])
    segs: list[dict] = []
    usos: dict[str, int] = {}
    i_stock = 0
    for idx, c in enumerate(cortes):
        if idx < len(reales):
            segs.append({"archivo": reales[idx]["archivo"], "offset": 0.0, "dur": c, "fuente": "real"})
            continue
        if not stock:
            if reales:
                r = reales[idx % len(reales)]
                segs.append({"archivo": r["archivo"], "offset": 0.0, "dur": c, "fuente": "real"})
            continue
        t = stock[i_stock % len(stock)]
        i_stock += 1
        k = usos.get(t["archivo"], 0)
        usos[t["archivo"]] = k + 1
        dur_arch = float(t.get("duracion_archivo") or 0.0)
        hueco = max(0.0, dur_arch - c - 0.2)
        offset = ((0.5 + k * (c + 0.7)) % hueco) if hueco > 0.5 else 0.0
        segs.append({"archivo": t["archivo"], "offset": round(offset, 2), "dur": c, "fuente": "stock"})
    return segs


def montar_fondo_escena(p, esc, duracion: float, destino: Path, cfg: Optional[dict] = None) -> Optional[Path]:
    """Concatena las tomas planificadas en un fondo 1920x1080 de la duración exacta de la escena."""
    ct = cfg_tomas(cfg)
    if not ct.get("enabled", True):
        return None
    man = cargar_manifiesto(p, esc.id)
    if not man or not man.get("tomas"):
        return None
    segs = planificar_segmentos(man, duracion, cfg)
    carpeta = p.ruta("b_roll")
    segs = [s for s in segs if (carpeta / s["archivo"]).exists()]
    if not segs or (len(segs) == 1 and segs[0]["fuente"] != "real"):
        return None
    inputs: list[str] = []
    filtros: list[str] = []
    for i, s in enumerate(segs):
        inputs += ["-stream_loop", "-1", "-ss", f"{s['offset']:.2f}", "-i", str(carpeta / s["archivo"])]
        filtros.append(
            f"[{i}:v]scale={ANCHO}:{ALTO}:force_original_aspect_ratio=increase,crop={ANCHO}:{ALTO},setsar=1,fps=30,"
            f"format=yuv420p,trim=duration={s['dur']:.3f},setpts=PTS-STARTPTS[s{i}]"
        )
    filtros.append("".join(f"[s{i}]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=0[v]")
    destino.parent.mkdir(parents=True, exist_ok=True)
    ok = _run([_ffmpeg(), "-y", *inputs, "-filter_complex", ";".join(filtros), "-map", "[v]",
               "-t", f"{duracion:.2f}", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(destino)], timeout=900)
    if ok and destino.exists() and destino.stat().st_size > 1000:
        (destino.with_suffix(".json")).write_text(json.dumps(segs, ensure_ascii=False, indent=2), "utf-8")
        return destino
    return None
