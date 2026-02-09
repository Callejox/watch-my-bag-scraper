# Watch MY Bag - Guía Rápida para Usuarios

## ¿Qué hace este programa?

Watch MY Bag es un programa que **monitorea automáticamente relojes de lujo** en páginas web como Chrono24, Vestiaire Collective y Catawiki.

**Te ayuda a:**
- Ver qué relojes están a la venta en estas páginas
- Detectar automáticamente cuáles se han vendido
- Analizar precios y tendencias de venta
- Ver toda la información en un dashboard visual fácil de usar

---

## 📥 Descargar el Proyecto

**Enlace del proyecto:** https://github.com/Callejox/watch-my-bag-scraper

### Opción 1: Descargar como ZIP (Más fácil)
1. Ve al enlace de arriba
2. Haz clic en el botón verde **"Code"**
3. Selecciona **"Download ZIP"**
4. Descomprime el archivo en tu ordenador

### Opción 2: Con Git (Si ya lo tienes instalado)
Abre PowerShell o Terminal y escribe:
```powershell
git clone https://github.com/Callejox/watch-my-bag-scraper.git
cd watch-my-bag-scraper
```

---

## 📋 Requisitos Previos

Antes de usar el programa, necesitas instalar:

### 1. Python (versión 3.9 o superior)
- **Descargar:** https://www.python.org/downloads/
- ⚠️ **IMPORTANTE:** Durante la instalación, marca la casilla **"Add Python to PATH"**

### 2. Docker Desktop (necesario para evitar bloqueos de Cloudflare)
- **Descargar:** https://www.docker.com/products/docker-desktop/
- Después de instalar, abre Docker Desktop y déjalo ejecutándose

---

## 🚀 Instalación (Solo la Primera Vez)

1. **Abre PowerShell** en la carpeta del proyecto:
   - Haz clic derecho en la carpeta del proyecto
   - Selecciona "Abrir en Terminal" o "Open PowerShell window here"

2. **Instala las dependencias** (copia y pega este comando):
   ```powershell
   py -m pip install -r requirements.txt
   ```

3. **Inicializa la base de datos** (solo la primera vez):
   ```powershell
   py main.py --init
   ```

---

## ▶️ Cómo Ejecutar el Scraper

### Comando Simple (Recomendado)

Abre PowerShell en la carpeta del proyecto y ejecuta:

```powershell
.\run_workflow.bat
```

Este comando hace **TODO automáticamente**:
- ✅ Verifica que Docker está corriendo
- ✅ Inicia FlareSolverr (para evitar bloqueos)
- ✅ Descarga información de Chrono24 y Vestiaire
- ✅ Detecta ventas comparando con el día anterior
- ✅ Verifica que los datos son correctos
- ✅ Genera un reporte Excel si hay ventas nuevas

**Tiempo estimado:** 20-30 minutos (depende de cuántas páginas scrape)

### Comandos Alternativos (Más control)

Si quieres más control, puedes usar:

```powershell
# Solo scrapear Chrono24
.\run_workflow.bat --chrono24-only

# Solo scrapear Vestiaire
.\run_workflow.bat --vestiaire-only

# Modo prueba (rápido, solo 1 página por modelo)
.\run_workflow.bat --test-mode

# Scrapear sin generar reporte Excel
.\run_workflow.bat --skip-report
```

---

## 📊 Ver los Resultados

### Opción 1: Dashboard Visual (Recomendado)

Abre el dashboard interactivo para ver gráficos, fotos y análisis:

```powershell
py -m streamlit run dashboard.py
```

Se abrirá automáticamente en tu navegador en: http://localhost:8501

**El dashboard te muestra:**
- 📦 Inventario actual de relojes a la venta
- 💰 Ventas detectadas con fotos, precios y enlaces
- 📈 Gráficos de ventas por modelo y plataforma
- 🔍 Filtros para buscar por precio, país, condición, etc.

### Opción 2: Reporte Excel

Los reportes se guardan automáticamente en:
```
data/exports/reporte_[mes]_2026.xlsx
```

Ábrelo con Excel para ver todas las ventas del mes.

---

## 🔧 Solución de Problemas Comunes

### "Docker no está corriendo"
- Abre **Docker Desktop** manualmente antes de ejecutar el scraper
- Espera a que Docker Desktop muestre "Engine running"

### "El término 'py' no se reconoce"
- Python no está instalado o no está en PATH
- Reinstala Python y marca **"Add Python to PATH"** durante la instalación

### "run_workflow.bat no se encuentra"
- Usa `.\run_workflow.bat` (con punto y barra al inicio)
- O ejecuta directamente: `py main.py --workflow`

### El scraper no encuentra productos en Chrono24
- Chrono24 tiene protección anti-bots muy agresiva
- **Solución:** Solo ejecuta el scraper 1-2 veces al DÍA (no más)
- Demasiadas ejecuciones seguidas resultarán en bloqueos

---

## ⏱️ ¿Con Qué Frecuencia Debo Ejecutarlo?

**Recomendación:** 1 vez al día (por ejemplo, cada mañana)

- ✅ **Chrono24:** Máximo 1-2 veces/día (protección anti-bot muy fuerte)
- ✅ **Vestiaire:** Puedes ejecutarlo más veces si quieres (3-4 veces/día)
- ✅ **Catawiki:** Máximo 1-2 veces/día (protección anti-bot fuerte)

Si ejecutas demasiado seguido, las páginas web pueden bloquearte temporalmente.

---

## 📁 Estructura de Archivos

Después de ejecutar el programa, encontrarás:

```
📂 Proyecto miha/
├── 📂 data/
│   ├── inventory.db          ← Base de datos con todo el inventario
│   ├── 📂 exports/           ← Reportes Excel generados
│   ├── 📂 images/            ← Fotos de los relojes descargadas
│   └── 📂 debug/             ← Capturas de pantalla si algo falla
├── 📂 logs/                  ← Archivos de log (errores y actividad)
└── run_workflow.bat          ← Comando principal para ejecutar
```

---

## 🆘 ¿Necesitas Ayuda?

Si tienes problemas:

1. **Revisa los logs** en la carpeta `logs/` - el archivo más reciente mostrará qué pasó
2. **Reporta el problema** en GitHub: https://github.com/Callejox/watch-my-bag-scraper/issues
3. Incluye el archivo de log cuando reportes un problema

---

## 📝 Configuración Avanzada (Opcional)

Si quieres cambiar qué modelos buscar o cuántas páginas scrapear, edita el archivo `config.py`:

```python
# Modelos a buscar en Chrono24
CHRONO24_MODELS = [
    "Omega de ville",
    "Hermès Arceau",
    "Omega Seamaster"
]

# Páginas a scrapear por modelo (20 = ~2,400 relojes)
CHRONO24_MAX_PAGES = 20
```

---

**¡Listo!** Ya puedes empezar a monitorear relojes de lujo automáticamente.

**Proyecto en GitHub:** https://github.com/Callejox/watch-my-bag-scraper
