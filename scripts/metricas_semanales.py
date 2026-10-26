"""Docu Factory — reporte semanal de métricas (reproducible, multiplataforma).

Lee YouTube Data API v3 + YouTube Analytics API v2 con el MISMO token OAuth que usa
subir_video.py (assets/credentials/token_youtube.json) y cruza cada video con el
inventario de proyectos/ (tono, estilo_color, avatar, hook, duración, miniatura).

Uso (Windows o Linux, desde la raíz del repo):
  python scripts/metricas_semanales.py                      # semana anterior (lun-dom)
  python scripts/metricas_semanales.py --inicio 2026-10-19 --fin 2026-10-25
  python scripts/metricas_semanales.py --sin-api            # solo inventario
  python scripts/metricas_semanales.py --logs C:\\ruta\\logs  # carpetas extra con upload.log

Salida: reportes/metricas_<fin>.md y reportes/metricas_<fin>.json (carpeta ignorada por git).
Nunca inventa números: si una métrica no se puede leer, el reporte dice cuál y por qué.
No abre navegador ni re-autoriza: si el token no sirve, indica correr
`python subir_video.py auth-youtube`.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

RAIZ = Path(__file__).resolve().parent.parent
PROYECTOS = RAIZ / "proyectos"
REPORTES = RAIZ / "reportes"
TOKEN_FILE = RAIZ / "assets" / "credentials" / "token_youtube.json"
SCOPE_ANALYTICS = "https://www.googleapis.com/auth/yt-analytics.readonly"
INICIO_PRUEBA = date(2026, 10, 22)  # arranque de la prueba de 8 semanas

try:  # Windows sin paquete tzdata no trae la base IANA: Mérida es UTC-6 fijo (sin horario de verano)
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo("America/Merida")
except Exception:  # pragma: no cover
    TZ = timezone(timedelta(hours=-6), "America/Merida")

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ----------------------------------------------------------------- utilidades puras
def iso_duracion_a_s(d: str) -> int:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 0
    dd, h, mi, s = (int(x or 0) for x in m.groups())
    return dd * 86400 + h * 3600 + mi * 60 + s


def fmt_dur(s: Optional[float]) -> str:
    if s is None:
        return "—"
    s = int(round(s))
    return f"{s // 60}:{s % 60:02d}"


def utc_a_merida(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TZ)


def normalizar(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", t).strip()


def similitud(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalizar(a), normalizar(b)).ratio()


def limpiar_ssml(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t or "")).strip()


def semana_anterior(hoy: date) -> tuple[date, date]:
    lunes = hoy - timedelta(days=hoy.weekday())
    return lunes - timedelta(days=7), lunes - timedelta(days=1)


def evaluar_checkpoints(subs: Optional[int], max_largo: Optional[int], max_reel: Optional[int],
                        hoy: date, subs_inicio: Optional[int] = None) -> dict:
    semana = (hoy - INICIO_PRUEBA).days // 7 + 1
    res: dict[str, Any] = {"semana_de_prueba": semana}
    if subs is not None:
        res["semana4"] = {
            "meta": ">100 subs Y (largo >1,000 vistas O reel >10,000)",
            "subs_ok": subs > 100,
            "vistas_ok": (max_largo or 0) > 1000 or (max_reel or 0) > 10000,
            "max_reel_conocido": max_reel,
        }
        dias = max((hoy - INICIO_PRUEBA).days, 1)
        res["semana8"] = {
            "meta": "ritmo para 1,000 subs en ~4 meses (~120 días desde el inicio de la prueba)",
            "subs_actuales": subs,
            "subs_por_dia_necesarios_desde_hoy": round((1000 - subs) / max(120 - dias, 1), 2),
            "subs_por_dia_actual": (round((subs - subs_inicio) / dias, 3) if subs_inicio is not None
                                    else "desconocido (pasa --subs-inicio o habilita Analytics para subscribersGained)"),
        }
    return res


# ----------------------------------------------------------------- inventario local
def _leer_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def inventario(proyectos: Path = PROYECTOS) -> list[dict]:
    out = []
    if not proyectos.exists():
        return out
    for d in sorted(x for x in proyectos.iterdir() if x.is_dir()):
        if "test_revision" in d.name:
            continue
        p = _leer_json(d / "proyecto.json")
        g = _leer_json(d / "guion" / "guion.json") or _leer_json(d / "guion" / "guion_tiktok.json")
        if not p and not g:
            continue
        esc = g.get("escenas") or []
        mini_pub = _leer_json(d / "publicacion" / "miniatura.json")
        hook = g.get("hook") or (esc[0].get("voz") if esc else "")
        estilo = g.get("estilo_color")
        out.append({
            "carpeta": d.name,
            "formato": p.get("formato") or g.get("formato"),
            "creado": p.get("creado"),
            "titulo_trabajo": g.get("titulo_trabajo") or g.get("titulo") or p.get("tema"),
            "titulos_yt": (g.get("youtube_metadata") or {}).get("titulos") or [],
            "tono": g.get("tono"),
            "mood": g.get("mood"),
            "estilo_color_base": estilo.get("base") if isinstance(estilo, dict) else estilo,
            # guiones viejos no traían el campo: el modelo Guion asume True (host visible)
            "usar_avatar": g.get("usar_avatar") if g.get("usar_avatar") is not None else (
                "True (default)" if any(e.get("host_visible") for e in esc) else None),
            "hook": limpiar_ssml(hook)[:220],
            "minutos_guion": g.get("minutos"),
            "duracion_real_s": (p.get("validacion_duracion") or {}).get("real_s"),
            "escenas": len(esc),
            "escenas_con_host": sum(1 for e in esc if e.get("host_visible")),
            "clips_reales": sum(len(e.get("clips_fuente") or []) for e in esc),
            "fuentes_video": len(g.get("fuentes_video") or []),
            "miniatura_guion": g.get("miniatura"),
            "miniatura_estilo": (mini_pub.get("estilo") or None),
            "miniatura_titulo": mini_pub.get("titulo_miniatura") or (g.get("miniatura") or {}).get("titulo"),
            "etapas": {k: v for k, v in (p.get("etapas") or {}).items() if k in ("revision", "render", "publicacion")},
        })
    return out


def subidas_en_logs(carpetas: list[Path]) -> list[dict]:
    """Busca upload.log del CLI subir_video.py: título, plataformas, video_id/enlaces."""
    res = []
    for base in carpetas:
        if not base.exists():
            continue
        for f in base.rglob("upload*.log"):
            txt = f.read_text(encoding="utf-8", errors="ignore")
            for bloque in txt.split("PUBLICANDO VIDEO MULTI-PLATAFORMA")[1:]:
                tit = re.search(r"Título:\s*(.+)", bloque)
                pl = re.search(r"Plataformas:\s*(.+)", bloque)
                res.append({
                    "log": str(f),
                    "mtime_log": datetime.fromtimestamp(f.stat().st_mtime, TZ).isoformat(timespec="minutes"),
                    "titulo": tit.group(1).strip() if tit else None,
                    "plataformas": pl.group(1).strip() if pl else None,
                    "yt_id": (re.search(r"video_id=([\w-]{11})", bloque) or [None, None])[1],
                    "fb": re.findall(r"facebook\.com/reel/\d+", bloque),
                    "tiktok_ok": "subido a TikTok con éxito" in bloque,
                })
    return res


def emparejar(titulo_yt: str, inv: list[dict]) -> Optional[dict]:
    mejor, score = None, 0.0
    for it in inv:
        if it.get("formato") == "9:16":
            continue
        for cand in [it.get("titulo_trabajo") or ""] + list(it.get("titulos_yt") or []):
            s = similitud(titulo_yt, cand)
            if s > score or (s == score and mejor and (it.get("creado") or "") > (mejor.get("creado") or "")):
                mejor, score = it, s
    return mejor if score >= 0.6 else None


# ----------------------------------------------------------------- APIs YouTube
def credenciales():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    if not TOKEN_FILE.exists():
        raise RuntimeError(f"No existe {TOKEN_FILE}. Corre: python subir_video.py auth-youtube")
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE))
    if not creds.valid:
        try:
            creds.refresh(Request())
        except Exception as e:
            raise RuntimeError(f"No se pudo refrescar el token ({e}). Corre: python subir_video.py auth-youtube")
    return creds


def scopes_concedidos(creds) -> list[str]:
    import requests

    try:
        r = requests.get("https://oauth2.googleapis.com/tokeninfo", params={"access_token": creds.token}, timeout=20)
        return (r.json().get("scope") or "").split()
    except Exception:
        return list(creds.scopes or [])


def datos_youtube(creds) -> dict:
    from googleapiclient.discovery import build

    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    ch = yt.channels().list(part="snippet,statistics,contentDetails", mine=True).execute()["items"][0]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, tok = [], None
    while True:
        r = yt.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=50, pageToken=tok).execute()
        ids += [i["contentDetails"]["videoId"] for i in r.get("items", [])]
        tok = r.get("nextPageToken")
        if not tok:
            break
    videos = []
    for i in range(0, len(ids), 50):
        r = yt.videos().list(part="snippet,status,contentDetails,statistics", id=",".join(ids[i:i + 50])).execute()
        for v in r.get("items", []):
            st = v.get("statistics", {})
            dur = iso_duracion_a_s(v["contentDetails"]["duration"])
            videos.append({
                "id": v["id"],
                "titulo": v["snippet"]["title"],
                "publicado_utc": v["snippet"]["publishedAt"],
                "publicado_merida": utc_a_merida(v["snippet"]["publishedAt"]).isoformat(timespec="minutes"),
                "privacidad": v["status"]["privacyStatus"],
                "duracion_s": dur,
                "tipo": "short" if dur <= 180 else "largo",
                "vistas": int(st.get("viewCount", 0)),
                "likes": int(st.get("likeCount", 0)),
                "comentarios": int(st.get("commentCount", 0)),
            })
    videos.sort(key=lambda x: x["publicado_utc"])
    return {
        "canal": {
            "id": ch["id"],
            "titulo": ch["snippet"]["title"],
            "creado_merida": utc_a_merida(ch["snippet"]["publishedAt"]).isoformat(timespec="minutes"),
            "suscriptores": int(ch["statistics"].get("subscriberCount", 0)),
            "vistas_totales": int(ch["statistics"].get("viewCount", 0)),
            "videos": int(ch["statistics"].get("videoCount", 0)),
        },
        "videos": videos,
    }


def datos_analytics(creds, inicio: date, fin: date, desde_canal: date, video_ids: list[str]) -> dict:
    """Devuelve métricas o, por bloque, el error exacto (nunca rellena con ceros)."""
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    ya = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    out: dict[str, Any] = {"errores": {}}

    def q(nombre, **kw):
        try:
            r = ya.reports().query(ids="channel==MINE", **kw).execute()
            cols = [h["name"] for h in r.get("columnHeaders", [])]
            out[nombre] = [dict(zip(cols, row)) for row in r.get("rows", []) or []]
        except HttpError as e:
            msg = str(e)
            if "accessNotConfigured" in msg or "has not been used in project" in msg:
                m = re.search(r"project (\d+)", msg)
                proj = m.group(1) if m else "<id>"
                fix = ("Habilitar 'YouTube Analytics API' en Google Cloud (proyecto docufactory "
                       f"{proj}): https://console.developers.google.com/apis/api/youtubeanalytics.googleapis.com/overview?project={proj} "
                       "y volver a correr este script (no hace falta re-autorizar: el token ya tiene yt-analytics.readonly).")
            elif "insufficient" in msg.lower() or "forbidden" in msg.lower():
                fix = "Falta scope yt-analytics.readonly: correr `python subir_video.py auth-youtube` en la laptop de Francisco."
            else:
                fix = "Revisar mensaje; reintentar en 24-72 h si es retraso de datos."
            out["errores"][nombre] = {"error": msg[-400:], "fix": fix}

    base = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained,subscribersLost"
    q("semana_total", startDate=str(inicio), endDate=str(fin), metrics=base)
    q("historico_total", startDate=str(desde_canal), endDate=str(fin), metrics=base)
    q("semana_por_dia", startDate=str(inicio), endDate=str(fin), metrics="views,estimatedMinutesWatched,subscribersGained", dimensions="day", sort="day")
    if video_ids:
        q("historico_por_video", startDate=str(desde_canal), endDate=str(fin), metrics=base, dimensions="video",
          filters="video==" + ",".join(video_ids[:200]), sort="-views", maxResults=200)
        q("semana_por_video", startDate=str(inicio), endDate=str(fin), metrics=base, dimensions="video",
          filters="video==" + ",".join(video_ids[:200]), sort="-views", maxResults=200)
    q("fuentes_trafico", startDate=str(desde_canal), endDate=str(fin), metrics="views,estimatedMinutesWatched",
      dimensions="insightTrafficSourceType", sort="-views")
    out["nota_impresiones_ctr"] = ("Impresiones y CTR de miniatura NO existen en YouTube Analytics API v2; solo en "
                                   "YouTube Studio o en YouTube Reporting API (reporte channel_reach_basic_a1).")
    return out


# ----------------------------------------------------------------- reporte
def construir_md(rep: dict) -> str:
    L = [f"# Docu Factory — métricas {rep['inicio']} a {rep['fin']} (hora Mérida)",
         f"Generado: {rep['generado']} · fuente: YouTube Data API v3 / Analytics API v2 + proyectos/", ""]
    yt = rep.get("youtube")
    if yt:
        c = yt["canal"]
        L += [f"## Canal {c['titulo']}", f"- Suscriptores (lifetime, Data API): **{c['suscriptores']}**",
              f"- Vistas totales (lifetime, Data API, contador del canal; puede ir atrasado vs. la suma por video): **{c['vistas_totales']}**",
              f"- Suma de vistas por video: {sum(v['vistas'] for v in yt['videos'])}",
              f"- Videos (contador del canal): {c['videos']} · listados en uploads: {len(yt['videos'])}", ""]
        L += ["## Videos", "| Publicado (Mérida) | Título | Priv. | Duración | Vistas | Vistas/día |  Likes | Coment. | Tono | Avatar | Clips reales | Miniatura |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for v in yt["videos"]:
            it = v.get("proyecto") or {}
            me = it.get("miniatura_estilo") or {}
            mini = f"{it.get('miniatura_titulo') or '—'} ({me.get('layout', '—')})" if it else "—"
            L.append(f"| {v['publicado_merida'].replace('T', ' ')[:16]} | {v['titulo']} | {v['privacidad']} | {fmt_dur(v['duracion_s'])} | "
                     f"{v['vistas']} | {v.get('vistas_por_dia', '—')} | {v['likes']} | {v['comentarios']} | {it.get('tono') or it.get('mood') or '—'} | "
                     f"{it.get('usar_avatar') if it else '—'} | {it.get('clips_reales', '—') if it else '—'} | {mini} |")
        L.append("")
    elif rep.get("error_youtube"):
        L += [f"## YouTube: NO LEÍDO", f"- {rep['error_youtube']}", ""]
    an = rep.get("analytics")
    if an:
        L.append("## YouTube Analytics")
        for k in ("semana_total", "historico_total"):
            if k in an:
                L.append(f"- {k}: {an[k]}")
        for k, v in an.get("errores", {}).items():
            L.append(f"- **{k}: no leído** — {v['fix']}")
        L += [f"- {an['nota_impresiones_ctr']}", ""]
    L += ["## Subidas registradas en logs (FB/TikTok)"]
    for s in rep.get("subidas_logs", []):
        L.append(f"- mtime log {s['mtime_log']} · {s['titulo']} · {s['plataformas']} · FB {s['fb'] or '—'} · TikTok ok={s['tiktok_ok']}")
    L += ["", "## Checkpoints", "```", json.dumps(rep.get("checkpoints"), ensure_ascii=False, indent=1), "```", ""]
    L += ["## Inventario proyectos/ (no publicados o verticales)"]
    for it in rep["inventario"]:
        if it.get("_emparejado"):
            continue
        L.append(f"- {it['carpeta']} · {it['formato']} · tono={it['tono'] or it['mood']} · avatar={it['usar_avatar']} · "
                 f"clips_reales={it['clips_reales']} · etapas={it['etapas']} · hook: {it['hook'][:90]}")
    return "\n".join(L) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    hoy = datetime.now(TZ).date()
    ini_def, fin_def = semana_anterior(hoy)
    ap.add_argument("--inicio", type=date.fromisoformat, default=ini_def)
    ap.add_argument("--fin", type=date.fromisoformat, default=fin_def)
    ap.add_argument("--sin-api", action="store_true", help="solo inventario local")
    ap.add_argument("--logs", nargs="*", type=Path, default=[], help="carpetas extra donde buscar upload*.log")
    ap.add_argument("--salida", type=Path, default=REPORTES)
    ap.add_argument("--subs-inicio", type=int, default=None, help="suscriptores al iniciar la prueba (si se conocen)")
    a = ap.parse_args(argv)

    inv = inventario()
    rep: dict[str, Any] = {"inicio": str(a.inicio), "fin": str(a.fin),
                           "generado": datetime.now(TZ).isoformat(timespec="minutes"), "inventario": inv}
    rep["subidas_logs"] = subidas_en_logs([PROYECTOS, *a.logs])

    if not a.sin_api:
        try:
            creds = credenciales()
            rep["scopes"] = scopes_concedidos(creds)
            yt = datos_youtube(creds)
            for v in yt["videos"]:
                it = emparejar(v["titulo"], inv)
                if it:
                    it["_emparejado"] = True
                    v["proyecto"] = {k: it[k] for k in ("carpeta", "tono", "mood", "estilo_color_base", "usar_avatar", "hook",
                                                        "clips_reales", "fuentes_video", "miniatura_titulo", "miniatura_estilo")}
                v["vistas_por_dia"] = round(v["vistas"] / max((datetime.now(timezone.utc) - datetime.fromisoformat(
                    v["publicado_utc"].replace("Z", "+00:00"))).total_seconds() / 86400, 0.5), 2)
            rep["youtube"] = yt
            if SCOPE_ANALYTICS in rep["scopes"]:
                desde = date.fromisoformat(yt["canal"]["creado_merida"][:10])
                rep["analytics"] = datos_analytics(creds, a.inicio, a.fin, desde, [v["id"] for v in yt["videos"]])
            else:
                rep["analytics"] = {"errores": {"todo": {"error": "token sin yt-analytics.readonly",
                                    "fix": "Correr `python subir_video.py auth-youtube` en la laptop de Francisco y aceptar el permiso de Analytics."}},
                                    "nota_impresiones_ctr": "n/a"}
            largos = [v["vistas"] for v in yt["videos"] if v["tipo"] == "largo"]
            shorts = [v["vistas"] for v in yt["videos"] if v["tipo"] == "short"]
            rep["checkpoints"] = evaluar_checkpoints(yt["canal"]["suscriptores"], max(largos or [0]),
                                                     max(shorts) if shorts else None, hoy, a.subs_inicio)
            ga = sum(r.get("subscribersGained", 0) - r.get("subscribersLost", 0) for r in rep["analytics"].get("historico_total", []))
            if "historico_total" in rep["analytics"] and a.subs_inicio is None:
                rep["checkpoints"]["semana8"]["nota"] = f"Analytics: {ga} subs netos desde la creación del canal"
        except Exception as e:
            rep["error_youtube"] = str(e)

    a.salida.mkdir(parents=True, exist_ok=True)
    base = a.salida / f"metricas_{a.fin}"
    base.with_suffix(".json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    base.with_suffix(".md").write_text(construir_md(rep), encoding="utf-8")
    print(f"✅ Reporte: {base.with_suffix('.md')}\n   Datos:   {base.with_suffix('.json')}")
    for k, v in (rep.get("analytics") or {}).get("errores", {}).items():
        print(f"⚠️  {k}: {v['fix']}")
    if rep.get("error_youtube"):
        print(f"❌ YouTube: {rep['error_youtube']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
