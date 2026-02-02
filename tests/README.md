# Tests de Integridad de Datos

Suite de tests para verificar la calidad e integridad de los datos del scraper de relojes.

## Descripción

Estos tests verifican:

1. **Duplicados en Inventario**
   - No hay listings duplicados en el mismo snapshot
   - Detecta si un listing_id aparece en múltiples plataformas

2. **Duplicados en Ventas Detectadas**
   - No hay ventas duplicadas en la misma fecha de detección
   - Alerta sobre productos vendidos múltiples veces en diferentes fechas

3. **Falsos Positivos** ⚠️ **MUY IMPORTANTE**
   - Verifica que productos marcados como vendidos NO vuelvan a aparecer en inventario
   - Identifica problemas del scraper o inconsistencias de las plataformas

4. **Consistencia de Datos**
   - Precios válidos en todas las ventas
   - Fechas coherentes (no futuras, no muy antiguas)
   - No hay caídas sospechosas en inventario (>90%)

5. **Integridad Referencial**
   - Todas las ventas tienen registro histórico en inventario

## Instalación

```bash
# Instalar dependencias de testing
pip install -r requirements.txt
```

## Ejecución

### Opción 1: Scripts automatizados (recomendado)

**Linux/Mac:**
```bash
# Dar permisos (solo la primera vez)
chmod +x run_tests.sh

# Ejecutar todos los tests
./run_tests.sh

# Modo verbose (ver detalles)
./run_tests.sh -v

# Solo tests de duplicados
./run_tests.sh -k "duplicate"

# Solo generar reporte
./run_tests.sh --report
```

**Windows:**
```cmd
# Ejecutar todos los tests
run_tests.bat

# Modo verbose
run_tests.bat -v

# Solo tests de duplicados
run_tests.bat -k "duplicate"

# Solo generar reporte
run_tests.bat --report
```

### Opción 2: Pytest directo

```bash
# Todos los tests
pytest tests/test_data_integrity.py -v

# Solo tests de una clase
pytest tests/test_data_integrity.py::TestDataIntegrity -v

# Solo un test específico
pytest tests/test_data_integrity.py::TestDataIntegrity::test_no_sold_items_reappearing_in_inventory -v

# Con salida detallada
pytest tests/test_data_integrity.py -v -s

# Detener en el primer fallo
pytest tests/test_data_integrity.py -x
```

### Opción 3: Python directo

```bash
python tests/test_data_integrity.py
```

## Interpretación de Resultados

### ✅ Test Pasado
El test no encontró problemas.

### ❌ Test Fallido (AssertionError)
**CRÍTICO** - Hay un problema grave que requiere atención inmediata:
- Duplicados en ventas del mismo día
- Falsos positivos (productos vendidos que reaparecen)
- Precios inválidos en más del 10% de ventas

### ⚠️ Advertencias (Warnings)
**REVISAR** - Situaciones sospechosas que debes investigar:
- Productos vendidos múltiples veces (puede ser legítimo)
- Listing_id en múltiples plataformas
- Caídas importantes en inventario
- Ventas sin registro histórico

## Reporte de Integridad

Para generar un reporte completo sin ejecutar validaciones:

```bash
# Linux/Mac
./run_tests.sh --report

# Windows
run_tests.bat --report

# Pytest directo
pytest tests/test_data_integrity.py::TestDataIntegrity::test_generate_integrity_report -v -s
```

Ejemplo de salida:

```
======================================================================
REPORTE DE INTEGRIDAD DE DATOS
======================================================================

📊 ESTADÍSTICAS GENERALES:
  - Total registros en inventario: 1,234
  - Total ventas detectadas: 56
  - Plataformas: chrono24, vestiaire
  - Rango de fechas: 2026-01-01 → 2026-01-25

💰 PRECIOS DE VENTAS:
  - Precios reales: 12
  - Precios estimados: 44

📈 VENTAS POR PLATAFORMA:
  - chrono24: 34 ventas
  - vestiaire: 22 ventas
======================================================================
```

## Frecuencia Recomendada

- **Diario**: Después de cada scraping para detectar problemas rápidamente
- **Semanal**: Reporte completo de integridad
- **Mensual**: Análisis profundo de tendencias

## Integración con CI/CD

Puedes integrar estos tests en tu pipeline:

```yaml
# GitHub Actions ejemplo
- name: Run integrity tests
  run: |
    pip install -r requirements.txt
    pytest tests/test_data_integrity.py -v
```

## Qué hacer si hay fallos

### Duplicados en ventas del mismo día
```bash
# Investigar en la base de datos
sqlite3 data/inventory.db
SELECT * FROM detected_sales
WHERE listing_id IN (
    SELECT listing_id FROM detected_sales
    GROUP BY platform, listing_id, detection_date
    HAVING COUNT(*) > 1
);
```

**Solución**: Eliminar duplicados y revisar la lógica de `save_detected_sales()`.

### Falsos positivos (vendidos que reaparecen)
```bash
# Ver detalles en el output del test
./run_tests.sh -v -s
```

**Posibles causas**:
- Scraper falló temporalmente y no capturó el producto
- Producto fue republicado con el mismo ID
- Error en la plataforma

**Solución**: Revisar logs del scraper en las fechas indicadas.

### Caídas sospechosas en inventario
**Posibles causas**:
- Scraper fue bloqueado
- Cambio en estructura HTML de la plataforma
- Error en selectores CSS/XPath

**Solución**: Ejecutar scraper manualmente y revisar logs.

## Tests Funcionales

También incluye tests unitarios de la lógica de detección:

```bash
# Solo tests funcionales
pytest tests/test_data_integrity.py::TestSalesDetectionLogic -v
```

Estos tests usan una base de datos temporal y verifican:
- Detección correcta de ventas cuando un item desaparece
- No hay falsos positivos cuando items persisten
- Detección correcta de cambios de precio

## Archivos

- `test_data_integrity.py`: Suite completa de tests
- `run_tests.sh`: Script para Linux/Mac
- `run_tests.bat`: Script para Windows
- `README.md`: Esta documentación

## Contribuir

Si encuentras nuevos casos de problemas de integridad, añade tests adicionales en `test_data_integrity.py`.

---

**Última actualización**: 2026-01-25
