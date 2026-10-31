cmake_minimum_required(VERSION 3.16)
project(KDramaScraper LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include_directories(include)

set(SOURCES
    src/main.cpp
    src/HttpClient.cpp
    src/HtmlParser.cpp
    src/StorageEngine.cpp
)

add_executable(kdrama_scraper ${SOURCES})

if(WIN32)
    # En Windows enlazamos directamente con WinHTTP nativo
    target_link_libraries(kdrama_scraper PRIVATE winhttp)
    if(MSVC)
        target_compile_options(kdrama_scraper PRIVATE "/utf-8" "/W3" "/O2")
    endif()
else()
    # En Linux / macOS usa libcurl
    find_package(CURL REQUIRED)
    target_compile_definitions(kdrama_scraper PRIVATE USE_CURL)
    target_link_libraries(kdrama_scraper PRIVATE CURL::libcurl)
endif()
