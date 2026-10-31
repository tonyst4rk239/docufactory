#pragma once
#include <string>
#include <optional>

class HttpClient {
public:
    HttpClient();
    ~HttpClient();

    void setUserAgent(const std::string& ua);
    void setTimeout(int seconds);
    std::optional<std::string> get(const std::string& url);

private:
    std::string userAgent_;
    int timeoutSeconds_ = 15;
};
