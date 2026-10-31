#pragma once
#include <string>
#include <vector>

struct DramaEpisode {
    int episodeNumber = 0;
    std::string title;
    std::string synopsis;
    std::vector<std::string> keyConflicts; // Puntos de quiebre dramático y giros de trama
};
