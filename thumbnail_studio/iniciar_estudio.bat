@echo off
title Cinematic YouTube Thumbnail Studio
cd /d "%~dp0"
echo ========================================================
echo   Iniciando Cinematic YouTube Thumbnail Studio...
echo ========================================================
start http://localhost:3000
call npm.cmd run dev
pause
