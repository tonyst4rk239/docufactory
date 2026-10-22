"""Descargador de B-Roll vertical (9:16) con prioridad de licencia segura, filtro anti-Content ID y análisis FFmpeg."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
import requests
import urllib3

from src import config
from src.broll import (
    HTTP_HEADERS,
    analizar_calidad_visual_clip,
    descargar_archivo_directo,
    descargar_clip_youtube,
    es_video_valido,
    generar_reporte_broll_md,
    obtener_duracion_video,
    youtube_disponible,
)
from src.estado import Proyecto
from src_tiktok.guion_tt import GuionTikTok

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _buscar_candidatos_pixabay_vertical(queries: list[str], clips_usados: set[str]) -> list[dict]:
    """Busca candidatos en Pixabay priorizando orientación vertical y HD recortable."""
    if not config.PIXABAY_API_KEY:
        return []
    url = "https://pixabay.com/api/videos/"
    candidatos: list[dict] = []
    vistos: set[str] = set()

    intentos: list[tuple[str, str]] = []
    for q in queries[:3]:
        intentos.append((q, "vertical"))
        intentos.append((q, "all"))
    intentos.append(("dark cinematic night", "vertical"))
    intentos.append(("dark mysterious shadow", "all"))

    for q_int, orient in intentos:
        params = {
            "key": config.PIXABAY_API_KEY,
            "q": q_int,
            "orientation": orient,
            "per_page": 6,
        }
        try:
            r = requests.get(url, params=params, headers=HTTP_HEADERS, verify=False, timeout=10)
            if not r.ok:
                continue
            for h in r.json().get("hits", []):
                vid_id = str(h.get("id", ""))
                key = f"pixabay:{vid_id}"
                if not vid_id or vid_id in vistos or key in clips_usados:
                    continue
                vids = h.get("videos", {})
                opt = vids.get("large") or vids.get("medium") or vids.get("small")
                if not opt or not opt.get("url"):
                    continue
                vistos.add(vid_id)
                candidatos.append({
                    "fuente": "Pixabay",
                    "key": key,
                    "url": opt["url"],
                    "tags": str(h.get("tags") or ""),
                    "duracion": float(h.get("duration") or 0.0),
                    "orientacion": orient,
                })
        except Exception:
            continue
    return candidatos


# ----------------------------------------------------------------------------- clips reales 9:16
CORTE_REAL_MAX_S = 3.0   # cortes cortos para retención
CORTE_REAL_MIN_S = 1.5


def _firma_reales(esc) -> str:
    import hashlib
    datos = json.dumps(list(getattr(esc, "clips_fuente", []) or []), sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(f"v1|{datos}".encode("utf-8")).hexdigest()


def _vertical_real(raw: Path, destino: Path, dur: float, credito: str) -> bool:
    """Lleva un fragmento real a 1080x1920: fondo desenfocado + clip completo arriba del centro y crédito
    en la franja superior (lejos del karaoke central y del avatar en la esquina inferior)."""
    from src.tomas import _ruta_filtro
    ffmpeg = config.ffmpeg_bin("ffmpeg") or "ffmpeg"
    destino.parent.mkdir(parents=True, exist_ok=True)
    txt = destino.with_suffix(".cred.txt")
    txt.write_text(f"Fuente: {credito or 'redes sociales'}"[:60], encoding="utf-8")
    fuente = config.FONTS_DIR / "bold.ttf"
    ff = f":fontfile='{_ruta_filtro(fuente)}'" if fuente.exists() else ""
    filtro = (
        "[0:v]split[a][b];"
        "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:2,eq=brightness=-0.18[bg];"
        "[b]scale=1080:1500:force_original_aspect_ratio=decrease[fg];"
        "[bg][fg]overlay=(W-w)/2:max(170\\,(H-h)/2-160),"
        f"drawtext=textfile='{_ruta_filtro(txt)}'{ff}:fontsize=34:fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=10:x=(w-tw)/2:y=90,"
        "fps=30,setsar=1,format=yuv420p[v]"
    )
    cmd = [ffmpeg, "-y", "-i", str(raw), "-filter_complex", filtro, "-map", "[v]", "-t", f"{dur:.2f}",
           "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(destino)]
    try:
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=300)
        return r.returncode == 0 and es_video_valido(destino)
    finally:
        txt.unlink(missing_ok=True)


def _concatenar(partes: list[Path], destino: Path) -> bool:
    ffmpeg = config.ffmpeg_bin("ffmpeg") or "ffmpeg"
    lista = destino.with_suffix(".concat.txt")
    lista.write_text("\n".join(f"file '{x.resolve().as_posix()}'" for x in partes), encoding="utf-8")
    cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(lista), "-an",
           "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,setsar=1,format=yuv420p",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(destino)]
    try:
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=600)
        return r.returncode == 0 and es_video_valido(destino)
    finally:
        lista.unlink(missing_ok=True)


def _preparar_reales_escena(carpeta: Path, esc, rechazos_esc: list[dict], dur_objetivo: float = 0.0) -> list[dict]:
    """Descarga (yt-dlp, solo el rango) cada clip_fuente y lo corta en tomas cortas 9:16."""
    from src.tomas import descargar_fragmento_real
    tomas: list[dict] = []
    for j, cf in enumerate(getattr(esc, "clips_fuente", []) or [], 1):
        if dur_objetivo and sum(t["duracion"] for t in tomas) >= dur_objetivo + 0.5:
            break  # ya cubre la narración: no descargar de más
        url = str(cf.get("url") or "").strip()
        if not url:
            continue
        ini = float(cf.get("inicio") or 0.0)
        d = max(CORTE_REAL_MIN_S, min(6.0, float(cf.get("duracion") or 4.0)))
        raw = carpeta / f"escena_{esc.id:03d}_real_{j:02d}_raw.mp4"
        ok, err = descargar_fragmento_real(url, ini, d, raw)
        if not ok:
            print(f"      ⚠️ Escena {esc.id}: clip real {j} no disponible ({err})")
            rechazos_esc.append({"fuente": "real", "candidato": url, "url": url, "motivo": f"Descarga real fallida: {err}"})
            raw.unlink(missing_ok=True)
            continue
        # Un fragmento largo se parte en cortes de <= 3 s (cada corte = una toma)
        n = max(1, int(round(d / CORTE_REAL_MAX_S + 0.49)))
        dur_corte = d / n
        for k in range(n):
            final = carpeta / f"escena_{esc.id:03d}_real_{j:02d}_{k + 1}.mp4"
            sub = raw.with_name(raw.stem + f"_{k}.mp4")
            ffmpeg = config.ffmpeg_bin("ffmpeg") or "ffmpeg"
            r = subprocess.run([ffmpeg, "-y", "-ss", f"{k * dur_corte:.2f}", "-i", str(raw), "-t", f"{dur_corte:.2f}",
                                "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(sub)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if r.returncode == 0 and es_video_valido(sub) and _vertical_real(sub, final, dur_corte, str(cf.get("credito") or "")):
                tomas.append({"archivo": final.name, "fuente": "real", "url": url, "inicio": ini + k * dur_corte,
                              "duracion": dur_corte, "credito": cf.get("credito") or "redes sociales"})
            sub.unlink(missing_ok=True)
        raw.unlink(missing_ok=True)
        print(f"      🎞️ Escena {esc.id}: clip real {j} listo ({d:.1f}s en {n} corte(s), {cf.get('credito') or url})")
    return tomas


def etapa_broll_tiktok(p: Proyecto, guion: GuionTikTok, duraciones: dict[int, float]):
    carpeta_broll = p.ruta("b_roll")
    carpeta_broll.mkdir(parents=True, exist_ok=True)
    total = len(guion.escenas)
    creditos: list[dict] = []
    rechazos_por_escena: dict[int, list[dict]] = {}
    clips_usados: set[str] = set()

    print(f"🎬 Curando B-roll vertical (9:16) para {total} micro-escenas (licencia segura + filtro FFmpeg YAVG/texto)...")

    for i, esc in enumerate(guion.escenas, 1):
        destino = carpeta_broll / f"escena_{esc.id:03d}.mp4"
        rechazos_esc: list[dict] = []
        rechazos_por_escena[esc.id] = rechazos_esc

        man_reales = carpeta_broll / f"escena_{esc.id:03d}_reales.json"
        firma = _firma_reales(esc)
        tiene_reales = bool(getattr(esc, "clips_fuente", None))
        if destino.exists() and tiene_reales:
            try:
                previo = json.loads(man_reales.read_text(encoding="utf-8"))
            except Exception:
                previo = {}
            if previo.get("firma") != firma:
                destino.unlink(missing_ok=True)
        if destino.exists():
            aprobado_c, motivo_c, met_c = analizar_calidad_visual_clip(destino, formato="9:16", min_yavg=25.0)
            if aprobado_c:
                t_vid = obtener_duracion_video(destino)
                print(f"   [{i}/{total}] Clip en caché válido para Escena {esc.id}: {destino.name} (YAVG={met_c.get('yavg')})")
                creditos.append({
                    "escena": esc.id,
                    "archivo": destino.name,
                    "fuente": "Cache",
                    "detalle": f"YAVG={met_c.get('yavg')}, res={met_c.get('width')}x{met_c.get('height')}",
                    "duracion_video": t_vid,
                })
                continue
            else:
                rechazos_esc.append({
                    "fuente": "Cache",
                    "candidato": destino.name,
                    "url": "",
                    "motivo": f"Caché invalidado: {motivo_c}",
                })
                destino.unlink(missing_ok=True)

        queries = list(getattr(esc, "broll_queries_en", []) or [])
        if esc.broll_query_en and esc.broll_query_en.strip() not in queries:
            queries.insert(0, esc.broll_query_en.strip())
        if not queries:
            queries = ["dark mysterious night"]

        query_principal = queries[0]
        dur_pedida = max(5, int(duraciones.get(esc.id, 3.0)) + 3)
        print(f"   [{i}/{total}] Escena {esc.id}: Buscando clip 9:16 para '{query_principal}'...")

        exito = False
        fuente_usada = "Fallback"
        detalle_clip = ""
        url_usada = ""

        # 0. PRIORIDAD 0: clips reales del guion (clips_fuente) con cortes cortos; stock solo de relleno
        tomas_reales = _preparar_reales_escena(carpeta_broll, esc, rechazos_esc, float(duraciones.get(esc.id, 0.0))) if tiene_reales else []
        dur_audio = float(duraciones.get(esc.id, 3.0))
        dur_reales = sum(t["duracion"] for t in tomas_reales)
        if tomas_reales:
            partes = [carpeta_broll / t["archivo"] for t in tomas_reales]
            relleno = None
            if dur_reales < dur_audio:
                relleno = carpeta_broll / f"escena_{esc.id:03d}_relleno.mp4"
                for cand in _buscar_candidatos_pixabay_vertical(queries, clips_usados):
                    if descargar_archivo_directo(cand["url"], relleno):
                        ok_r, _m, _x = analizar_calidad_visual_clip(relleno, formato="9:16", min_yavg=25.0, es_fuente_youtube=False)
                        if ok_r:
                            clips_usados.update({cand["key"], cand["url"]})
                            break
                    relleno.unlink(missing_ok=True)
                if relleno.exists():
                    corto = carpeta_broll / f"escena_{esc.id:03d}_relleno_corte.mp4"
                    ffm = config.ffmpeg_bin("ffmpeg") or "ffmpeg"
                    subprocess.run([ffm, "-y", "-stream_loop", "-1", "-i", str(relleno), "-t", f"{dur_audio - dur_reales + 0.5:.2f}",
                                    "-an", "-c:v", "libx264", "-preset", "veryfast", str(corto)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if es_video_valido(corto):
                        partes.append(corto)
            if _concatenar(partes, destino):
                exito = True
                fuente_usada = "Real (clips_fuente)"
                creds = sorted({str(t["credito"]) for t in tomas_reales})
                detalle_clip = f"{len(tomas_reales)} tomas reales ({dur_reales:.1f}s): {', '.join(creds)}"
                url_usada = tomas_reales[0]["url"]
                man_reales.write_text(json.dumps({"firma": firma, "tomas": tomas_reales,
                                                  "relleno_stock": len(partes) > len(tomas_reales)},
                                                 ensure_ascii=False, indent=2), "utf-8")
                print(f"      ✅ Escena {esc.id}: {len(tomas_reales)} tomas reales + {'relleno stock' if len(partes) > len(tomas_reales) else 'sin relleno'}")
            for x in partes:
                if x != destino:
                    x.unlink(missing_ok=True)
            if relleno is not None:
                relleno.unlink(missing_ok=True)

        # 1. PRIORIDAD 1: Fuentes con licencia segura (Pixabay vertical o HD recortable)
        candidatos_pix = [] if exito else _buscar_candidatos_pixabay_vertical(queries, clips_usados)
        for cand in candidatos_pix:
            if descargar_archivo_directo(cand["url"], destino):
                aprobado_st, motivo_st, met_st = analizar_calidad_visual_clip(
                    destino, formato="9:16", min_yavg=25.0, es_fuente_youtube=False
                )
                if aprobado_st:
                    exito = True
                    fuente_usada = "Pixabay (Licencia Segura)"
                    detalle_clip = (
                        f"{cand['key']} (YAVG={met_st.get('yavg')}, "
                        f"res={met_st.get('width')}x{met_st.get('height')}, tags='{cand['tags'][:45]}')"
                    )
                    clips_usados.add(cand["key"])
                    clips_usados.add(cand["url"])
                    url_usada = cand["url"]
                    print(f"      ✅ Clip 9:16 aprobado desde Pixabay [{cand['key']}] (YAVG={met_st.get('yavg')})")
                    break
                else:
                    destino.unlink(missing_ok=True)
                    rechazos_esc.append({
                        "fuente": "Pixabay",
                        "candidato": cand["key"],
                        "url": cand["url"],
                        "motivo": f"Post-descarga FFmpeg: {motivo_st}",
                    })

        # 2. PRIORIDAD 2: YouTube Creative Commons / archivo limpio (sin Shorts ni compilaciones)
        if not exito and youtube_disponible():
            clave_yt = descargar_clip_youtube(
                query_principal,
                destino,
                inicio_s=6,
                duracion_s=dur_pedida,
                clips_usados=clips_usados,
                formato="9:16",
                rechazos_log=rechazos_esc,
            )
            if clave_yt:
                exito = True
                fuente_usada = "YouTube"
                detalle_clip = clave_yt
                import re as _re_tt
                m_yt_id = _re_tt.search(r"yt:([A-Za-z0-9_-]{11})", clave_yt)
                url_usada = f"https://www.youtube.com/watch?v={m_yt_id.group(1)}" if m_yt_id else clave_yt
                print(f"      ✅ Clip 9:16 aprobado desde YouTube ({clave_yt})")

        # 3. PRIORIDAD 3: Fondo cinematográfico si ningún candidato aprobó
        if not exito:
            fuente_usada = "Fallback"
            detalle_clip = "fondo estilizado 9:16"
            url_usada = "lavfi:color:9:16"
            print(f"      ⚠️ Generando fondo cinematográfico 9:16 para escena {esc.id}...")
            ffmpeg = config.ffmpeg_bin("ffmpeg") or "ffmpeg"
            cmd_emergencia = [
                ffmpeg, "-y",
                "-f", "lavfi", "-i", "color=c=0x1e2538:s=1080x1920:r=30",
                "-t", f"{dur_pedida:.2f}",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-an", str(destino)
            ]
            try:
                subprocess.run(cmd_emergencia, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                exito = es_video_valido(destino)
            except Exception:
                pass

        t_vid = obtener_duracion_video(destino) if exito else 0.0
        creditos.append({
            "escena": esc.id,
            "archivo": destino.name if exito else None,
            "fuente": fuente_usada,
            "credito": f"{fuente_usada}: {detalle_clip}",
            "detalle": detalle_clip,
            "duracion_video": t_vid,
            "url": url_usada,
            "consultas_usadas": queries,
        })

    p.ruta("b_roll", "creditos.json").write_text(json.dumps(creditos, ensure_ascii=False, indent=2), "utf-8")
    ruta_rep = p.ruta("b_roll", "broll_reporte.md")
    generar_reporte_broll_md(ruta_rep, p.tema, "9:16", creditos, rechazos_por_escena)
    p.marcar("broll", "ok")
    print(f"✨ Clips 9:16 listos. Reporte de rechazos: {ruta_rep}")


