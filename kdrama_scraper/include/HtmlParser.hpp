#pragma once
#include "DramaEpisode.hpp"
#include <string>
#include <vector>

class HtmlParser {
public:
    static std::string stripNoiseAndTags(std::string html);
    static std::string decodeEntities(std::string text);
    static std::string cleanWhitespace(std::string text);

    // Parsea los episodios desde el HTML completo
    static std::vector<DramaEpisode> parseEpisodes(const std::string& rawHtml);

    // Genera un HTML de demostración con tramas de un K-Drama para pruebas locales
    static std::string getDemoHtml();

private:
    static std::vector<std::string> extractKeyConflicts(const std::string& text);
};
