# Watch MY Bag Scraper

Aplicación de monitoreo y scraping de relojes en marketplaces online (Chrono24, Vestiaire Collective, Catawiki).

Detecta automáticamente ventas comparando inventarios diarios y proporciona un dashboard interactivo para visualizar los datos.

---

## Requisitos Previos

### Opción A: Docker (Recomendado)
- Docker Desktop instalado
- Docker Compose

### Opción B: Instalación Local
- Python 3.9 o superior
- pip (gestor de paquetes de Python)

---

## Instalación Rápida

### 1. Descargar el proyecto

```bash
# Clonar o copiar el proyecto a tu máquina
cd /ruta/donde/quieras/el/proyecto
```

### 2. Ejecutar el script de configuración

```bash
# Dar permisos de ejecución (solo la primera vez)
chmod +x setup.sh

# Ejecutar configuración inicial
./setup.sh
```

El script automáticamente:
- Crea los directorios necesarios (`data/`, `logs/`, `data/exports/`, `data/images/`)
- Detecta si tienes Docker o necesitas instalación local
- Instala las dependencias
- Inicializa la base de datos

---

## Uso con Docker (Recomendado)

### Comandos principales

```bash
# 1. INICIALIZAR (solo la primera vez)
docker compose --profile init run --rm init

# 2. EJECUTAR SCRAPER (obtener datos de los marketplaces)
docker compose --profile scrape run --rm scraper

# 3. INICIAR DASHBOARD (visualizar datos)
docker compose up dashboard
# Luego abre: http://localhost:8501

# 4. GENERAR REPORTE EXCEL
docker compose --profile report run --rm report

# 5. DETENER TODO
docker compose down
```

### Ver logs

```bash
# Ver logs del dashboard
docker compose logs -f dashboard

# Ver logs del scraper
docker compose --profile scrape logs scraper
```

---

## Uso Local (sin Docker)

### Comandos principales

```bash
# 1. ACTIVAR ENTORNO VIRTUAL (siempre antes de usar)
source venv/bin/activate

# 2. INICIALIZAR BASE DE DATOS (solo la primera vez)
python main.py --init

# 3. EJECUTAR SCRAPER (obtener datos de los marketplaces)
python main.py --scrape

# 4. INICIAR DASHBOARD (visualizar datos)
streamlit run dashboard.py
# Luego abre: http://localhost:8501

# 5. GENERAR REPORTE EXCEL
python main.py --report

# 6. EJECUTAR SCRAPER + DETECTAR VENTAS + REPORTE (todo junto)
python main.py --all
```

---

## Configuración

Edita el archivo `config.py` para personalizar:

### Modelos a buscar en Chrono24

```python
CHRONO24_MODELS = [
    "Omega de ville",
    "Hermès Arceau",
    "Omega seamaster",
    # Añade más modelos aquí
]
```

### Vendedores a seguir en Vestiaire

```python
VESTIAIRE_SELLER_IDS = [
    "3022988",      # ID del vendedor 1
    "10125453",     # ID del vendedor 2
    # Añade más IDs aquí
]
```

### Países a excluir

```python
CHRONO24_EXCLUDE_COUNTRIES = [
    "Japón",
    "Japan",
]
```

---

## Estructura del Proyecto

```
watch-my-bag-scraper/
├── main.py              # Script principal (scraper)
├── dashboard.py         # Dashboard web (Streamlit)
├── config.py            # Configuración (modelos, vendedores, etc.)
├── requirements.txt     # Dependencias Python
├── Dockerfile           # Imagen Docker
├── docker-compose.yml   # Orquestación Docker
├── setup.sh             # Script de instalación
├── README.md            # Este archivo
│
├── database/
│   └── db_manager.py    # Gestión de base de datos SQLite
│
├── scrapers/
│   ├── base_scraper.py      # Clase base para scrapers
│   ├── scraper_chrono.py    # Scraper de Chrono24
│   ├── scraper_vestiaire.py # Scraper de Vestiaire
│   └── scraper_catawiki.py  # Scraper de Catawiki
│
├── processors/
│   ├── data_processor.py    # Detección de ventas
│   └── excel_manager.py     # Generación de reportes
│
├── data/
│   ├── inventory.db         # Base de datos SQLite
│   ├── exports/             # Reportes Excel generados
│   └── images/              # Imágenes descargadas
│
└── logs/                    # Archivos de log
```

---

## Flujo de Trabajo Recomendado

### Uso diario

1. **Ejecutar el scraper** una vez al día (preferiblemente a la misma hora):
   ```bash
   # Docker
   docker compose --profile scrape run --rm scraper

   # Local
   python main.py --scrape
   ```

2. **Revisar el dashboard** para ver inventario y ventas detectadas:
   ```bash
   # Docker
   docker compose up dashboard

   # Local
   streamlit run dashboard.py
   ```

3. **Generar reporte** cuando necesites exportar datos:
   ```bash
   # Docker
   docker compose --profile report run --rm report

   # Local
   python main.py --report
   ```

### Automatización (opcional)

Puedes programar el scraper con cron (Linux/Mac) o Task Scheduler (Windows):

```bash
# Ejemplo de cron para ejecutar diariamente a las 9:00 AM
0 9 * * * cd /ruta/al/proyecto && docker compose --profile scrape run --rm scraper
```

---

## Funcionalidades del Dashboard

El dashboard (http://localhost:8501) incluye:

- **Inventario**: Ver todos los productos actuales en los marketplaces
- **Ventas**: Productos detectados como vendidos
- **Análisis**: Gráficos de ventas por plataforma, distribución de precios
- **Datos**: Tabla exportable con todos los datos

### Filtros disponibles

- Plataforma (Chrono24, Vestiaire, Catawiki)
- Modelo buscado
- Rango de precio
- País del vendedor
- Condición del producto
- ID del vendedor (Vestiaire)
- ID del producto (Chrono24)

---

## Solución de Problemas

### El scraper no obtiene datos

1. Verifica tu conexión a internet
2. Los marketplaces pueden tener protección anti-bot. Espera unos minutos y reintenta
3. Revisa los logs en `logs/` para más detalles

### El dashboard no inicia

```bash
# Verificar que el puerto 8501 está libre
lsof -i :8501

# Usar otro puerto
streamlit run dashboard.py --server.port=8502
```

### Error de base de datos

```bash
# Reinicializar la base de datos
# Docker
docker compose --profile init run --rm init

# Local
python main.py --init
```

### Limpiar y reconstruir Docker

```bash
# Eliminar contenedores e imágenes
docker compose down --rmi all --volumes

# Reconstruir
docker compose build --no-cache
```

---

## Notas Importantes

- **Catawiki** está temporalmente desactivado por protección anti-bot agresiva
- El scraper incluye delays aleatorios para evitar bloqueos
- Se recomienda no ejecutar el scraper más de 2-3 veces al día
- Los datos se guardan localmente en SQLite (no requiere servidor de base de datos)

---

## Soporte

Si encuentras algún problema:

1. Revisa los logs en la carpeta `logs/`
2. Asegúrate de tener la última versión del proyecto
3. Verifica que tu configuración en `config.py` es correcta

---

**Watch MY Bag Scraper** - Monitoreo inteligente de relojes en marketplaces
