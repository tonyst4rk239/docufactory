# Docu Factory 🎬

Pipeline automatizado en Python + FFmpeg para producción de documentales cinematográficos en español con tono oscuro/misterioso.
Soporta dos formatos principales:
- **Videos Largos (16:9)**: tops, rankings y documentales profundos vía `make_video.py`.
- **Reels / TikTok / Shorts (9:16)**: micro-documentales rápidos de alta retención vía `make_tiktok.py`.

El código está diseñado para ser totalmente compatible y portable entre **Windows y Linux** (rutas relativas con `pathlib.Path`).

---

## 🚀 Uso Rápido

### Verificación de Entorno
```bash
python make_video.py doctor
```

### Flujo de Producción 16:9
```bash
# 1. Importar guion JSON externo (generado por Pluma)
python make_video.py importar ejemplos/guion_ejemplo.json

# 2. Curaduría y revisión de B-roll (Lente)
python make_video.py revisar <slug> --aprobar all

# 3. Render final
python make_video.py renderizar <slug>

# O todo de corrido:
python make_video.py importar ejemplos/guion_ejemplo.json --auto
```

### Flujo de Producción 9:16 (Reels / Shorts)
```bash
python make_tiktok.py importar <guion.json>
python make_tiktok.py renderizar <slug>
```

---

## ⚖️ Normalización Automática de Brillo entre Escenas

Para evitar cortes bruscos y choques visuales entre tomas oscuras y tomas sobreexpuestas, el renderizador implementa una normalización automática de luminancia tanto en **videos largos (16:9)** como en **Reels (9:16)**.

### ¿Cómo funciona?
1. **Medición de Luminancia Media**: Utiliza el filtro `signalstats` de FFmpeg para calcular la luminancia media `YAVG` de cada escena en una escala de 0 a 255.
2. **Detección de Saltos Visuales**: Si el salto de brillo entre dos escenas consecutivas es mayor a **~40** puntos (umbral por defecto):
   - Se identifica la toma más brillante.
   - Si su luminancia excede el rango confortable (`115–125`), se calcula un ajuste correctivo en escala FFmpeg `eq=brightness` para situarla en una media de **120.0**.
3. **Respeto al Color Grade por Tono**: El ajuste de brillo se integra directamente en el filtro `eq=brightness` sin alterar la saturación, el contraste, el `colorbalance` ni las curvas (`curves`) del tono artístico asignado (`misterio`, `terror`, `epico`, `curiosidad`, etc.).

### Desactivación por CLI
Si se desea renderizar sin aplicar la normalización automática, se puede pasar la bandera `--sin-normalizar-brillo`:

```bash
# En videos largos 16:9
python make_video.py renderizar <slug> --sin-normalizar-brillo
python make_video.py continuar <slug> --sin-normalizar-brillo
python make_video.py importar <guion.json> --auto --sin-normalizar-brillo

# En Reels 9:16
python make_tiktok.py renderizar <slug> --sin-normalizar-brillo
python make_tiktok.py continuar <slug> --sin-normalizar-brillo
python make_tiktok.py importar <guion.json> --auto --sin-normalizar-brillo
```

### Configuración en `config/edicion.yaml`
Los parámetros de normalización pueden ajustarse o desactivarse globalmente o por formato:

```yaml
formatos:
  horizontal_16_9:
    normalizar_brillo: true
  vertical_9_16:
    normalizar_brillo: true

normalizacion_brillo:
  enabled: true
  umbral_salto: 40.0         # Salto máximo permitido entre escenas consecutivas (0-255)
  target_luminancia: 120.0   # Media objetivo para la toma brillante (~115-125)
  rango_target: [115.0, 125.0]
```

---

## 🧪 Pruebas Unitarias

Para correr la suite de pruebas de la normalización de brillo:

```bash
python -m unittest tests/test_normalizar_brillo.py
```
