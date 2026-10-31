#pragma once
#include "DramaEpisode.hpp"
#include <string>
#include <vector>

class StorageEngine {
public:
    static bool saveToCsv(const std::string& filePath, const std::vector<DramaEpisode>& episodes);
    static bool saveToJson(const std::string& filePath, const std::vector<DramaEpisode>& episodes);

private:
    static std::string escapeCsv(const std::string& field);
    static std::string escapeJson(const std::string& str);
};
