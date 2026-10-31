# KDrama & Novel Scraping Engine (C++17)

Motor modular de scraping, sanitización y análisis de tramas para K-Dramas y novelas desarrollado en C++17. Diseñado para integrarse en el ecosistema de generación de contenidos de `docufactory`.

## Características
- **Descarga HTTP/HTTPS Segura:** Implementación nativa con `WinHTTP` (TLS 1.3 / Schannel) en Windows y compatibilidad con `libcurl` en Linux/macOS.
- **Limpieza y Sanitización Lineal O(N):** Purga de `<script>`, `<style>`, anuncios, menús y decodificación de entidades HTML sin recursión ni consumo excesivo de memoria.
- **Análisis de Conflicto Narrativo:** Algoritmo heurístico que identifica automáticamente puntos de quiebre dramático, traiciones, muertes, conspiraciones y revelaciones clave por capítulo.
- **Exportación Dual:**
  - `CSV` compatible con Excel (RFC 4180 y BOM UTF-8).
  - `JSON` estructurado con sinopsis y lista de giros dramáticos.

## Estructura
```text
kdrama_scraper/
├── CMakeLists.txt          # Configuración multiplataforma
├── build.bat               # Compilador 1-clic con MSVC en Windows
├── include/
│   ├── DramaEpisode.hpp    # Estructura del capítulo y conflictos
│   ├── HttpClient.hpp      # Cliente HTTP WinHTTP / cURL
│   ├── HtmlParser.hpp      # Parser y analizador narrativo
│   ├── Logger.hpp          # Sistema de logs con timestamps
│   └── StorageEngine.hpp   # Exportador CSV/JSON
└── src/
    ├── HttpClient.cpp
    ├── HtmlParser.cpp
    ├── StorageEngine.cpp
    └── main.cpp
```

## Compilación en Windows
Ejecuta el script:
```powershell
.\build.bat
```
El ejecutable se generará en `bin\kdrama_scraper.exe`.

## Uso
```powershell
# Modo demostración integrado:
.\bin\kdrama_scraper.exe --demo

# Extracción desde URL pública:
.\bin\kdrama_scraper.exe --url "https://en.wikipedia.org/wiki/The_World_of_the_Married" --output "el_mundo_de_los_casados"
```
