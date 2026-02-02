@echo off
REM ============================================================
REM  Watch MY Bag - Flujo de Trabajo Automatizado
REM ============================================================
REM
REM Script orquestador que ejecuta el flujo completo:
REM 1. Verificar requisitos (Python, Docker)
REM 2. Ejecutar: py main.py --workflow
REM 3. Mostrar resultados
REM
REM Uso:
REM   run_workflow.bat              # Flujo completo
REM   run_workflow.bat --test-mode  # Modo prueba (1 página)
REM   run_workflow.bat --chrono24-only  # Solo Chrono24
REM   run_workflow.bat --skip-report    # Sin generar reporte
REM
REM ============================================================

echo.
echo ============================================================
echo   Watch MY Bag - Flujo Automatizado de Scraping
echo ============================================================
echo.

REM Verificar Python
py --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python no encontrado
    echo.
    echo Instala Python 3.9+ desde: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Verificar Docker Desktop
echo [1/3] Verificando Docker Desktop...
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker Desktop no esta corriendo
    echo.
    echo Por favor:
    echo 1. Abre Docker Desktop desde el menu de inicio
    echo 2. Espera a que este completamente iniciado
    echo 3. Vuelve a ejecutar este script
    echo.
    pause
    exit /b 1
)
echo [OK] Docker Desktop esta corriendo
echo.

REM Ejecutar workflow
echo [2/3] Ejecutando workflow automatizado...
echo.
py main.py --workflow %*

REM Capturar exit code
set WORKFLOW_EXIT=%errorlevel%

echo.
echo [3/3] Workflow finalizado
echo.

if %WORKFLOW_EXIT% equ 0 (
    echo ============================================================
    echo [OK] Workflow completado exitosamente
    echo ============================================================
) else (
    echo ============================================================
    echo [ERROR] Workflow fallo con codigo: %WORKFLOW_EXIT%
    echo ============================================================
    echo.
    echo Revisa los logs en: logs\scraper_%date:~-4,4%-%date:~-7,2%-%date:~-10,2%.log
)

echo.
pause

exit /b %WORKFLOW_EXIT%
