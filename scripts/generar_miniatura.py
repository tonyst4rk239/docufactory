#!/usr/bin/env python3
"""CLI para generación automática de miniaturas de YouTube con alto CTR para Docu Factory.

Uso:
  python scripts/generar_miniatura.py --slug <slug_del_proyecto>
  python scripts/generar_miniatura.py --titulo "¡FUE UN FRAUDE!" --host alerta --salida miniatura.png
  python scripts/generar_miniatura.py --config config_miniatura.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Agregar raíz al sys.path
RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from src.estado import Proyecto
from src.miniatura import generar_miniatura, generar_miniatura_proyecto


def main() -> int:
    parser = argparse.ArgumentParser(description="Generador de miniaturas cinematográficas de alto CTR.")
    parser.add_argument("--slug", help="Slug o ruta de un proyecto de Docu Factory")
    parser.add_argument("--titulo", default=None, help="Texto viral principal en amarillo de alto impacto")
    parser.add_argument("--subtitulo", default=None, help="Subtítulo o banner inferior")
    parser.add_argument("--host", default=None, help="Pose del host (alerta, pensativo, dinero, explicando, etc.)")
    parser.add_argument("--fondo", default=None, help="Ruta a una imagen o video de fondo")
    parser.add_argument("--stamp", default=None, help="Texto del sello de alerta (ej. CONFIDENCIAL / TOP SECRET)")
    parser.add_argument("--salida", default=None, help="Ruta donde guardar la imagen resultante")
    parser.add_argument("--resolucion", choices=["1080p", "720p"], default="1080p", help="Resolución de exportación")
    parser.add_argument("--layout", default=None, choices=["avatar_derecha", "avatar_izquierda", "avatar_centro", "sin_avatar"])
    parser.add_argument("--tono", default=None, help="misterio, polemica, investigacion, humor, epico, drama, curiosidad, terror")
    parser.add_argument("--salida-dir", default=None, help="(con --slug) carpeta destino en vez de publicacion/")
    parser.add_argument("--sin-historial", action="store_true", help="(con --slug) no registrar en el historial anti-repetición")
    parser.add_argument("--config", default=None, help="Archivo JSON con configuración personalizada de ThumbnailConfig")

    args = parser.parse_args()

    if args.config:
        cfg_path = Path(args.config)
        if not cfg_path.exists():
            print(f"❌ Error: Archivo de configuración no encontrado: {cfg_path}")
            return 1
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        salida = generar_miniatura(
            titulo=data.get("primaryText", "¡FUE UN FRAUDE!"),
            subtitulo=data.get("subtitleBannerText", "DOCUMENTAL DE INVESTIGACIÓN"),
            host_pose="alerta",
            fondo_path=Path(data["customBackgroundImage"]) if data.get("customBackgroundImage") else None,
            salida_path=Path(args.salida) if args.salida else None,
            stamp_text=data.get("stampText", "CONFIDENCIAL"),
            resolucion=args.resolucion,
        )
        print(f"✅ Miniatura generada desde JSON: {salida}")
        return 0

    if args.slug:
        p = Proyecto.cargar(args.slug)
        print(f"🎨 Generando paquete de miniaturas A/B (1080p y 720p) para '{p.tema}'...")
        res = generar_miniatura_proyecto(
            p=p,
            titulo_custom=args.titulo,
            pose_custom=args.host,
            fondo_custom=Path(args.fondo) if args.fondo else None,
            subtitulo_custom=args.subtitulo,
            sello_custom=args.stamp,
            layout_custom=args.layout,
            tono_custom=args.tono,
            salida_dir=Path(args.salida_dir) if args.salida_dir else None,
            registrar_historial=not args.sin_historial,
        )
        print("=" * 60)
        print("🏆 ¡MINIATURAS GENERADAS CON ÉXITO!")
        print(f"🖼️  1080p Full HD: {res['1080p']}")
        print(f"🖼️  720p Estándar: {res['720p']}")
        print(f"📄 Manifiesto:    {Path(res['1080p']).parent / 'miniatura.json'}")
        print("=" * 60)
        return 0

    # Generación individual
    titulo = args.titulo or "¡FUE UN FRAUDE!"
    salida = generar_miniatura(
        titulo=titulo,
        subtitulo=args.subtitulo if args.subtitulo is not None else "DOCUMENTAL DE INVESTIGACIÓN",
        host_pose=args.host or "alerta",
        fondo_path=Path(args.fondo) if args.fondo else None,
        salida_path=Path(args.salida) if args.salida else None,
        stamp_text=args.stamp if args.stamp is not None else "CONFIDENCIAL",
        resolucion=args.resolucion,
    )
    print(f"✅ Miniatura generada: {salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
