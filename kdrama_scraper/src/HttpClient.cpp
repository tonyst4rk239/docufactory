#include "HttpClient.hpp"
#include "Logger.hpp"

#ifdef USE_CURL
#include <curl/curl.h>

HttpClient::HttpClient()
    : userAgent_("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36") {
    curl_global_init(CURL_GLOBAL_DEFAULT);
}

HttpClient::~HttpClient() {
    curl_global_cleanup();
}

void HttpClient::setUserAgent(const std::string& ua) {
    userAgent_ = ua;
}

void HttpClient::setTimeout(int seconds) {
    timeoutSeconds_ = seconds;
}

static size_t curlWriteCallback(void* contents, size_t size, size_t nmemb, void* userp) {
    size_t total = size * nmemb;
    auto* mem = static_cast<std::string*>(userp);
    mem->append(static_cast<char*>(contents), total);
    return total;
}

std::optional<std::string> HttpClient::get(const std::string& url) {
    CURL* curl = curl_easy_init();
    if (!curl) return std::nullopt;

    std::string response;
    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_USERAGENT, userAgent_.c_str());
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, static_cast<long>(timeoutSeconds_));
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, curlWriteCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);

    Logger::log(LogLevel::INFO, "Conectando via cURL: " + url);
    CURLcode res = curl_easy_perform(curl);
    long httpCode = 0;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &httpCode);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK || httpCode < 200 || httpCode >= 300) {
        Logger::log(LogLevel::ERR, "Petición fallida (HTTP " + std::to_string(httpCode) + ")");
        return std::nullopt;
    }

    return response;
}

#else
// Backend nativo para Windows con WinHTTP (Soporta HTTPS con TLS 1.2/1.3 sin dependencias externas)
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winhttp.h>
#include <vector>
#pragma comment(lib, "winhttp.lib")

static std::wstring toWide(const std::string& str) {
    if (str.empty()) return L"";
    int count = MultiByteToWideChar(CP_UTF8, 0, str.c_str(), static_cast<int>(str.length()), nullptr, 0);
    std::wstring wstr(count, 0);
    MultiByteToWideChar(CP_UTF8, 0, str.c_str(), static_cast<int>(str.length()), &wstr[0], count);
    return wstr;
}

static std::string toUtf8(const std::wstring& wstr) {
    if (wstr.empty()) return "";
    int count = WideCharToMultiByte(CP_UTF8, 0, wstr.c_str(), static_cast<int>(wstr.length()), nullptr, 0, nullptr, nullptr);
    std::string str(count, 0);
    WideCharToMultiByte(CP_UTF8, 0, wstr.c_str(), static_cast<int>(wstr.length()), &str[0], count, nullptr, nullptr);
    return str;
}

HttpClient::HttpClient()
    : userAgent_("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36") {
}

HttpClient::~HttpClient() {
}

void HttpClient::setUserAgent(const std::string& ua) {
    userAgent_ = ua;
}

void HttpClient::setTimeout(int seconds) {
    timeoutSeconds_ = seconds;
}

