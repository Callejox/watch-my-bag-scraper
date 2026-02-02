@echo off
REM Script para iniciar FlareSolverr con Docker

echo ============================================
echo  INICIANDO FLARESOLVERR
echo ============================================
echo.

REM Verificar si Docker está corriendo
docker info > nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker no está corriendo
    echo.
    echo Por favor inicia Docker Desktop antes de continuar
    echo.
    pause
    exit /b 1
)

echo [OK] Docker está corriendo
echo.

REM Verificar si ya existe el contenedor
docker ps -a --filter name=flaresolverr --format "{{.Names}}" | findstr flaresolverr > nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Contenedor FlareSolverr ya existe, iniciándolo...
    docker start flaresolverr
) else (
    echo [INFO] Creando nuevo contenedor FlareSolverr...
    docker run -d --name flaresolverr -p 8191:8191 --restart unless-stopped ghcr.io/flaresolverr/flaresolverr:latest
)

echo.
echo Esperando 5 segundos para que FlareSolverr inicie...
timeout /t 5 /nobreak > nul

echo.
echo ============================================
echo  VERIFICANDO ESTADO
echo ============================================
echo.

REM Verificar que está corriendo
docker ps --filter name=flaresolverr --format "{{.Status}}" | findstr Up > nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] FlareSolverr está corriendo
    echo [OK] URL: http://localhost:8191
    echo.
    echo Ahora puedes ejecutar el scraper de Chrono24
    echo Comando: py main.py --scrape --chrono24-only
) else (
    echo [ERROR] FlareSolverr no se inició correctamente
    echo.
    echo Ver logs con: docker logs flaresolverr
)

echo.
pause
