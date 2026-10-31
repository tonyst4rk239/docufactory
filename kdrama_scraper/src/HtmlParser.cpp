#include "HtmlParser.hpp"
#include <sstream>
#include <algorithm>
#include <cctype>

std::string HtmlParser::decodeEntities(std::string text) {
    struct Entity { const char* code; const char* val; };
    static const Entity entities[] = {
        {"&amp;", "&"}, {"&lt;", "<"}, {"&gt;", ">"},
        {"&quot;", "\""}, {"&#39;", "'"}, {"&apos;", "'"},
        {"&nbsp;", " "}, {"&aacute;", "á"}, {"&eacute;", "é"},
        {"&iacute;", "í"}, {"&oacute;", "ó"}, {"&uacute;", "ú"},
        {"&ntilde;", "ñ"}, {"&Aacute;", "Á"}, {"&Eacute;", "É"},
        {"&Iacute;", "Í"}, {"&Oacute;", "Ó"}, {"&Uacute;", "Ú"},
        {"&Ntilde;", "Ñ"}, {"&#160;", " "}
    };

    for (const auto& [code, val] : entities) {
        size_t pos = 0;
        size_t len = std::string(code).length();
        while ((pos = text.find(code, pos)) != std::string::npos) {
            text.replace(pos, len, val);
            pos += std::string(val).length();
        }
    }
    return text;
}

// O(N) Iterative tag and noise stripper (evita stack-overflow de std::regex en HTMLs de varios megabytes)
std::string HtmlParser::stripNoiseAndTags(std::string html) {
    std::string out;
    out.reserve(html.size() / 2);

    size_t i = 0;
    const size_t n = html.size();

    auto caseInsensitiveMatch = [&](size_t idx, const std::string& pattern) {
        if (idx + pattern.size() > n) return false;
        for (size_t p = 0; p < pattern.size(); ++p) {
            if (std::tolower(static_cast<unsigned char>(html[idx + p])) != 
                std::tolower(static_cast<unsigned char>(pattern[p]))) {
                return false;
            }
        }
        return true;
    };

    while (i < n) {
        // Ignorar comentarios HTML <!-- ... -->
        if (caseInsensitiveMatch(i, "<!--")) {
            size_t endComment = html.find("-->", i + 4);
            if (endComment == std::string::npos) break;
            i = endComment + 3;
            continue;
        }

        // Ignorar bloques <script>...</script>
        if (caseInsensitiveMatch(i, "<script")) {
            size_t endTag = html.find(">", i);
            if (endTag == std::string::npos) break;
            size_t endScript = html.find("</script>", endTag);
            if (endScript == std::string::npos) {
                endScript = html.find("</SCRIPT>", endTag);
            }
            if (endScript == std::string::npos) break;
            i = endScript + 9;
            out += " ";
            continue;
        }

        // Ignorar bloques <style>...</style>
        if (caseInsensitiveMatch(i, "<style")) {
            size_t endTag = html.find(">", i);
            if (endTag == std::string::npos) break;
            size_t endStyle = html.find("</style>", endTag);
            if (endStyle == std::string::npos) {
                endStyle = html.find("</STYLE>", endTag);
            }
            if (endStyle == std::string::npos) break;
            i = endStyle + 8;
            out += " ";
            continue;
        }

        // Reemplazar saltos de bloque comunes por saltos de línea
        if (caseInsensitiveMatch(i, "</p>") || caseInsensitiveMatch(i, "</div>") ||
            caseInsensitiveMatch(i, "</li>") || caseInsensitiveMatch(i, "</tr>") ||
            caseInsensitiveMatch(i, "<br>") || caseInsensitiveMatch(i, "<br/>")) {
            out += "\n";
        }

        // Si es apertura de etiqueta '<', avanzar hasta '>'
        if (html[i] == '<') {
            size_t tagClose = html.find('>', i);
            if (tagClose == std::string::npos) break;
            i = tagClose + 1;
            continue;
        }

        out += html[i];
        ++i;
    }

    return decodeEntities(out);
}

std::string HtmlParser::cleanWhitespace(std::string text) {
    std::string result;
    result.reserve(text.size());

    bool inSpace = false;
    for (char c : text) {
        if (c == '\r') continue;
        if (c == ' ' || c == '\t') {
            if (!inSpace) {
                result += ' ';
                inSpace = true;
            }
        } else if (c == '\n') {
            if (!result.empty() && result.back() != '\n') {
                result += '\n';
            }
            inSpace = false;
        } else {
            result += c;
            inSpace = false;
        }
    }

    // Trim inicio y final
    size_t first = result.find_first_not_of(" \n");
    if (first == std::string::npos) return "";
    size_t last = result.find_last_not_of(" \n");
    return result.substr(first, (last - first + 1));
}

std::vector<std::string> HtmlParser::extractKeyConflicts(const std::string& text) {
    std::vector<std::string> conflicts;
    static const std::vector<std::string> triggers = {
        "sin embargo", "de repente", "traición", "accidente", "confronta",
        "secreta", "secreto", "revela", "pero", "conflicto", "disputa", "muerte",
        "sospecha", "venganza", "descubre", "amenaza", "desaparición", "arrest",
        "however", "suddenly", "betrayal", "accident", "confronts", "secret",
        "reveals", "conflict", "death", "suspects", "revenge", "discovers",
        "threat", "announces", "disaster", "danger", "murders", "killed", "arrested"
    };

    std::stringstream ss(text);
    std::string sentence;
    while (std::getline(ss, sentence, '.')) {
        std::string lower = sentence;
        std::transform(lower.begin(), lower.end(), lower.begin(), [](unsigned char c) {
            return static_cast<char>(std::tolower(c));
        });

        for (const auto& trig : triggers) {
            if (lower.find(trig) != std::string::npos) {
                std::string cleaned = cleanWhitespace(sentence);
                if (cleaned.length() > 20) {
                    conflicts.push_back(cleaned);
                    break;
                }
            }
        }
    }
    return conflicts;
}

