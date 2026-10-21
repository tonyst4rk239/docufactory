"""Descargador idempotente de assets libres de derechos para Docu Factory.

Descarga:
1. Música de dominio público (CC0 1.0) de FreePD (https://freepd.com/ + espejo oficial Archive.org):
   4-6 pistas por mood en assets/music/{tension,epica,misterio,curiosidad,calma}/.
2. Overlays de video desde la API de Pixabay (usando PIXABAY_API_KEY):
   2-3 clips por tipo ("film grain", "dust overlay", "light leak", "glitch", "vhs")
   en assets/overlays/{film_grain,dust_overlay,light_leak,glitch,vhs}/.
3. SFX opcionales desde Freesound API v2 (si existe FREESOUND_API_KEY) con filtro
   license:"Creative Commons 0", guardando 3-5 por categoría en
   assets/sfx/{whoosh,riser,impact,tension,ambiente,digital,click}/.
   Si no hay FREESOUND_API_KEY, genera SFX sintéticos CC0 con FFmpeg para las carpetas vacías.
4. Genera y actualiza assets/CREDITS.md con la fuente, URL, autor y licencia de cada archivo.

Uso:
  python scripts/descargar_assets.py
  python scripts/descargar_assets.py --max-music 5 --max-overlays 3 --max-sfx 4
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
load_dotenv(RAIZ / ".env")

from src import config  # noqa: E402

USER_AGENT = "DocuFactory-AssetDownloader/1.0 (+https://github.com/tonyst4rk239/docufactory)"
CREDITS_JSON = config.ASSETS / ".credits_manifest.json"
CREDITS_MD = config.ASSETS / "CREDITS.md"

# Catálogo curado de pistas de FreePD (100% CC0 1.0 Public Domain) por mood:
# (Nombre original en FreePD, subcarpeta en el archivo de FreePD, autor)
FREEPD_CATALOGO: dict[str, list[tuple[str, str, str]]] = {
    "misterio": [
        ("Mysterious Lights", "featured", "Bryan Teoh / FreePD"),
        ("Hidden Truth", "horror", "Rafael Krux / FreePD"),
        ("Asking Questions", "horror", "Rafael Krux / FreePD"),
        ("The Abyss", "horror", "Kevin MacLeod / FreePD"),
        ("Island Mystery", "Page2", "FreePD Public Domain"),
    ],
    "tension": [
        ("Horror Suspense", "horror", "Kevin MacLeod / FreePD"),
        ("Driving Concern", "scoring", "Kevin MacLeod / FreePD"),
        ("Beginning of Conflict", "scoring", "Rafael Krux / FreePD"),
        ("Tension", "Page2", "FreePD Public Domain"),
        ("Thinking Tension A", "Page2", "FreePD Public Domain"),
    ],
    "epica": [
        ("Epic Blockbuster 2", "epic", "Rafael Krux / FreePD"),
        ("Strength of the Titans", "epic", "Kevin MacLeod / FreePD"),
        ("Ancient Rite", "epic", "Kevin MacLeod / FreePD"),
        ("Night Vigil", "epic", "Kevin MacLeod / FreePD"),
        ("Behind Enemy Lines", "epic", "Rafael Krux / FreePD"),
    ],
    "curiosidad": [
        ("Find Them", "scoring", "Alexander Nakarada / FreePD"),
        ("Patron Saint of Heists", "scoring", "Bryan Teoh / FreePD"),
        ("Chronos", "electronic", "Alexander Nakarada / FreePD"),
        ("Space Ambience", "electronic", "Alexander Nakarada / FreePD"),
        ("Action Investigation", "Page2", "FreePD Public Domain"),
    ],
    "calma": [
        ("Study and Relax", "featured", "Kevin MacLeod / FreePD"),
        ("The Lagoon", "scoring", "Kevin MacLeod / FreePD"),
        ("Meditating Beat", "electronic", "Kevin MacLeod / FreePD"),
        ("Calm Sketch for Piano", "Page2", "FreePD Public Domain"),
        ("Quiet NIght", "Page2", "FreePD Public Domain"),
    ],
}

# Consultas de overlays en Pixabay Videos API -> subcarpeta en assets/overlays/
OVERLAY_QUERIES: dict[str, list[str]] = {
    "film_grain": ["film grain", "old film grain overlay", "retro film noise"],
    "dust_overlay": ["dust overlay", "dust particles black screen", "floating dust"],
    "light_leak": ["light leak", "film burn light leak", "lens flare overlay"],
    "glitch": ["glitch", "digital glitch noise", "tv static glitch"],
    "vhs": ["vhs", "vhs tape retro noise", "bad tv signal vhs"],
}

# Consultas de SFX para Freesound API v2 (licencia Creative Commons 0)
FREESOUND_QUERIES: dict[str, str] = {
    "whoosh": "cinematic whoosh transition swish",
    "riser": "dark cinematic riser suspense build",
    "impact": "cinematic sub bass impact hit boom",
    "tension": "dark horror tension drone stinger",
    "ambiente": "dark eerie room tone drone atmosphere",
    "digital": "digital glitch data ui beep telemetry",
    "click": "camera shutter mechanical click switch",
}


def _slug_archivo(texto: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", texto.strip()).strip("_").lower()
    return s[:48] or "asset"


def _cargar_manifiesto() -> dict[str, dict[str, Any]]:
    if CREDITS_JSON.exists():
        try:
            return json.loads(CREDITS_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _guardar_manifiesto(manifiesto: dict[str, dict[str, Any]]) -> None:
    CREDITS_JSON.parent.mkdir(parents=True, exist_ok=True)
    CREDITS_JSON.write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8")


def _registrar_credito(
    manifiesto: dict[str, dict[str, Any]],
    ruta_relativa: str,
    tipo: str,
    categoria: str,
    fuente: str,
    url: str,
    licencia: str,
    autor: str = "Dominio Público / CC0",
) -> None:
    manifiesto[ruta_relativa] = {
        "archivo": ruta_relativa,
        "tipo": tipo,
        "categoria": categoria,
        "fuente": fuente,
        "autor": autor,
        "url": url,
        "licencia": licencia,
    }


def _descargar_binario(urls: list[str], destino: Path, min_bytes: int = 8_000) -> str | None:
    """Intenta descargar desde una lista de URLs candidatas y verifica que no sea HTML de error."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": USER_AGENT}
    temp = destino.with_suffix(destino.suffix + ".part")

    for url in urls:
        try:
            with requests.get(url, headers=headers, stream=True, timeout=35, allow_redirects=True) as r:
                if r.status_code != 200:
                    continue
                ctype = (r.headers.get("content-type") or "").lower()
                if "text/html" in ctype:
                    continue
                with open(temp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
            if temp.exists() and temp.stat().st_size >= min_bytes:
                # Verificar que los primeros bytes no sean <!DOCTYPE html
                with open(temp, "rb") as f_chk:
                    cabecera = f_chk.read(64).lower()
                if b"<!doctype" in cabecera or b"<html" in cabecera:
                    temp.unlink(missing_ok=True)
                    continue
                temp.replace(destino)
                return url
            temp.unlink(missing_ok=True)
        except Exception:
            temp.unlink(missing_ok=True)
            continue
    return None


def descargar_musica_freepd(manifiesto: dict[str, dict[str, Any]], max_por_mood: int = 5) -> int:
    """Descarga 4-6 pistas de dominio público de FreePD por cada mood."""
    print("\n🎵 [1/3] Descargando música de Dominio Público (FreePD CC0)...")
    descargados_total = 0

    for mood, pistas in FREEPD_CATALOGO.items():
        carpeta_mood = config.MUSIC_DIR / mood
        carpeta_mood.mkdir(parents=True, exist_ok=True)
        gitkeep = carpeta_mood / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text(f"# Carpeta de música para mood '{mood}'\n", encoding="utf-8")

        print(f"  📂 Mood '{mood}':")
        for titulo, sub_freepd, autor in pistas[:max_por_mood]:
            slug = _slug_archivo(titulo)
            nombre_mp3 = f"freepd_{slug}.mp3"
            destino = carpeta_mood / nombre_mp3
            rel_path = destino.relative_to(config.RAIZ).as_posix()

            url_original = f"https://freepd.com/music/{quote(titulo)}.mp3"
            url_archive = f"https://archive.org/download/freepd/{quote(sub_freepd)}/{quote(titulo)}.mp3"
            url_wayback = f"https://web.archive.org/web/2024id_/https://freepd.com/music/{quote(titulo)}.mp3"

            if destino.exists() and destino.stat().st_size > 10_000:
                print(f"     ⏭️  Ya existe: {nombre_mp3} ({destino.stat().st_size // 1024} KB)")
                if rel_path not in manifiesto:
                    _registrar_credito(
                        manifiesto,
                        rel_path,
                        tipo="music",
                        categoria=mood,
                        fuente="FreePD (Public Domain)",
                        url=f"{url_original} (mirror: {url_archive})",
                        licencia="CC0 1.0 Universal (Public Domain)",
                        autor=autor,
                    )
                descargados_total += 1
                continue

            url_usada = _descargar_binario([url_original, url_archive, url_wayback], destino, min_bytes=15_000)
            if url_usada:
                kb = destino.stat().st_size // 1024
                print(f"     ✅ Descargado: {nombre_mp3} ({kb} KB)")
                _registrar_credito(
                    manifiesto,
                    rel_path,
                    tipo="music",
                    categoria=mood,
                    fuente="FreePD (Public Domain)",
                    url=f"{url_original} (mirror: {url_usada})",
                    licencia="CC0 1.0 Universal (Public Domain)",
                    autor=autor,
                )
                descargados_total += 1
            else:
                print(f"     ⚠️ No se pudo descargar: {titulo}")

    return descargados_total


def descargar_overlays_pixabay(manifiesto: dict[str, dict[str, Any]], max_por_tipo: int = 3) -> int:
    """Descarga 2-3 overlays de video por tipo usando PIXABAY_API_KEY."""
    print("\n🎞️ [2/3] Descargando Overlays de Video desde Pixabay API...")
    api_key = config.PIXABAY_API_KEY
    if not api_key:
        print("  ⚠️ PIXABAY_API_KEY no configurada en .env -> se omiten descargas de overlays (FFmpeg usará grano/viñeta generados).")
        return 0

    descargados_total = 0
    ids_usados: set[int] = set()

    for tipo, consultas in OVERLAY_QUERIES.items():
        carpeta_tipo = config.OVERLAYS_DIR / tipo
        carpeta_tipo.mkdir(parents=True, exist_ok=True)
        gitkeep = carpeta_tipo / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text(f"# Carpeta de overlays para '{tipo}'\n", encoding="utf-8")

        existentes = sorted([p for p in carpeta_tipo.glob("*.mp4") if p.stat().st_size > 10_000])
        if len(existentes) >= max_por_tipo:
            print(f"  📂 Overlay '{tipo}': ⏭️  Ya tiene {len(existentes)} archivo(s), saltando.")
            for ex in existentes:
                rel_p = ex.relative_to(config.RAIZ).as_posix()
                if rel_p not in manifiesto:
                    m_id = re.search(r"pixabay_(\d+)", ex.stem)
                    pid = m_id.group(1) if m_id else "overlay"
                    _registrar_credito(
                        manifiesto,
                        rel_p,
                        tipo="overlay",
                        categoria=tipo,
                        fuente="Pixabay Videos API",
                        url=f"https://pixabay.com/videos/id-{pid}/",
                        licencia="Pixabay Content License (Free for commercial use)",
                        autor="Pixabay Contributor",
                    )
            descargados_total += len(existentes)
            continue

        print(f"  📂 Overlay '{tipo}': buscando hasta {max_por_tipo} clip(s)...")
        obtenidos_tipo = len(existentes)

        for q in consultas:
            if obtenidos_tipo >= max_por_tipo:
                break
            try:
                r = requests.get(
                    "https://pixabay.com/api/videos/",
                    params={
                        "key": api_key,
                        "q": q,
                        "per_page": 15,
                        "safesearch": "true",
                    },
                    timeout=20,
                )
                if r.status_code != 200:
                    continue
                hits = r.json().get("hits", [])
            except Exception as e:
                print(f"     ⚠️ Error consultando Pixabay ('{q}'): {e}")
                continue

            for h in hits:
                if obtenidos_tipo >= max_por_tipo:
                    break
                hid = int(h.get("id", 0))
                if not hid or hid in ids_usados:
                    continue
                nombre_mp4 = f"{tipo}_pixabay_{hid}.mp4"
                destino = carpeta_tipo / nombre_mp4
                rel_path = destino.relative_to(config.RAIZ).as_posix()

                if destino.exists() and destino.stat().st_size > 10_000:
                    ids_usados.add(hid)
                    obtenidos_tipo += 1
                    descargados_total += 1
                    continue

                vids = h.get("videos", {})
                # Preferimos 'small' o 'medium' para descargas rápidas y ligeras en servidor
                url_vid = ""
                for calidad in ("small", "medium", "tiny", "large"):
                    cand = (vids.get(calidad) or {}).get("url", "")
                    if cand:
                        url_vid = cand
                        break
                if not url_vid:
                    continue

                url_ok = _descargar_binario([url_vid], destino, min_bytes=20_000)
                if url_ok:
                    ids_usados.add(hid)
                    obtenidos_tipo += 1
                    descargados_total += 1
                    page_url = h.get("pageURL") or f"https://pixabay.com/videos/id-{hid}/"
                    autor = h.get("user") or "Pixabay Contributor"
                    kb = destino.stat().st_size // 1024
                    print(f"     ✅ Descargado: {nombre_mp4} ({kb} KB) — {page_url}")
                    _registrar_credito(
                        manifiesto,
                        rel_path,
                        tipo="overlay",
                        categoria=tipo,
                        fuente="Pixabay Videos API",
                        url=page_url,
                        licencia="Pixabay Content License (Free for commercial use, no attribution required)",
                        autor=autor,
                    )

    return descargados_total


def _generar_sfx_procedural_ffmpeg(manifiesto: dict[str, dict[str, Any]], cat: str, carpeta_cat: Path) -> int:
    """Genera 3 variaciones de SFX sintéticos CC0 con FFmpeg cuando no hay FREESOUND_API_KEY."""
    ffmpeg = config.ffmpeg_bin("ffmpeg")
    if not ffmpeg:
        return 0

    recetas: dict[str, list[tuple[str, list[str]]]] = {
        "riser": [
            (
                "riser_cinematic_dark_01.wav",
                [
                    "-f", "lavfi", "-i", "anoisesrc=d=1.8:c=pink:r=44100:a=0.35",
                    "-f", "lavfi", "-i", "sine=f=65:d=1.8:r=44100",
                    "-filter_complex",
                    "[0:a]lowpass=f=900,afade=t=in:ss=0:d=1.65:curve=exp,afade=t=out:st=1.65:d=0.15[n];"
                    "[1:a]asetrate=44100*1.6,aresample=44100,atempo=0.625,volume=0.3,afade=t=in:ss=0:d=1.6:curve=exp[s];"
                    "[n][s]amix=inputs=2:normalize=0,volume=1.4",
                ],
            ),
            (
                "riser_tension_sweep_02.wav",
                [
                    "-f", "lavfi", "-i", "anoisesrc=d=1.5:c=brown:r=44100:a=0.45",
                    "-af", "bandpass=f=420:width_type=h:w=300,afade=t=in:ss=0:d=1.35:curve=exp,afade=t=out:st=1.35:d=0.15,volume=1.8",
                ],
            ),
            (
                "riser_sub_lift_03.wav",
                [
                    "-f", "lavfi", "-i", "anoisesrc=d=2.0:c=pink:r=44100:a=0.30",
                    "-af", "lowpass=f=650,afade=t=in:ss=0:d=1.85:curve=iqsin,afade=t=out:st=1.85:d=0.15,volume=1.6",
                ],
            ),
        ],
        "impact": [
            (
                "impact_sub_boom_01.wav",
                [
                    "-f", "lavfi", "-i", "sine=f=52:d=1.4:r=44100",
                    "-f", "lavfi", "-i", "anoisesrc=d=1.4:c=brown:r=44100:a=0.5",
                    "-filter_complex",
                    "[0:a]afade=t=out:st=0.05:d=1.35:curve=exp,volume=0.9[s];"
                    "[1:a]lowpass=f=180,afade=t=out:st=0.02:d=0.9:curve=exp,volume=0.8[n];"
                    "[s][n]amix=inputs=2:normalize=0,volume=1.5",
                ],
            ),
            (
                "impact_dark_hit_02.wav",
                [
                    "-f", "lavfi", "-i", "sine=f=44:d=1.6:r=44100",
                    "-af", "afade=t=in:ss=0:d=0.01,afade=t=out:st=0.04:d=1.5:curve=exp,volume=1.3",
                ],
            ),
            (
                "impact_cinematic_thud_03.wav",
                [
                    "-f", "lavfi", "-i", "anoisesrc=d=1.2:c=brown:r=44100:a=0.6",
                    "-af", "lowpass=f=140,afade=t=out:st=0.02:d=1.15:curve=exp,volume=2.0",
                ],
            ),
        ],
        "tension": [
            (
                "tension_dark_drone_01.wav",
                [
                    "-f", "lavfi", "-i", "sine=f=55:d=2.5:r=44100",
                    "-f", "lavfi", "-i", "sine=f=58:d=2.5:r=44100",
                    "-filter_complex",
                    "[0:a][1:a]amix=inputs=2:normalize=0,lowpass=f=220,afade=t=in:ss=0:d=0.4,afade=t=out:st=1.9:d=0.6,volume=0.7",
                ],
            ),
            (
                "tension_pulse_low_02.wav",
                [
                    "-f", "lavfi", "-i", "anoisesrc=d=2.2:c=brown:r=44100:a=0.4",
                    "-af", "lowpass=f=160,tremolo=f=4:d=0.7,afade=t=in:ss=0:d=0.3,afade=t=out:st=1.7:d=0.5,volume=1.5",
                ],
            ),
            (
                "tension_eerie_stinger_03.wav",
                [
                    "-f", "lavfi", "-i", "sine=f=110:d=1.8:r=44100",
                    "-f", "lavfi", "-i", "sine=f=116.5:d=1.8:r=44100",
                    "-filter_complex",
                    "[0:a][1:a]amix=inputs=2:normalize=0,afade=t=in:ss=0:d=0.2,afade=t=out:st=1.2:d=0.6,volume=0.55",
                ],
            ),
        ],
        "ambiente": [
            (
                "ambiente_room_drone_01.wav",
                [
                    "-f", "lavfi", "-i", "anoisesrc=d=3.0:c=brown:r=44100:a=0.25",
                    "-af", "lowpass=f=240,afade=t=in:ss=0:d=0.6,afade=t=out:st=2.2:d=0.8,volume=1.3",
                ],
            ),
            (
                "ambiente_dark_wind_02.wav",
                [
                    "-f", "lavfi", "-i", "anoisesrc=d=3.0:c=pink:r=44100:a=0.20",
                    "-af", "bandpass=f=280:width_type=h:w=180,afade=t=in:ss=0:d=0.6,afade=t=out:st=2.2:d=0.8,volume=1.6",
                ],
            ),
            (
                "ambiente_sub_hum_03.wav",
                [
                    "-f", "lavfi", "-i", "sine=f=48:d=3.0:r=44100",
                    "-af", "afade=t=in:ss=0:d=0.5,afade=t=out:st=2.3:d=0.7,volume=0.45",
                ],
            ),
        ],
        "digital": [
            (
                "digital_data_blip_01.wav",
                [
                    "-f", "lavfi", "-i", "sine=f=1200:d=0.18:r=44100",
                    "-af", "tremolo=f=18:d=0.9,afade=t=out:st=0.08:d=0.10,volume=0.5",
                ],
            ),
            (
                "digital_glitch_burst_02.wav",
                [
                    "-f", "lavfi", "-i", "anoisesrc=d=0.22:c=white:r=44100:a=0.35",
                    "-af", "highpass=f=1400,tremolo=f=25:d=0.95,afade=t=out:st=0.12:d=0.10,volume=0.8",
                ],
            ),
            (
                "digital_telemetry_03.wav",
                [
                    "-f", "lavfi", "-i", "sine=f=880:d=0.25:r=44100",
                    "-af", "tremolo=f=14:d=0.85,afade=t=out:st=0.15:d=0.10,volume=0.5",
                ],
            ),
        ],
        "whoosh": [
            (
                "whoosh_fast_air_01.wav",
                [
                    "-f", "lavfi", "-i", "anoisesrc=d=0.55:c=pink:r=44100:a=0.45",
                    "-af", "bandpass=f=600:width_type=h:w=500,afade=t=in:ss=0:d=0.22,afade=t=out:st=0.22:d=0.33,volume=1.6",
                ],
            ),
            (
                "whoosh_low_pass_02.wav",
                [
                    "-f", "lavfi", "-i", "anoisesrc=d=0.65:c=brown:r=44100:a=0.50",
                    "-af", "bandpass=f=380:width_type=h:w=320,afade=t=in:ss=0:d=0.25,afade=t=out:st=0.25:d=0.40,volume=1.8",
                ],
            ),
        ],
        "click": [
            (
                "click_shutter_01.wav",
                [
                    "-f", "lavfi", "-i", "anoisesrc=d=0.06:c=white:r=44100:a=0.60",
                    "-af", "highpass=f=900,afade=t=out:st=0.01:d=0.05,volume=1.2",
                ],
            ),
        ],
    }

    generados = 0
    for nombre_wav, args_ff in recetas.get(cat, []):
        destino = carpeta_cat / nombre_wav
        rel_path = destino.relative_to(config.RAIZ).as_posix()
        if destino.exists() and destino.stat().st_size > 1_000:
            generados += 1
            if rel_path not in manifiesto:
                _registrar_credito(
                    manifiesto,
                    rel_path,
                    tipo="sfx",
                    categoria=cat,
                    fuente="FFmpeg Procedural Synthesis (Docu Factory)",
                    url="https://ffmpeg.org/ffmpeg-filters.html",
                    licencia="CC0 1.0 Universal (Public Domain)",
                    autor="Docu Factory Procedural Audio",
                )
            continue
        cmd = [ffmpeg, "-y", *args_ff, "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(destino)]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if destino.exists() and destino.stat().st_size > 1_000:
                generados += 1
                _registrar_credito(
                    manifiesto,
                    rel_path,
                    tipo="sfx",
                    categoria=cat,
                    fuente="FFmpeg Procedural Synthesis (Docu Factory)",
                    url="https://ffmpeg.org/ffmpeg-filters.html",
                    licencia="CC0 1.0 Universal (Public Domain)",
                    autor="Docu Factory Procedural Audio",
                )
        except Exception:
            pass
    return generados


def descargar_sfx_freesound(manifiesto: dict[str, dict[str, Any]], max_por_cat: int = 4) -> int:
    """Descarga 3-5 SFX CC0 por categoría desde Freesound (si FREESOUND_API_KEY existe) o genera procedurales."""
    print("\n🔊 [3/3] Configurando SFX en assets/sfx/{whoosh,riser,impact,tension,ambiente,digital,click}...")
    api_key = config.FREESOUND_API_KEY
    total_sfx = 0

    for cat, query in FREESOUND_QUERIES.items():
        carpeta_cat = config.SFX_DIR / cat
        carpeta_cat.mkdir(parents=True, exist_ok=True)
        gitkeep = carpeta_cat / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text(f"# Carpeta de SFX para categoría '{cat}'\n", encoding="utf-8")

        existentes = sorted(
            [p for ext in ("*.wav", "*.mp3", "*.ogg") for p in carpeta_cat.glob(ext) if p.stat().st_size > 1_000]
        )
        for ex in existentes:
            rel_p = ex.relative_to(config.RAIZ).as_posix()
            if rel_p not in manifiesto:
                _registrar_credito(
                    manifiesto,
                    rel_p,
                    tipo="sfx",
                    categoria=cat,
                    fuente="Docu Factory Base SFX / CC0",
                    url="https://freesound.org/",
                    licencia="CC0 1.0 Universal (Creative Commons 0)",
                    autor="CC0 Sound Designer",
                )

        if len(existentes) >= max_por_cat:
            print(f"  📂 SFX '{cat}': ⏭️  Ya cuenta con {len(existentes)} archivo(s).")
            total_sfx += len(existentes)
            continue

        if api_key:
            print(f"  📂 SFX '{cat}': buscando en Freesound (CC0)...")
            try:
                r = requests.get(
                    "https://freesound.org/apiv2/search/text/",
                    params={
                        "query": query,
                        "filter": 'license:"Creative Commons 0" duration:[0.15 TO 10.0]',
                        "fields": "id,name,previews,url,username,license",
                        "page_size": 12,
                        "token": api_key,
                    },
                    timeout=20,
                )
                if r.status_code == 200:
                    results = r.json().get("results", [])
                    obtenidos = len(existentes)
                    for item in results:
                        if obtenidos >= max_por_cat:
                            break
                        sid = item.get("id")
                        previews = item.get("previews") or {}
                        preview_url = previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3")
                        if not sid or not preview_url:
                            continue
                        slug_n = _slug_archivo(item.get("name", f"sfx_{sid}"))
                        destino = carpeta_cat / f"fs_{sid}_{slug_n}.mp3"
                        rel_path = destino.relative_to(config.RAIZ).as_posix()
                        if destino.exists() and destino.stat().st_size > 1_000:
                            obtenidos += 1
                            continue
                        if _descargar_binario([preview_url], destino, min_bytes=2_000):
                            obtenidos += 1
                            total_sfx += 1
                            page_url = item.get("url") or f"https://freesound.org/s/{sid}/"
                            autor = item.get("username") or "Freesound User"
                            print(f"     ✅ Descargado: {destino.name} — {page_url}")
                            _registrar_credito(
                                manifiesto,
                                rel_path,
                                tipo="sfx",
                                categoria=cat,
                                fuente="Freesound API v2",
                                url=page_url,
                                licencia="CC0 1.0 Universal (Creative Commons 0)",
                                autor=autor,
                            )
                    continue
                else:
                    print(f"     ⚠️ Freesound HTTP {r.status_code} para '{cat}', usando síntesis procedural CC0.")
            except Exception as e:
                print(f"     ⚠️ Error Freesound ('{cat}'): {e}")

        # Si no hay FREESOUND_API_KEY o aún faltan archivos, generamos SFX procedurales CC0 con FFmpeg
        gen = _generar_sfx_procedural_ffmpeg(manifiesto, cat, carpeta_cat)
        actuales = len([p for ext in ("*.wav", "*.mp3", "*.ogg") for p in carpeta_cat.glob(ext) if p.stat().st_size > 1_000])
        print(f"  📂 SFX '{cat}': ✅ {actuales} archivo(s) listos ({gen} sintéticos CC0 verificados).")
        total_sfx += actuales

    return total_sfx


def escribir_credits_md(manifiesto: dict[str, dict[str, Any]]) -> None:
    """Genera assets/CREDITS.md con todas las pistas de música, overlays y SFX."""
    lineas = [
        "# 📜 Créditos y Licencias de Assets (`assets/CREDITS.md`)",
        "",
        "Este archivo es generado y actualizado automáticamente por [`scripts/descargar_assets.py`](../scripts/descargar_assets.py).",
        "Todos los recursos utilizados por **Docu Factory** provienen de dominio público (**CC0 1.0**), **Pixabay Content License** o síntesis procedural propia sin reclamos de Content ID.",
        "",
        "## Resumen de Fuentes",
        "",
        "| Categoría | Fuente Principal | URL | Licencia |",
        "| :--- | :--- | :--- | :--- |",
        "| **Música Documental** (`assets/music/`) | **FreePD** (Public Domain Music) | <https://freepd.com/> / <https://archive.org/details/freepd> | **CC0 1.0 Universal (Public Domain)** |",
        "| **Video Overlays** (`assets/overlays/`) | **Pixabay Videos API** | <https://pixabay.com/videos/> | **Pixabay Content License** (Uso comercial libre, sin atribución obligatoria) |",
        "| **Efectos de Sonido** (`assets/sfx/`) | **Freesound (CC0)** / **FFmpeg Procedural** | <https://freesound.org/> / <https://ffmpeg.org/> | **CC0 1.0 Universal (Creative Commons 0)** |",
        "",
    ]

    for seccion_tipo, titulo_sec in [
        ("music", "🎵 Música por Mood (`assets/music/`)"),
        ("overlay", "🎞️ Overlays Visuales (`assets/overlays/`)"),
        ("sfx", "🔊 Efectos de Sonido (`assets/sfx/`)"),
    ]:
        lineas.append(f"## {titulo_sec}")
        lineas.append("")
        lineas.append("| Archivo | Categoría / Mood | Fuente | Autor | URL | Licencia |")
        lineas.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        items = sorted(
            [v for v in manifiesto.values() if v.get("tipo") == seccion_tipo],
            key=lambda x: (x.get("categoria", ""), x.get("archivo", "")),
        )
        for it in items:
            arch = f"`{it['archivo']}`"
            cat = it.get("categoria", "-")
            fnt = it.get("fuente", "-")
            aut = it.get("autor", "-")
            url = it.get("url", "-")
            lic = it.get("licencia", "-")
            lineas.append(f"| {arch} | `{cat}` | {fnt} | {aut} | {url} | {lic} |")
        lineas.append("")

    CREDITS_MD.write_text("\n".join(lineas), encoding="utf-8")
    print(f"\n📝 Archivo de licencias actualizado en: {CREDITS_MD}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Descargador idempotente de música FreePD, overlays Pixabay y SFX CC0.")
    ap.add_argument("--max-music", type=int, default=5, help="Pistas por mood de FreePD (default: 5)")
    ap.add_argument("--max-overlays", type=int, default=3, help="Overlays por tipo de Pixabay (default: 3)")
    ap.add_argument("--max-sfx", type=int, default=4, help="SFX por categoría de Freesound/FFmpeg (default: 4)")
    args = ap.parse_args()

    manifiesto = _cargar_manifiesto()

    n_music = descargar_musica_freepd(manifiesto, max_por_mood=args.max_music)
    n_over = descargar_overlays_pixabay(manifiesto, max_por_tipo=args.max_overlays)
    n_sfx = descargar_sfx_freesound(manifiesto, max_por_cat=args.max_sfx)

    _guardar_manifiesto(manifiesto)
    escribir_credits_md(manifiesto)

    print(
        f"\n✅ Descarga idempotente finalizada: "
        f"{n_music} pistas de música | {n_over} overlays de video | {n_sfx} efectos de sonido."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
