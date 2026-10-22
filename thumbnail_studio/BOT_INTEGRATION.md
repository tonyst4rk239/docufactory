# 🤖 Guía de Interacción para Bots (Doyou, Megáfono, Pluma) — Thumbnail Studio

Esta aplicación (`thumbnail_studio`) y su motor CLI en Python permiten que agentes autónomos (Doyou, Megáfono, Pluma) generen, auditen y exporten miniaturas cinematográficas de YouTube 16:9 con alto CTR, optimizadas para el nicho de thrillers y documentales de investigación.

---

## 🚀 Modos de Interacción para el Bot

### 1. Interacción Headless por CLI (Recomendado para servidores Linux y pipelines)
El bot puede generar miniaturas automáticamente sin requerir entorno gráfico:

```bash
# Modo 1: Generar miniaturas 1080p y 720p desde un proyecto existente
python make_video.py miniatura <slug>

# Modo 2: Usando el script dedicado con parámetros directos
python scripts/generar_miniatura.py \
  --slug <slug> \
  --titulo "¡FUE UN FRAUDE!" \
  --host alerta \
  --resolucion 1080p

# Modo 3: Generación independiente desde cualquier texto
python scripts/generar_miniatura.py \
  --titulo "LO APAGARON EN VIVO" \
  --subtitulo "DOCUMENTAL DE INVESTIGACIÓN" \
  --host pensativo \
  --stamp "CONFIDENCIAL" \
  --salida publicacion/miniatura_1080p.png
```

---

### 2. Interacción mediante Manifiesto JSON
El bot o agente puede escribir un archivo JSON con los parámetros de la miniatura (`ThumbnailConfig`) y renderizarla directamente:

```json
{
  "primaryText": "¡LA IA TOMÓ EL CONTROL!",
  "subtitleBannerText": "EXPEDIENTE DESCLASIFICADO",
  "hostPose": "alerta",
  "stampText": "TOP SECRET",
  "customBackgroundImage": "b_roll/revision/escena_001_mitad.jpg"
}
```

Y ejecutar:
```bash
python scripts/generar_miniatura.py --config mi_miniatura.json --salida miniatura.png
```

---

### 3. Estudio Web Interactivo (Vite + React)
Para revisión humana o interacción vía navegador automatizado (Puppeteer / Playwright):

```bash
cd thumbnail_studio

# En Linux:
./iniciar_estudio.sh

# En Windows:
iniciar_estudio.bat
# o manualmente:
npm install && npm run dev
```

La interfaz queda accesible en `http://localhost:3000` con:
- Editor visual en tiempo real de capas (Host, Fondo CCTV, Tipografía viral).
- Selector de poses del Host y siluetas brillantes en Cyan / Amarillo / Rojo.
- Auditor de CTR predictivo y simulador de feed de YouTube.
- Exportación directa a 1080p y 720p.
