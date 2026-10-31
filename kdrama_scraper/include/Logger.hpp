#pragma once
#include <iostream>
#include <string>
#include <chrono>
#include <iomanip>

enum class LogLevel {
    INFO,
    WARN,
    ERR,
    SUCCESS
};

class Logger {
public:
    static void log(LogLevel level, const std::string& msg) {
        auto now = std::chrono::system_clock::now();
        auto in_time = std::chrono::system_clock::to_time_t(now);
        
        std::tm tm_buf;
#if defined(_WIN32) || defined(_WIN64)
        localtime_s(&tm_buf, &in_time);
#else
        localtime_r(&in_time, &tm_buf);
#endif

        std::cout << "[" << std::put_time(&tm_buf, "%H:%M:%S") << "] ";

        switch (level) {
            case LogLevel::INFO:    std::cout << "[INFO]    "; break;
            case LogLevel::WARN:    std::cout << "[WARN]    "; break;
            case LogLevel::ERR:     std::cout << "[ERROR]   "; break;
            case LogLevel::SUCCESS: std::cout << "[SUCCESS] "; break;
        }
        std::cout << msg << std::endl;
    }
};
