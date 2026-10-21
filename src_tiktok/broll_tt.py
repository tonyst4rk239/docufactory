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

        # 1. PRIORIDAD 1: Fuentes con licencia segura (Pixabay vertical o HD recortable)
        candidatos_pix = _buscar_candidatos_pixabay_vertical(queries, clips_usados)
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
                print(f"      ✅ Clip 9:16 aprobado desde YouTube ({clave_yt})")

        # 3. PRIORIDAD 3: Fondo cinematográfico si ningún candidato aprobó
        if not exito:
            fuente_usada = "Fallback"
            detalle_clip = "fondo estilizado 9:16"
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
        })

    p.ruta("b_roll", "creditos.json").write_text(json.dumps(creditos, ensure_ascii=False, indent=2), "utf-8")
    ruta_rep = p.ruta("b_roll", "broll_reporte.md")
    generar_reporte_broll_md(ruta_rep, p.tema, "9:16", creditos, rechazos_por_escena)
    p.marcar("broll", "ok")
    print(f"✨ Clips 9:16 listos. Reporte de rechazos: {ruta_rep}")


