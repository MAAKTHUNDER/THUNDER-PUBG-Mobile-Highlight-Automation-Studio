@echo off
setlocal enabledelayedexpansion
title THUNDER - PUBG Mobile Highlight Automation Studio
cd /d "%~dp0"

echo =========================================================================
echo    THUNDER STUDIO - PUBG MOBILE HIGHLIGHT AUTOMATION STUDIO
echo    Official Client of MAAKTHUNDER Studios (c) 2026
echo =========================================================================
echo.

:: 1. Search for Python executable
set "PYTHON_EXE="

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "PYTHON_EXE=python"
    goto :found_python
)

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "PYTHON_EXE=py"
    goto :found_python
)

if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    goto :found_python
)

if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto :found_python
)

if exist "C:\Python312\python.exe" (
    set "PYTHON_EXE=C:\Python312\python.exe"
    goto :found_python
)

if exist "C:\Python311\python.exe" (
    set "PYTHON_EXE=C:\Python311\python.exe"
    goto :found_python
)

echo [!] Python 3.10+ was not automatically found on your computer.
echo [*] Please install Python from https://www.python.org/downloads/
echo     Be sure to check "Add Python to PATH" during installation.
echo.
pause
exit /b 1

:found_python
echo [*] Starting THUNDER Studio...
"%PYTHON_EXE%" thunder_web_app.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo =========================================================================
    echo [!] THUNDER Studio exited with return code %ERRORLEVEL%.
    echo     If packages are missing, run: pip install -r requirements.txt
    echo =========================================================================
    pause
)