std::optional<std::string> HttpClient::get(const std::string& url) {
    Logger::log(LogLevel::INFO, "Conectando a: " + url);

    std::wstring wUrl = toWide(url);
    URL_COMPONENTSW urlComp = { 0 };
    urlComp.dwStructSize = sizeof(urlComp);
    urlComp.dwSchemeLength = static_cast<DWORD>(-1);
    urlComp.dwHostNameLength = static_cast<DWORD>(-1);
    urlComp.dwUrlPathLength = static_cast<DWORD>(-1);
    urlComp.dwExtraInfoLength = static_cast<DWORD>(-1);

    if (!WinHttpCrackUrl(wUrl.c_str(), static_cast<DWORD>(wUrl.length()), 0, &urlComp)) {
        Logger::log(LogLevel::ERR, "URL inválida o no se pudo analizar.");
        return std::nullopt;
    }

    std::wstring host(urlComp.lpszHostName, urlComp.dwHostNameLength);
    std::wstring path = (urlComp.dwUrlPathLength > 0) ? std::wstring(urlComp.lpszUrlPath, urlComp.dwUrlPathLength) : L"/";
    if (urlComp.dwExtraInfoLength > 0) {
        path.append(urlComp.lpszExtraInfo, urlComp.dwExtraInfoLength);
    }

    bool isHttps = (urlComp.nScheme == INTERNET_SCHEME_HTTPS);
    INTERNET_PORT port = urlComp.nPort;

    std::wstring wUserAgent = toWide(userAgent_);
    HINTERNET hSession = WinHttpOpen(
        wUserAgent.c_str(),
        WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
        WINHTTP_NO_PROXY_NAME,
        WINHTTP_NO_PROXY_BYPASS,
        0
    );

    if (!hSession) {
        Logger::log(LogLevel::ERR, "Fallo al iniciar sesión WinHTTP.");
        return std::nullopt;
    }

    // Configurar timeouts
    int timeoutMs = timeoutSeconds_ * 1000;
    WinHttpSetTimeouts(hSession, timeoutMs, timeoutMs, timeoutMs, timeoutMs);

    HINTERNET hConnect = WinHttpConnect(hSession, host.c_str(), port, 0);
    if (!hConnect) {
        Logger::log(LogLevel::ERR, "No se pudo conectar al host: " + toUtf8(host));
        WinHttpCloseHandle(hSession);
        return std::nullopt;
    }

    DWORD reqFlags = isHttps ? WINHTTP_FLAG_SECURE : 0;
    HINTERNET hRequest = WinHttpOpenRequest(
        hConnect,
        L"GET",
        path.c_str(),
        nullptr,
        WINHTTP_NO_REFERER,
        WINHTTP_DEFAULT_ACCEPT_TYPES,
        reqFlags
    );

    if (!hRequest) {
        Logger::log(LogLevel::ERR, "Fallo al crear la petición HTTP.");
        WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession);
        return std::nullopt;
    }

    // Enviar petición
    BOOL bResults = WinHttpSendRequest(
        hRequest,
        WINHTTP_NO_ADDITIONAL_HEADERS,
        0,
        WINHTTP_NO_REQUEST_DATA,
        0,
        0,
        0
    );

    if (bResults) {
        bResults = WinHttpReceiveResponse(hRequest, nullptr);
    }

    if (!bResults) {
        Logger::log(LogLevel::ERR, "Fallo al recibir respuesta HTTP. Error: " + std::to_string(GetLastError()));
        WinHttpCloseHandle(hRequest);
        WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession);
        return std::nullopt;
    }

    // Verificar código HTTP
    DWORD statusCode = 0;
    DWORD statusCodeSize = sizeof(statusCode);
    WinHttpQueryHeaders(
        hRequest,
        WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
        WINHTTP_HEADER_NAME_BY_INDEX,
        &statusCode,
        &statusCodeSize,
        WINHTTP_NO_HEADER_INDEX
    );

    if (statusCode < 200 || statusCode >= 300) {
        Logger::log(LogLevel::WARN, "Código HTTP recibido: " + std::to_string(statusCode));
        WinHttpCloseHandle(hRequest);
        WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession);
        return std::nullopt;
    }

    // Leer respuesta
    std::string responseBody;
    DWORD dwSize = 0;
    DWORD dwDownloaded = 0;

    do {
        dwSize = 0;
        if (!WinHttpQueryDataAvailable(hRequest, &dwSize)) {
            break;
        }

        if (dwSize == 0) break;

        std::vector<char> buffer(dwSize);
        if (WinHttpReadData(hRequest, buffer.data(), dwSize, &dwDownloaded)) {
            responseBody.append(buffer.data(), dwDownloaded);
        } else {
            break;
        }
    } while (dwSize > 0);

    WinHttpCloseHandle(hRequest);
    WinHttpCloseHandle(hConnect);
    WinHttpCloseHandle(hSession);

    Logger::log(LogLevel::SUCCESS, "HTML descargado exitosamente (" + std::to_string(responseBody.size()) + " bytes).");
    return responseBody;
}
#endif