std::vector<DramaEpisode> HtmlParser::parseEpisodes(const std::string& rawHtml) {
    std::vector<DramaEpisode> episodes;

    // Estrategia 1: Formato de tablas de episodios (Wikipedia, Fandom, wikis de series)
    // Busca: <td class="description">...</td>
    const std::string tagStart = "<td class=\"description\"";
    size_t pos = 0;
    int epCounter = 1;

    while ((pos = rawHtml.find(tagStart, pos)) != std::string::npos) {
        size_t contentStart = rawHtml.find('>', pos);
        if (contentStart == std::string::npos) break;
        contentStart += 1;

        size_t contentEnd = rawHtml.find("</td>", contentStart);
        if (contentEnd == std::string::npos) break;

        std::string cellHtml = rawHtml.substr(contentStart, contentEnd - contentStart);
        std::string cleanSynopsis = cleanWhitespace(stripNoiseAndTags(cellHtml));

        if (!cleanSynopsis.empty()) {
            DramaEpisode ep;
            ep.episodeNumber = epCounter++;
            ep.title = "Episodio " + std::to_string(ep.episodeNumber);
            ep.synopsis = cleanSynopsis;
            ep.keyConflicts = extractKeyConflicts(ep.synopsis);
            episodes.push_back(ep);
        }

        pos = contentEnd + 5;
    }

    if (!episodes.empty()) {
        return episodes;
    }

    // Estrategia 2: Heurística por encabezados de capítulos (Blogs, páginas de sinopsis)
    // Busca patrones tipo: <h3>Capítulo 1: ...</h3> o similares
    size_t searchPos = 0;
    while (searchPos < rawHtml.size()) {
        size_t hPos = rawHtml.find("<h", searchPos);
        if (hPos == std::string::npos) break;

        // Comprobar que sea h2, h3 o h4
        if (hPos + 3 < rawHtml.size() && (rawHtml[hPos+2] >= '2' && rawHtml[hPos+2] <= '4')) {
            size_t hClose = rawHtml.find('>', hPos);
            size_t hEnd = rawHtml.find("</h", hClose);
            if (hClose != std::string::npos && hEnd != std::string::npos) {
                std::string headerText = rawHtml.substr(hClose + 1, hEnd - hClose - 1);
                std::string lowerH = headerText;
                std::transform(lowerH.begin(), lowerH.end(), lowerH.begin(), [](unsigned char c) {
                    return static_cast<char>(std::tolower(c));
                });

                if (lowerH.find("episod") != std::string::npos || lowerH.find("capit") != std::string::npos || lowerH.find("capít") != std::string::npos) {
                    DramaEpisode ep;
                    ep.title = cleanWhitespace(stripNoiseAndTags(headerText));
                    ep.episodeNumber = ++epCounter;

                    // Buscar el párrafo subsiguiente
                    size_t pStart = rawHtml.find("<p", hEnd);
                    if (pStart != std::string::npos && pStart < hEnd + 500) {
                        size_t pContent = rawHtml.find('>', pStart);
                        size_t pEnd = rawHtml.find("</p>", pContent);
                        if (pContent != std::string::npos && pEnd != std::string::npos) {
                            std::string pRaw = rawHtml.substr(pContent + 1, pEnd - pContent - 1);
                            ep.synopsis = cleanWhitespace(stripNoiseAndTags(pRaw));
                            ep.keyConflicts = extractKeyConflicts(ep.synopsis);
                            episodes.push_back(ep);
                            searchPos = pEnd + 4;
                            continue;
                        }
                    }
                }
            }
        }
        searchPos = hPos + 2;
    }

    return episodes;
}

std::string HtmlParser::getDemoHtml() {
    return R"(
<!DOCTYPE html>
<html lang="es">
<head>
    <title>Resumen K-Drama: Sombras de Seúl</title>
    <style>body { font-family: sans-serif; }</style>
    <script>console.log("Tracker");</script>
</head>
<body>
    <header><h1>Sombras de Seúl</h1></header>
    <main>
        <h3>Episodio 1: El Regreso del Fiscal</h3>
        <p>Min-jun regresa a Seúl después de tres años en el extranjero para investigar la misteriosa muerte de su mentor. Sin embargo, en su primer día descubre que los expedientes oficiales fueron destruidos. Una sospecha recae sobre el nuevo fiscal general mientras una llamada anónima le advierte sobre una traición inminente en su propio equipo.</p>

        <h3>Episodio 2: Cenizas del Pasado</h3>
        <p>La abogada defensora Seo-yeon se une a la investigación tras el brutal ataque a su bufete. De repente, una pista oculta en una cámara de seguridad revela la presencia de un automóvil de lujo perteneciente al conglomerado Daesung. Min-jun confronta al heredero corporativo, pero este niega conocer los hechos antes de sufrir un sospechoso accidente vehicular.</p>

        <h3>Episodio 3: Pacto de Silencio</h3>
        <p>Con el testigo clave en coma, Min-jun y Seo-yeon descubren una red de corrupción financiera de proporciones masivas. La familia del fiscal general exige el cierre inmediato del caso. La tensión aumenta cuando se revela que el hermano menor de Seo-yeon mantenía una deuda secreta con el principal sospechoso, desatando una dolorosa ruptura en la alianza.</p>
    </main>
</body>
</html>
)";
}
