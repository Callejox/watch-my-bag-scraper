"""
Configuración del proyecto de scraping.
Modifica estos valores según tus necesidades.
"""

import os
from pathlib import Path

# =============================================================================
# RUTAS DEL PROYECTO
# =============================================================================
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
EXPORTS_DIR = DATA_DIR / "exports"
IMAGES_DIR = DATA_DIR / "images"

# Base de datos SQLite
DATABASE_PATH = DATA_DIR / "inventory.db"

# =============================================================================
# CONFIGURACIÓN DE IMÁGENES
# =============================================================================
# Descargar imágenes localmente (True/False)
DOWNLOAD_IMAGES = True
# Máximo ancho de imagen en píxeles (para reducir tamaño)
IMAGE_MAX_WIDTH = 800

# =============================================================================
# CHRONO24 - MODELOS A RASTREAR
# =============================================================================
# Lista de modelos genéricos para buscar en Chrono24
# Puedes añadir o quitar modelos según necesites
CHRONO24_MODELS = [
    "Omega de ville",
    "Hermès Arceau",
    "Omega seamaster",
]

# Países a excluir de Chrono24
CHRONO24_EXCLUDE_COUNTRIES = [
    "Japón",
    "Japan",
    "JP",  # Código de país
]

# Configuración de paginación de Chrono24
CHRONO24_PAGE_SIZE = 120  # Items por página (30, 60, o 120)
CHRONO24_MAX_PAGES = 0    # Máximo de páginas por modelo (0 = todas las páginas)

# =============================================================================
# FLARESOLVERR - BYPASS CLOUDFLARE
# =============================================================================
# Habilitar FlareSolverr para Chrono24 (requiere Docker corriendo)
USE_FLARESOLVERR = True
# URL del servicio FlareSolverr (Docker en localhost:8191 por defecto)
FLARESOLVERR_URL = "http://localhost:8191/v1"
# Timeout para FlareSolverr en segundos
FLARESOLVERR_TIMEOUT = 60

# =============================================================================
# PAGINACIÓN - Validación y límites
# =============================================================================

# Vestiaire: Máximo de páginas por vendedor (0 = todas, N = límite)
VESTIAIRE_MAX_PAGES_DEFAULT = 20  # Aumentado de 10 a 20 como límite de seguridad

# Tolerancia para validación de items (±N items es aceptable)
CHRONO24_PAGINATION_TOLERANCE = 120  # ±120 items
VESTIAIRE_PAGINATION_TOLERANCE = 60  # ±60 items

# Número de reintentos para páginas que fallan
PAGINATION_RETRY_COUNT = 3  # Reintentar 3 veces antes de saltar/detener

# Comportamiento ante fallo consecutivo: si página N y N+1 fallan, detener scraping
PAGINATION_STOP_ON_CONSECUTIVE_FAILURES = True

# =============================================================================
# VESTIAIRE COLLECTIVE - VENDEDORES A SEGUIR
# =============================================================================
# IDs de vendedores específicos para monitorear
# Reemplaza estos valores con los IDs reales de los vendedores
VESTIAIRE_SELLER_IDS = [
    "3022988",  # TODO: Reemplazar con ID real
    #"10125453",  # TODO: Reemplazar con ID real
    #"8642167",  # TODO: Reemplazar con ID real
 
    # Puedes añadir hasta 6 vendedores
]

# =============================================================================
# CONFIGURACIÓN DEL SCRAPER
# =============================================================================
# Delays entre requests (en segundos) - para evitar bloqueos
REQUEST_DELAY_MIN = 2.0
REQUEST_DELAY_MAX = 5.0

# Número máximo de reintentos por request
MAX_RETRIES = 3

# Timeout para carga de páginas (en milisegundos)
PAGE_TIMEOUT = 30000

# User agents rotativos
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

# =============================================================================
# CONFIGURACIÓN DE LOGGING
# =============================================================================
LOG_LEVEL = "INFO"
LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
LOG_ROTATION = "1 day"
LOG_RETENTION = "30 days"

# =============================================================================
# CATAWIKI - CONFIGURACIÓN
# =============================================================================
# Catawiki usa los mismos modelos que Chrono24
# Si quieres modelos diferentes, descomenta y modifica la lista
# CATAWIKI_MODELS = [
#     "Omega de ville",
#     "Hermès Arceau",
# ]

# Por defecto usa los mismos modelos que CHRONO24_MODELS
# NOTA: Catawiki tiene protección anti-bot muy agresiva que bloquea búsquedas.
# Desactivado temporalmente hasta encontrar una solución robusta.
# Opciones futuras: proxies residenciales, API oficial, o scraping manual.
CATAWIKI_ENABLED = False  # Activar/desactivar scraping de Catawiki

# =============================================================================
# CATAWIKI - FLARESOLVERR Y PAGINACIÓN
# =============================================================================

# Usar FlareSolverr para Catawiki (mismo servicio que Chrono24)
CATAWIKI_USE_FLARESOLVERR = True

# Configuración de paginación de Catawiki
CATAWIKI_MAX_PAGES_DEFAULT = 5  # Páginas por modelo (0 = todas, N = límite)
CATAWIKI_PAGINATION_TOLERANCE = 100  # ±100 items aceptable en validación

# =============================================================================
# URLs BASE
# =============================================================================
CHRONO24_BASE_URL = "https://www.chrono24.es"
VESTIAIRE_BASE_URL = "https://es.vestiairecollective.com"
CATAWIKI_BASE_URL = "https://www.catawiki.com"

# =============================================================================
# WORKFLOW - Automatización
# =============================================================================

# Timeout para verificación de Docker (segundos)
DOCKER_VERIFY_TIMEOUT = 5

# Timeout para inicio de FlareSolverr (segundos)
FLARESOLVERR_STARTUP_TIMEOUT = 15

# Generar reporte siempre (incluso sin ventas nuevas)
WORKFLOW_REPORT_ALWAYS = False
