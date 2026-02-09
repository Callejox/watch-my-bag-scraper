# Watch MY Bag Scraper

**Repositorio:** https://github.com/Callejox/watch-my-bag-scraper

Aplicación de monitoreo y scraping de relojes de lujo en marketplaces online (Chrono24, Vestiaire Collective, Catawiki).

Detecta automáticamente ventas comparando inventarios diarios y proporciona un dashboard interactivo para visualizar los datos.

## 📖 ¿Nuevo en Programación?

Si no tienes experiencia técnica, consulta la **[Guía Rápida para Usuarios](GUIA_RAPIDA.md)** con instrucciones paso a paso simplificadas.

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

### Flujo Automatizado (Recomendado - Windows)

```powershell
# FLUJO COMPLETO (scraping + validación + reporte) - UN SOLO COMANDO
.\run_workflow.bat

# OPCIONES DISPONIBLES:
.\run_workflow.bat --test-mode        # Modo prueba (1 modelo, 1 página)
.\run_workflow.bat --chrono24-only    # Solo Chrono24
.\run_workflow.bat --vestiaire-only   # Solo Vestiaire
.\run_workflow.bat --catawiki-only    # Solo Catawiki
.\run_workflow.bat --skip-report      # Sin generar reporte Excel
```

**El workflow hace TODO automáticamente:**
- ✅ Verifica Docker y FlareSolverr (necesarios para Chrono24 y Catawiki)
- ✅ Ejecuta scraping de todas las plataformas activas
- ✅ Verifica integridad de datos
- ✅ Repara errores si es necesario
- ✅ Genera reporte Excel si hay ventas nuevas

### Comandos Individuales (Más control)

```bash
# 1. ACTIVAR ENTORNO VIRTUAL (siempre antes de usar)
source venv/bin/activate          # Linux/Mac
venv\Scripts\activate             # Windows

# 2. INICIALIZAR BASE DE DATOS (solo la primera vez)
python main.py --init

# 3. EJECUTAR SCRAPER (obtener datos de los marketplaces)
python main.py --scrape

# 4. INICIAR DASHBOARD (visualizar datos)
streamlit run dashboard.py
# Luego abre: http://localhost:8501

# 5. GENERAR REPORTE EXCEL
python main.py --report

# 6. VERIFICAR INTEGRIDAD DE DATOS (IMPORTANTE después de scrapear)
python check_integrity.py --full

# 7. REPARAR BASE DE DATOS (si se detectan problemas)
python fix_database.py --fix-all

# 8. EJECUTAR FLUJO COMPLETO (Python directo)
python main.py --workflow
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

### Pestañas Principales

1. **Inventario**:
   - Grid visual con tarjetas de productos
   - Imágenes, precios y enlaces clickeables
   - Sistema dual de imágenes (local → remota → placeholder)

2. **Ventas** (Vista Jerárquica de 2 Niveles):
   - **Nivel 1 - Modelo Genérico**: Expanders por modelo (Omega Seamaster, De Ville, etc.)
     - Gráficos comparativos de sub-modelos (barras + box plots)
     - Análisis de distribución de precios
   - **Nivel 2 - Sub-Modelos**: Expanders dentro de cada modelo
     - Galería de fotos (hasta 6 por grupo)
     - Métricas: rango de precios, media, total, días medio en venta
     - Tabla detallada con enlaces clickeables
   - **Selector de Plataforma**: Filtrar por "Todas" | "Chrono24" | "Vestiaire"

3. **Análisis**:
   - Gráficos de ventas por plataforma
   - Distribución de precios
   - Ventas diarias (timeline)

4. **Datos**:
   - Tabla completa exportable a CSV
   - Todos los campos disponibles para análisis

### Filtros Disponibles (Sidebar)

- Plataforma (Chrono24, Vestiaire, Catawiki)
- Modelo buscado
- Rango de precio (slider)
- País del vendedor
- Condición del producto
- Rango de fechas (calendarios)
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

### Protección Anti-Bot y FlareSolverr

- **Chrono24**: Requiere FlareSolverr (Docker) para bypass de Cloudflare. Ejecutar máximo 1-2 veces/día
- **Catawiki**: Requiere FlareSolverr (Docker) para bypass de Cloudflare. Ejecutar máximo 1-2 veces/día
- **Vestiaire**: No requiere FlareSolverr. Puede ejecutarse 3-4 veces/día sin problemas
- **FlareSolverr**: Se inicia automáticamente con `run_workflow.bat` o se puede iniciar manualmente con `start_flaresolverr.bat`

### Otras Consideraciones

- El scraper incluye delays aleatorios para evitar bloqueos
- Los datos se guardan localmente en SQLite (no requiere servidor de base de datos)
- Se recomienda ejecutar `check_integrity.py` después de cada scraping
- Las imágenes se descargan automáticamente durante el scraping

---

## Soporte

Si encuentras algún problema:

1. Revisa los logs en la carpeta `logs/`
2. Asegúrate de tener la última versión del proyecto
3. Verifica que tu configuración en `config.py` es correcta

---

**Watch MY Bag Scraper** - Monitoreo inteligente de relojes en marketplaces
