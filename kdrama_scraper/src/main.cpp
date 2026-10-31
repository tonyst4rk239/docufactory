#include "HttpClient.hpp"
#include "HtmlParser.hpp"
#include "StorageEngine.hpp"
#include "Logger.hpp"

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#endif

#include <iostream>
#include <string>

void printBanner() {
    std::cout << "===============================================================\n"
              << "       KDRAMA & NOVEL SCRAPING ENGINE (C++17 Modular)          \n"
              << "===============================================================\n";
}

void printUsage() {
    printBanner();
    std::cout << "Uso:\n"
              << "  kdrama_scraper.exe --url <URL> [opciones]\n"
              << "  kdrama_scraper.exe --demo      [opciones]\n\n"
              << "Opciones:\n"
              << "  --url <URL>          : URL publica a descargar y procesar.\n"
              << "  --demo               : Ejecuta la prueba con simulador de K-Drama integrado.\n"
              << "  --output <nombre>    : Nombre base para los archivos de salida (defecto: kdrama_export).\n"
              << "  --format <csv|json|both> : Formato de salida deseado (defecto: both).\n"
              << "  --help               : Muestra este mensaje de ayuda.\n\n"
              << "Ejemplos:\n"
              << "  kdrama_scraper.exe --demo\n"
              << "  kdrama_scraper.exe --url \"https://ejemplo.com/drama-resumen\" --output \"vincenzo\"\n";
}

int main(int argc, char* argv[]) {
#ifdef _WIN32
    // Habilitar soporte de caracteres UTF-8 en la consola de Windows
    SetConsoleOutputCP(CP_UTF8);
    SetConsoleCP(CP_UTF8);
#endif

    std::string targetUrl;
    std::string outputPrefix = "kdrama_export";
    std::string format = "both";
    bool runDemo = false;

    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--url" && i + 1 < argc) {
            targetUrl = argv[++i];
        } else if (arg == "--output" && i + 1 < argc) {
            outputPrefix = argv[++i];
        } else if (arg == "--format" && i + 1 < argc) {
            format = argv[++i];
        } else if (arg == "--demo") {
            runDemo = true;
        } else if (arg == "--help" || arg == "-h") {
            printUsage();
            return 0;
        }
    }

    if (targetUrl.empty() && !runDemo) {
        Logger::log(LogLevel::ERR, "Debes proporcionar una --url o utilizar el modo --demo.");
        printUsage();
        return 1;
    }

    printBanner();
    std::string rawHtml;

    if (runDemo) {
        Logger::log(LogLevel::INFO, "Modo DEMO activado: Cargando pagina de muestra estructurada de K-Drama...");
        rawHtml = HtmlParser::getDemoHtml();
    } else {
        HttpClient client;
        auto response = client.get(targetUrl);
        if (!response.has_value()) {
            Logger::log(LogLevel::ERR, "No se pudo recuperar el HTML de la URL especificada. Proceso detenido.");
            return 1;
        }
        rawHtml = response.value();
    }

    // 2. Limpieza y Parseo
    Logger::log(LogLevel::INFO, "Ejecutando limpieza de etiquetas, ruido HTML y extraccion de episodios...");
    auto episodes = HtmlParser::parseEpisodes(rawHtml);

    if (episodes.empty()) {
        Logger::log(LogLevel::WARN, "No se encontraron episodios estructurados con las expresiones y patrones actuales.");
        return 0;
    }

    Logger::log(LogLevel::SUCCESS, "Se extrajeron con exito " + std::to_string(episodes.size()) + " capitulos.");

    // Vista previa en consola
    std::cout << "\n==================== RESUMEN DE EXTRACCION ====================\n";
    for (const auto& ep : episodes) {
        std::cout << "\n[Capitulo " << ep.episodeNumber << "] " << ep.title << "\n";
        std::cout << "  Sinopsis : " << ep.synopsis << "\n";
        std::cout << "  Puntos Clave / Giros (" << ep.keyConflicts.size() << " detectados):\n";
        if (ep.keyConflicts.empty()) {
            std::cout << "    (Sin giros criticos explicitos detectados)\n";
        } else {
            for (const auto& conflict : ep.keyConflicts) {
                std::cout << "    -> " << conflict << "\n";
            }
        }
    }
    std::cout << "================================================================\n\n";

    // 3. Almacenamiento estructurado
    if (format == "csv" || format == "both") {
        std::string csvPath = outputPrefix + ".csv";
        StorageEngine::saveToCsv(csvPath, episodes);
    }

    if (format == "json" || format == "both") {
        std::string jsonPath = outputPrefix + ".json";
        StorageEngine::saveToJson(jsonPath, episodes);
    }

    Logger::log(LogLevel::SUCCESS, "Proceso finalizado satisfactoriamente.");
    return 0;
}
