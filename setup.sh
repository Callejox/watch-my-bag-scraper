#!/bin/bash
# =============================================================================
# Watch MY Bag Scraper - Script de Configuración Inicial
# =============================================================================
# Este script crea todos los directorios necesarios e inicializa la aplicación.
# Ejecutar una sola vez antes de usar la aplicación.
# =============================================================================

set -e  # Salir si hay algún error

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # Sin color

# Banner
echo -e "${BLUE}"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║                                                               ║"
echo "║             ⌚ WATCH MY BAG SCRAPER ⌚                        ║"
echo "║                                                               ║"
echo "║         Monitoreo de relojes en marketplaces                  ║"
echo "║                                                               ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Función para imprimir mensajes
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[i]${NC} $1"
}

# Obtener directorio del script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
print_info "Directorio de trabajo: $SCRIPT_DIR"
echo ""

# =============================================================================
# 1. Crear estructura de directorios
# =============================================================================
echo -e "${YELLOW}━━━ Paso 1: Creando directorios ━━━${NC}"

mkdir -p data/exports
mkdir -p data/images
mkdir -p logs

print_status "data/          - Directorio de datos"
print_status "data/exports/  - Reportes Excel exportados"
print_status "data/images/   - Imágenes descargadas"
print_status "logs/          - Archivos de log"

echo ""

# =============================================================================
# 2. Verificar archivos necesarios
# =============================================================================
echo -e "${YELLOW}━━━ Paso 2: Verificando archivos ━━━${NC}"

REQUIRED_FILES=("main.py" "dashboard.py" "config.py" "requirements.txt")
MISSING_FILES=()

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        print_status "$file encontrado"
    else
        print_error "$file NO encontrado"
        MISSING_FILES+=("$file")
    fi
done

if [ ${#MISSING_FILES[@]} -gt 0 ]; then
    echo ""
    print_error "Faltan archivos necesarios. Asegúrate de tener todos los archivos del proyecto."
    exit 1
fi

echo ""

# =============================================================================
# 3. Detectar método de ejecución (Docker o Local)
# =============================================================================
echo -e "${YELLOW}━━━ Paso 3: Detectando entorno ━━━${NC}"

USE_DOCKER=false

if command -v docker &> /dev/null && command -v docker-compose &> /dev/null; then
    print_status "Docker y Docker Compose detectados"
    USE_DOCKER=true
elif command -v docker &> /dev/null && docker compose version &> /dev/null; then
    print_status "Docker con Compose plugin detectado"
    USE_DOCKER=true
else
    print_warning "Docker no detectado - se usará instalación local"
fi

echo ""

# =============================================================================
# 4. Inicializar según el entorno
# =============================================================================
if [ "$USE_DOCKER" = true ]; then
    echo -e "${YELLOW}━━━ Paso 4: Configurando Docker ━━━${NC}"

    print_info "Construyendo imagen Docker (esto puede tardar varios minutos)..."

    if docker compose version &> /dev/null 2>&1; then
        # Docker Compose V2 (plugin)
        docker compose build
        print_status "Imagen Docker construida"

        print_info "Inicializando base de datos..."
        docker compose --profile init run --rm init
        print_status "Base de datos inicializada"
    else
        # Docker Compose V1 (standalone)
        docker-compose build
        print_status "Imagen Docker construida"

        print_info "Inicializando base de datos..."
        docker-compose --profile init run --rm init
        print_status "Base de datos inicializada"
    fi

else
    echo -e "${YELLOW}━━━ Paso 4: Configurando entorno local ━━━${NC}"

    # Verificar Python
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        print_error "Python no encontrado. Instala Python 3.9 o superior."
        exit 1
    fi

    PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
    print_status "Python detectado: $PYTHON_VERSION"

    # Crear entorno virtual si no existe
    if [ ! -d "venv" ]; then
        print_info "Creando entorno virtual..."
        $PYTHON_CMD -m venv venv
        print_status "Entorno virtual creado"
    else
        print_status "Entorno virtual ya existe"
    fi

    # Activar entorno virtual
    print_info "Activando entorno virtual..."
    source venv/bin/activate

    # Instalar dependencias
    print_info "Instalando dependencias (esto puede tardar)..."
    pip install --upgrade pip > /dev/null 2>&1
    pip install -r requirements.txt > /dev/null 2>&1
    print_status "Dependencias instaladas"

    # Instalar Playwright browsers
    print_info "Instalando navegador para scraping..."
    playwright install chromium > /dev/null 2>&1
    print_status "Navegador Chromium instalado"

    # Inicializar base de datos
    print_info "Inicializando base de datos..."
    $PYTHON_CMD main.py --init
    print_status "Base de datos inicializada"
fi

echo ""

# =============================================================================
# 5. Mostrar instrucciones finales
# =============================================================================
echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║              ✅ CONFIGURACIÓN COMPLETADA ✅                   ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo ""
echo -e "${BLUE}📋 PRÓXIMOS PASOS:${NC}"
echo ""

if [ "$USE_DOCKER" = true ]; then
    echo "1. Edita config.py para configurar los modelos y vendedores a seguir"
    echo ""
    echo "2. Ejecuta el scraper para obtener datos:"
    echo -e "   ${YELLOW}docker compose --profile scrape run --rm scraper${NC}"
    echo ""
    echo "3. Inicia el dashboard para ver los resultados:"
    echo -e "   ${YELLOW}docker compose up dashboard${NC}"
    echo ""
    echo "4. Abre el navegador en: http://localhost:8501"
    echo ""
    echo "5. Para generar un reporte Excel:"
    echo -e "   ${YELLOW}docker compose --profile report run --rm report${NC}"
else
    echo "1. Activa el entorno virtual:"
    echo -e "   ${YELLOW}source venv/bin/activate${NC}"
    echo ""
    echo "2. Edita config.py para configurar los modelos y vendedores a seguir"
    echo ""
    echo "3. Ejecuta el scraper para obtener datos:"
    echo -e "   ${YELLOW}python main.py --scrape${NC}"
    echo ""
    echo "4. Inicia el dashboard para ver los resultados:"
    echo -e "   ${YELLOW}streamlit run dashboard.py${NC}"
    echo ""
    echo "5. Abre el navegador en: http://localhost:8501"
    echo ""
    echo "6. Para generar un reporte Excel:"
    echo -e "   ${YELLOW}python main.py --report${NC}"
fi

echo ""
echo -e "${BLUE}📖 Para más información, consulta el archivo README.md${NC}"
echo ""
