#!/bin/bash

# Script para ejecutar los tests de integridad de datos
# Uso: ./run_tests.sh [opciones]
#
# Ejemplos:
#   ./run_tests.sh                    # Ejecutar todos los tests
#   ./run_tests.sh -v                 # Modo verbose
#   ./run_tests.sh -k "duplicate"     # Solo tests de duplicados
#   ./run_tests.sh --report           # Solo generar reporte

echo "=================================================="
echo "Watch MY Bag Scraper - Tests de Integridad"
echo "=================================================="
echo ""

# Activar entorno virtual si existe
if [ -d "venv" ]; then
    echo "✓ Activando entorno virtual..."
    source venv/bin/activate
fi

# Verificar que pytest está instalado
if ! command -v pytest &> /dev/null; then
    echo "❌ Error: pytest no está instalado"
    echo "Instálalo con: pip install -r requirements.txt"
    exit 1
fi

# Si se pasa --report, solo ejecutar el test de reporte
if [[ "$*" == *"--report"* ]]; then
    echo "📊 Generando reporte de integridad..."
    python -m pytest tests/test_data_integrity.py::TestDataIntegrity::test_generate_integrity_report -v -s
    exit 0
fi

# Ejecutar tests
echo "🧪 Ejecutando tests de integridad..."
echo ""

# Pasar todos los argumentos a pytest
python -m pytest tests/test_data_integrity.py "$@"

# Capturar el código de salida
EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Todos los tests pasaron correctamente"
else
    echo "❌ Algunos tests fallaron. Revisar los detalles arriba."
fi

exit $EXIT_CODE
