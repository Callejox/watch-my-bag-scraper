@echo off
REM Script para ejecutar los tests de integridad de datos en Windows
REM Uso: run_tests.bat [opciones]

echo ==================================================
echo Watch MY Bag Scraper - Tests de Integridad
echo ==================================================
echo.

REM Activar entorno virtual si existe
if exist "venv\Scripts\activate.bat" (
    echo Activando entorno virtual...
    call venv\Scripts\activate.bat
)

REM Verificar que pytest está instalado
python -m pytest --version >nul 2>&1
if errorlevel 1 (
    echo Error: pytest no esta instalado
    echo Instalalo con: pip install -r requirements.txt
    exit /b 1
)

REM Si se pasa --report, solo ejecutar el test de reporte
echo %* | findstr /C:"--report" >nul
if not errorlevel 1 (
    echo Generando reporte de integridad...
    python -m pytest tests/test_data_integrity.py::TestDataIntegrity::test_generate_integrity_report -v -s
    exit /b 0
)

REM Ejecutar tests
echo Ejecutando tests de integridad...
echo.

python -m pytest tests/test_data_integrity.py %*

if errorlevel 1 (
    echo.
    echo Algunos tests fallaron. Revisar los detalles arriba.
    exit /b 1
) else (
    echo.
    echo Todos los tests pasaron correctamente
    exit /b 0
)
