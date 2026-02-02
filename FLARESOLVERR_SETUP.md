# Configuración de FlareSolverr para Chrono24

FlareSolverr es un servicio que resuelve automáticamente la protección Cloudflare de Chrono24.

## Requisitos

- ✅ Docker Desktop instalado y ejecutándose
- ✅ Puerto 8191 disponible

## Instalación y Configuración

### Paso 1: Iniciar Docker Desktop

1. Abre **Docker Desktop** desde el menú de inicio de Windows
2. Espera a que Docker esté completamente iniciado (ícono verde en la bandeja del sistema)

### Paso 2: Iniciar FlareSolverr

Ejecuta el script automático:

```powershell
start_flaresolverr.bat
```

Esto hará:
- Verificar que Docker esté corriendo
- Descargar la imagen de FlareSolverr (solo la primera vez, ~300 MB)
- Iniciar el contenedor en el puerto 8191
- Verificar que esté funcionando

### Paso 3: Verificar Instalación

```powershell
py test_flaresolverr.py
```

Deberías ver:
```
✓ FlareSolverr está corriendo
✓ FlareSolverr resolvió correctamente
✓ FLARESOLVERR FUNCIONANDO CORRECTAMENTE
```

### Paso 4: Ejecutar Scraper

Ahora puedes ejecutar el scraper de Chrono24:

```powershell
py main.py --scrape --chrono24-only
```

## Comandos Útiles

### Ver estado de FlareSolverr
```powershell
docker ps --filter name=flaresolverr
```

### Ver logs en tiempo real
```powershell
docker logs -f flaresolverr
```

### Detener FlareSolverr
```powershell
docker stop flaresolverr
```

### Iniciar FlareSolverr (si ya existe)
```powershell
docker start flaresolverr
```

### Reiniciar FlareSolverr
```powershell
docker restart flaresolverr
```

### Eliminar FlareSolverr completamente
```powershell
docker rm -f flaresolverr
```

## Configuración Avanzada

### Cambiar configuración en config.py

```python
# Activar/desactivar FlareSolverr
USE_FLARESOLVERR = True

# URL del servicio (cambiar si usas otro puerto)
FLARESOLVERR_URL = "http://localhost:8191/v1"

# Timeout en segundos
FLARESOLVERR_TIMEOUT = 60
```

### Usar FlareSolverr en otro puerto

Si el puerto 8191 está ocupado:

```powershell
docker run -d --name flaresolverr -p 9191:8191 --restart unless-stopped ghcr.io/flaresolverr/flaresolverr:latest
```

Y actualiza en config.py:
```python
FLARESOLVERR_URL = "http://localhost:9191/v1"
```

## Solución de Problemas

### "Docker no está corriendo"
- Inicia Docker Desktop
- Espera a que el ícono esté verde en la bandeja del sistema

### "No se puede conectar a FlareSolverr"
- Verifica que el contenedor esté corriendo: `docker ps`
- Verifica los logs: `docker logs flaresolverr`
- Reinicia el contenedor: `docker restart flaresolverr`

### "Error durante resolución"
- Aumenta el timeout en config.py (ej: 90 segundos)
- Verifica tu conexión a internet
- Chrono24 puede haber actualizado su protección

### "Puerto 8191 ya en uso"
- Ver qué está usando el puerto: `netstat -ano | findstr :8191`
- Usar otro puerto (ver Configuración Avanzada arriba)

## Cómo Funciona

1. El scraper envía la URL a FlareSolverr
2. FlareSolverr usa un navegador real para resolver Cloudflare
3. FlareSolverr devuelve HTML + cookies resueltos
4. El scraper usa esas cookies para acceder a Chrono24

## Limitaciones

- ⏱️ Más lento que scraping directo (15-30s por resolución)
- 🐳 Requiere Docker Desktop corriendo siempre
- ⚠️ No garantiza 100% de éxito (Cloudflare Bot Management es muy avanzado)
- 💾 Consume ~500 MB de RAM cuando está activo

## Alternativas si FlareSolverr no funciona

Si FlareSolverr falla constantemente:

1. **Reducir frecuencia**: Scrapear Chrono24 solo 1 vez al día
2. **Proxies residenciales** ($$): BrightData, Smartproxy, Oxylabs
3. **Servicios anti-captcha** ($): 2Captcha, Anti-Captcha, CapSolver
4. **Scraping manual**: Resolver Cloudflare manualmente y exportar cookies

---

**Documentación oficial de FlareSolverr**: https://github.com/FlareSolverr/FlareSolverr
