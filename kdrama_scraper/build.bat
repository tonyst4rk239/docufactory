@echo off
setlocal

echo =======================================================
echo Compilando Motor de Scraping K-Drama (C++17 MSVC)
echo =======================================================

call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" x64
if errorlevel 1 (
    echo Error al inicializar entorno MSVC.
    exit /b 1
)

if not exist bin mkdir bin

cl.exe /std:c++17 /O2 /W3 /EHsc /utf-8 /Iinclude ^
    src\main.cpp src\HttpClient.cpp src\HtmlParser.cpp src\StorageEngine.cpp ^
    /Fe:bin\kdrama_scraper.exe ^
    /link winhttp.lib

if errorlevel 1 (
    echo [ERROR] Fallo en la compilacion.
    exit /b 1
)

echo.
echo [EXITO] Compilacion completada. Binario en bin\kdrama_scraper.exe
echo =======================================================
