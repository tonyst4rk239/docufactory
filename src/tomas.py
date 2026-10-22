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


def transformar_evidencia(raw: Path, destino: Path, duracion: float, credito: str, etiqueta: str = "EVIDENCIA",
                          pose: str = "explicando", host_lado: str = "izquierda", host_visible: bool = True,
                          resaltar: Optional[list[float]] = None, cfg: Optional[dict] = None) -> bool:
    """Panel ~70 % sobre fondo desenfocado y oscurecido, zoom lento, etiqueta y 'Fuente: <credito>'."""
    rc = cfg_reales(cfg)
    cx, cy, pw, ph = geometria_panel(pose, host_lado, host_visible, float(rc["escala_panel"]))
    D = max(0.5, float(duracion))
    z = float(rc["zoom_lento"])
    fuente = config.FONTS_DIR / "bold.ttf"
    tmp = Path(tempfile.mkdtemp(prefix="ev_", dir=str(destino.parent)))
    try:
        (tmp / "etq.txt").write_text(f" {etiqueta.upper()} ", encoding="utf-8")
        (tmp / "cred.txt").write_text(f"Fuente: {credito or 'redes sociales'}", encoding="utf-8")
        from .broll import obtener_dimensiones_video
        try:
            iw, ih, _ = obtener_dimensiones_video(raw)
        except Exception:
            iw, ih = 1920, 1080
        iw, ih = (iw or 1920), (ih or 1080)
        esc_fit = min(pw / iw, ph / ih)
        qw, qh = max(2, int(iw * esc_fit) // 2 * 2), max(2, int(ih * esc_fit) // 2 * 2)
        pw, ph = qw, qh
        ff = f":fontfile='{_ruta_filtro(fuente)}'" if fuente.exists() else ""
        hl = ""
        if resaltar and len(resaltar) == 4:
            fx, fy, fw, fh = [max(0.0, min(1.0, float(v))) for v in resaltar]
            hl = f",drawbox=x=iw*{fx:.3f}:y=ih*{fy:.3f}:w=iw*{fw:.3f}:h=ih*{fh:.3f}:color=red@0.9:t=6"
        filtro = (
            f"[0:v]split[a][b];"
            f"[a]scale={ANCHO}:{ALTO}:force_original_aspect_ratio=increase,crop={ANCHO}:{ALTO},"
            f"boxblur={int(rc['desenfoque_fondo'])}:2,eq=brightness={float(rc['oscurecer_fondo']):.2f}:saturation=0.6,setsar=1[bg];"
            f"[b]scale={qw}:{qh},setsar=1,"
            f"scale=w='trunc({qw}*(1+{z}*t/{D:.2f})/2)*2':h='trunc({qh}*(1+{z}*t/{D:.2f})/2)*2':eval=frame,"
            f"crop={qw}:{qh}{hl},"
            f"drawbox=x=0:y=0:w=iw:h=ih:color=0xFFD400@0.95:t=6[pn];"
            f"[bg][pn]overlay=x={cx}-w/2:y={cy}-h/2:shortest=1,"
            f"drawtext=textfile='{_ruta_filtro(tmp / 'etq.txt')}'{ff}:fontsize=46:fontcolor=white:box=1:boxcolor=0xC81E1E@0.95:boxborderw=12:"
            f"x={cx}-{pw}/2:y={cy}-{ph}/2-78,"
            f"drawtext=textfile='{_ruta_filtro(tmp / 'cred.txt')}'{ff}:fontsize=34:fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=10:"
            f"x={cx}-text_w/2:y={cy}+{ph}/2+26,"
            f"fps=30,format=yuv420p[v]"
        )
        ok = _run([_ffmpeg(), "-y", "-stream_loop", "-1", "-i", str(raw), "-filter_complex", filtro,
                   "-map", "[v]", "-t", f"{D:.2f}", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(destino)])
        return ok and destino.exists() and destino.stat().st_size > 1000
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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
    for j, cf in enumerate(getattr(esc, "clips_fuente", []) or [], 1):
        d = max(float(rc["duracion_min_s"]), min(float(rc["duracion_max_s"]), float(cf.duracion or 4.0)))
        final = carpeta / f"escena_{esc.id:03d}_real_{j:02d}.mp4"
        info = {"archivo": final.name, "fuente": "real", "url": cf.url, "inicio": float(cf.inicio or 0.0),
                "duracion": d, "credito": cf.credito or "redes sociales"}
        if final.exists() and es_video_valido(final) and previas.get(final.name, {}).get("url") == cf.url:
            tomas.append(info)
            continue
        raw = carpeta / f"escena_{esc.id:03d}_real_{j:02d}_raw.mp4"
        ok, err = descargar_fragmento_real(cf.url, float(cf.inicio or 0.0), d, raw)
        if ok:
            ok = transformar_evidencia(raw, final, d, cf.credito, cf.etiqueta or rc["etiqueta"], esc.pose,
                                       esc.host_lado, bool(esc.host_visible) and not sin_host, cf.resaltar, cfg)
            err = "" if ok else "fallo al transformar panel EVIDENCIA"
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
            ok, motivo, _met = analizar_calidad_visual_clip(destino, formato="16:9", min_yavg=25.0, es_fuente_youtube=False)
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
