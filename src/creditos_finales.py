"""Tarjeta final de créditos (obras CC BY / CC BY-SA) que se anexa al final del video largo.

La descripción de YouTube tiene un tope de 5000 bytes UTF-8 y no siempre caben el título, autor,
licencia y enlace de cada obra con licencia Creative Commons de atribución. Este módulo arma la lista
completa a partir de b_roll/creditos.json (campo `tomas` de cada escena), la pagina en imágenes
1920x1080 legibles y la anexa al render como un bloque de unos segundos con audio en silencio.

Todo usa pathlib, Pillow y ffmpeg, sin rutas ni comandos propios de un sistema operativo.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import unquote

ANCHO, ALTO = 1920, 1080
FPS = 30
_RE_ATRIBUCION = re.compile(r"\bCC[\s-]*BY\b", re.IGNORECASE)


def requiere_atribucion(licencia: str) -> bool:
    """True para CC BY y CC BY-SA (cualquier versión); False para CC0, dominio público o stock libre."""
    lic = (licencia or "").strip()
    if not lic or re.search(r"\bCC0\b|dominio p[úu]blico|public domain|\bPD\b", lic, re.IGNORECASE):
        return False
    return bool(_RE_ATRIBUCION.search(lic))


def enlace_legible(url: str) -> str:
    """Enlace sin esquema y decodificado (commons.wikimedia.org/wiki/File:Grutas_de_García.jpg)."""
    u = unquote((url or "").strip())
    return re.sub(r"^https?://", "", u)


def _titulo_desde_url(url: str) -> str:
    u = unquote(url or "")
    if "/wiki/File:" in u:
        return u.split("/wiki/File:", 1)[1].replace("_", " ")
    return u.rstrip("/").rsplit("/", 1)[-1]


def recolectar_obras(creditos: Iterable[dict]) -> list[dict]:
    """Obras con atribución obligatoria, sin duplicados (por página), en orden de aparición."""
    obras: list[dict] = []
    vistas: set[str] = set()
    for entrada in creditos or []:
        for t in entrada.get("tomas") or []:
            lic = t.get("licencia") or ""
            pagina = t.get("pagina") or t.get("url") or ""
            if not requiere_atribucion(lic) or not pagina:
                continue
            clave = unquote(pagina).strip().lower()
            if clave in vistas:
                continue
            vistas.add(clave)
            obras.append({
                "titulo": (t.get("titulo") or _titulo_desde_url(pagina)).strip(),
                "autor": (t.get("autor") or t.get("credito") or "autor sin nombre").strip(),
                "licencia": lic.strip(),
                "enlace": pagina.strip(),
            })
    return obras


def paginar(obras: list[dict], por_pagina: int = 9) -> list[list[dict]]:
    por_pagina = max(1, int(por_pagina))
    return [obras[i:i + por_pagina] for i in range(0, len(obras), por_pagina)]


def _fuente(ruta: Optional[Path], tam: int):
    from PIL import ImageFont
    if ruta and Path(ruta).exists():
        return ImageFont.truetype(str(ruta), tam)
    try:
        return ImageFont.load_default(size=tam)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _ajustar(draw, texto: str, ruta_fuente: Optional[Path], tam: int, ancho_max: int, tam_min: int, recortar: bool):
    """Baja el tamaño hasta que el texto quepa; si `recortar`, corta con '…' al llegar al mínimo."""
    t = tam
    while t > tam_min:
        f = _fuente(ruta_fuente, t)
        if draw.textlength(texto, font=f) <= ancho_max:
            return texto, f
        t -= 1
    f = _fuente(ruta_fuente, tam_min)
    if recortar:
        while texto and draw.textlength(texto + "…", font=f) > ancho_max:
            texto = texto[:-1]
        texto = texto.rstrip() + "…"
    return texto, f


def render_paginas(obras: list[dict], carpeta: Path, ruta_fuente: Optional[Path] = None, por_pagina: int = 9,
                   titulo: str = "CRÉDITOS DE IMÁGENES · LICENCIAS CREATIVE COMMONS") -> list[Path]:
    """Dibuja cada página de créditos como PNG 1920x1080 y devuelve las rutas."""
    from PIL import Image, ImageDraw
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    paginas = paginar(obras, por_pagina)
    rutas: list[Path] = []
    margen = 110
    ancho_util = ANCHO - 2 * margen
    for n, grupo in enumerate(paginas, 1):
        im = Image.new("RGB", (ANCHO, ALTO), (12, 12, 14))
        d = ImageDraw.Draw(im)
        f_tit = _fuente(ruta_fuente, 44)
        d.text((margen, 56), titulo, font=f_tit, fill=(255, 200, 60))
        f_pag = _fuente(ruta_fuente, 26)
        d.text((ANCHO - margen, 66), f"{n}/{len(paginas)}", font=f_pag, fill=(170, 170, 170), anchor="ra")
        y = 150
        paso = (ALTO - y - 70) // max(1, por_pagina)
        for o in grupo:
            linea1 = f"«{o['titulo']}» · {o['autor']} · {o['licencia']}"
            l1, f1 = _ajustar(d, linea1, ruta_fuente, 32, ancho_util, 22, recortar=True)
            d.text((margen, y), l1, font=f1, fill=(245, 245, 245))
            l2, f2 = _ajustar(d, enlace_legible(o["enlace"]), ruta_fuente, 25, ancho_util, 16, recortar=False)
            d.text((margen, y + 42), l2, font=f2, fill=(140, 200, 255))
            y += paso
        d.text((margen, ALTO - 58), "Licencias: creativecommons.org/licenses · Otras imágenes: dominio público, CC0, Pixabay y Pexels",
               font=_fuente(ruta_fuente, 22), fill=(150, 150, 150))
        ruta = carpeta / f"creditos_{n:02d}.png"
        im.save(ruta)
        rutas.append(ruta)
    return rutas


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def video_desde_paginas(paginas: list[Path], destino: Path, ffmpeg: str = "ffmpeg", seg_por_pagina: float = 3.0,
                        fundido: float = 0.25, musica: Optional[Path] = None, musica_volumen: float = 0.12) -> Path:
    """Une las páginas en un MP4 H.264 1920x1080 30 fps con AAC estéreo 44.1 kHz.
    Con `musica`, la cama musical suena bajita (en bucle, con fundidos) en vez de silencio."""
    if not paginas:
        raise ValueError("No hay páginas de créditos")
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    inputs: list[str] = []
    filtros: list[str] = []
    for i, pag in enumerate(paginas):
        inputs += ["-loop", "1", "-framerate", str(FPS), "-t", f"{seg_por_pagina:.3f}", "-i", str(Path(pag))]
        filtros.append(f"[{i}:v]scale={ANCHO}:{ALTO},setsar=1,format=yuv420p,"
                       f"fade=t=in:st=0:d={fundido},fade=t=out:st={seg_por_pagina - fundido:.3f}:d={fundido}[p{i}]")
    total = seg_por_pagina * len(paginas)
    n = len(paginas)
    filtros.append("".join(f"[p{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]")
    if musica and Path(musica).exists():
        inputs += ["-stream_loop", "-1", "-i", str(Path(musica))]
        filtros.append(f"[{n}:a]aformat=sample_rates=44100:channel_layouts=stereo,atrim=0:{total:.3f},asetpts=PTS-STARTPTS,"
                       f"volume={musica_volumen:.3f},afade=t=in:st=0:d=1.5,afade=t=out:st={max(0.0, total - 3.0):.3f}:d=3[a]")
        mapa_audio = "[a]"
    else:
        inputs += ["-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        mapa_audio = f"{n}:a"
    _run([ffmpeg, "-y", *inputs, "-filter_complex", ";".join(filtros), "-map", "[v]", "-map", mapa_audio,
          "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2", "-t", f"{total:.3f}", str(destino)])
    return destino


def anexar(video: Path, tarjeta: Path, salida: Path, ffmpeg: str = "ffmpeg") -> Path:
    """Concatena video + tarjeta re-codificando solo lo necesario (filtro concat, robusto ante diferencias)."""
    salida = Path(salida)
    _run([ffmpeg, "-y", "-i", str(Path(video)), "-i", str(Path(tarjeta)), "-filter_complex",
          f"[0:v]scale={ANCHO}:{ALTO},setsar=1,fps={FPS},format=yuv420p[v0];[1:v]setsar=1,fps={FPS},format=yuv420p[v1];"
          "[0:a]aformat=sample_rates=44100:channel_layouts=stereo[a0];[1:a]aformat=sample_rates=44100:channel_layouts=stereo[a1];"
          "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]",
          "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2", "-movflags", "+faststart", str(salida)])
    return salida


def anexar_creditos_finales(p, videos: list[Path], ffmpeg: str, cfg: Optional[dict] = None) -> Optional[Path]:
    """Si el proyecto tiene obras CC BY/BY-SA, genera la tarjeta y la anexa a cada video (en sitio)."""
    cc = (cfg or {}).get("creditos_finales", {}) or {}
    if not cc.get("enabled", True):
        return None
    ruta_cred = p.ruta("b_roll", "creditos.json")
    if not ruta_cred.exists():
        return None
    obras = recolectar_obras(json.loads(ruta_cred.read_text("utf-8")))
    if not obras:
        return None
    from . import config
    carpeta = p.carpeta / "renders" / "creditos_finales"
    por_pagina = int(cc.get("obras_por_pagina", 9))
    paginas = render_paginas(obras, carpeta, ruta_fuente=config.FONTS_DIR / "bold.ttf", por_pagina=por_pagina)
    musica = None
    if cc.get("musica", True):
        try:
            from .guion import cargar_guion
            from .render import resolver_musica_mood
            g = cargar_guion(p)
            musica, _, _ = resolver_musica_mood(g.escenas[0].music_mood if g.escenas else "misterio", silencioso=True)
        except Exception as e:   # sin música no se rompe la tarjeta: queda en silencio
            print(f"   ⚠️ Créditos sin cama musical ({e})")
            musica = None
    tarjeta = video_desde_paginas(paginas, carpeta / "tarjeta_creditos.mp4", ffmpeg=ffmpeg,
                                  seg_por_pagina=float(cc.get("segundos_por_pagina", 3.0)),
                                  musica=musica, musica_volumen=float(cc.get("musica_volumen", 0.12)))
    (carpeta / "obras.json").write_text(json.dumps(obras, ensure_ascii=False, indent=1), "utf-8")
    for v in videos:
        v = Path(v)
        if not v.exists():
            continue
        tmp = v.with_name(v.stem + "_con_creditos" + v.suffix)
        anexar(v, tarjeta, tmp, ffmpeg=ffmpeg)
        tmp.replace(v)
    print(f"🎞️  Tarjeta final de créditos: {len(obras)} obras CC BY/BY-SA en {len(paginas)} páginas ({tarjeta})")
    return tarjeta
