#include "StorageEngine.hpp"
#include "Logger.hpp"
#include <fstream>
#include <sstream>

std::string StorageEngine::escapeCsv(const std::string& field) {
    std::string escaped = "\"";
    for (char c : field) {
        if (c == '"') {
            escaped += "\"\"";
        } else {
            escaped += c;
        }
    }
    escaped += "\"";
    return escaped;
}

std::string StorageEngine::escapeJson(const std::string& str) {
    std::ostringstream ss;
    for (char c : str) {
        switch (c) {
            case '"':  ss << "\\\""; break;
            case '\\': ss << "\\\\"; break;
            case '\b': ss << "\\b";  break;
            case '\f': ss << "\\f";  break;
            case '\n': ss << "\\n";  break;
            case '\r': ss << "\\r";  break;
            case '\t': ss << "\\t";  break;
            default:
                if ('\x00' <= c && c <= '\x1f') {
                    // Ignorar caracteres de control inválidos en JSON
                } else {
                    ss << c;
                }
        }
    }
    return ss.str();
}

bool StorageEngine::saveToCsv(const std::string& filePath, const std::vector<DramaEpisode>& episodes) {
    std::ofstream file(filePath, std::ios::out | std::ios::trunc | std::ios::binary);
    if (!file.is_open()) {
        Logger::log(LogLevel::ERR, "No se pudo abrir el archivo para CSV: " + filePath);
        return false;
    }

    // Escribir BOM UTF-8 para compatibilidad perfecta con Excel en Windows
    const unsigned char bom[] = { 0xEF, 0xBB, 0xBF };
    file.write(reinterpret_cast<const char*>(bom), sizeof(bom));

    file << "episode_number,title,synopsis,key_conflicts\r\n";

    for (const auto& ep : episodes) {
        file << ep.episodeNumber << ","
             << escapeCsv(ep.title) << ","
             << escapeCsv(ep.synopsis) << ",";

        std::string conflicts;
        for (size_t i = 0; i < ep.keyConflicts.size(); ++i) {
            conflicts += ep.keyConflicts[i];
            if (i + 1 < ep.keyConflicts.size()) conflicts += " | ";
        }
        file << escapeCsv(conflicts) << "\r\n";
    }

    file.close();
    Logger::log(LogLevel::SUCCESS, "Datos exportados a CSV: " + filePath);
    return true;
}

bool StorageEngine::saveToJson(const std::string& filePath, const std::vector<DramaEpisode>& episodes) {
    std::ofstream file(filePath, std::ios::out | std::ios::trunc);
    if (!file.is_open()) {
        Logger::log(LogLevel::ERR, "No se pudo abrir el archivo para JSON: " + filePath);
        return false;
    }

    file << "[\n";
    for (size_t i = 0; i < episodes.size(); ++i) {
        const auto& ep = episodes[i];
        file << "  {\n"
             << "    \"episode_number\": " << ep.episodeNumber << ",\n"
             << "    \"title\": \"" << escapeJson(ep.title) << "\",\n"
             << "    \"synopsis\": \"" << escapeJson(ep.synopsis) << "\",\n"
             << "    \"key_conflicts\": [\n";

        for (size_t j = 0; j < ep.keyConflicts.size(); ++j) {
            file << "      \"" << escapeJson(ep.keyConflicts[j]) << "\""
                 << (j + 1 < ep.keyConflicts.size() ? "," : "") << "\n";
        }

        file << "    ]\n"
             << "  }" << (i + 1 < episodes.size() ? "," : "") << "\n";
    }
    file << "]\n";

    file.close();
    Logger::log(LogLevel::SUCCESS, "Datos exportados a JSON: " + filePath);
    return true;
}
