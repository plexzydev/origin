@echo off
title Origin Network - Panel de Control
color 0b
echo.
echo   ===================================
echo    Origin Network - Panel de Control
echo   ===================================
echo.
echo   [1] Iniciar Proxy (Velocity)
echo   [2] Iniciar Lobby Server
echo   [3] Iniciar Prision Gens Server
echo   [4] Iniciar TODO
echo   [5] Salir
echo.
set /p choice="  Opcion: "

if "%choice%"=="1" goto proxy
if "%choice%"=="2" goto lobby
if "%choice%"=="3" goto prisongens
if "%choice%"=="4" goto all
if "%choice%"=="5" exit

:proxy
start "Velocity Proxy" cmd /c "cd /d "%~dp0proxy" && start.bat"
goto end

:lobby
start "Lobby Server" cmd /c "cd /d "%~dp0servers\lobby" && start.bat"
goto end

:prisongens
start "PrisionGens Server" cmd /c "cd /d "%~dp0servers\prisongens" && start.bat"
goto end

:all
echo  [1/3] Proxy...
start "Velocity Proxy" cmd /c "cd /d "%~dp0proxy" && start.bat"
timeout /t 5 /nobreak > nul
echo  [2/3] Lobby...
start "Lobby Server" cmd /c "cd /d "%~dp0servers\lobby" && start.bat"
timeout /t 3 /nobreak > nul
echo  [3/3] Prision Gens...
start "PrisionGens Server" cmd /c "cd /d "%~dp0servers\prisongens" && start.bat"
echo.
echo  Todo iniciado! Conectate a localhost:25565
goto end

:end
echo.
pause
