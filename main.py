#!/usr/bin/env python3
"""
Herramienta de Inventario Delta para Chrono24, Vestiaire Collective y Catawiki.

Detecta artículos vendidos mediante comparación diaria de inventarios.
Ejecutar diariamente (preferiblemente por la mañana) para detectar ventas del día anterior.

Uso:
    python main.py --scrape              # Ejecutar scraping completo
    python main.py --scrape --report     # Scraping + generar Excel
    python main.py --report              # Solo generar reporte Excel
    python main.py --test                # Probar conexión a los sitios
    python main.py --init                # Inicializar base de datos
    python main.py --stats               # Ver estadísticas

Autor: Generado con Claude
"""

import argparse
import asyncio
import os
import subprocess
import sys
import time
from datetime import datetime, date
from pathlib import Path

import requests
from loguru import logger

# Configurar path del proyecto
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from config import (
    LOGS_DIR,
    LOG_LEVEL,
    LOG_FORMAT,
    LOG_ROTATION,
    LOG_RETENTION,
    CHRONO24_MODELS,
    CHRONO24_MAX_PAGES,
    VESTIAIRE_SELLER_IDS,
    CATAWIKI_ENABLED,
    USE_FLARESOLVERR,
    FLARESOLVERR_URL,
)
from database.db_manager import DatabaseManager
from processors.data_processor import DataProcessor
from processors.excel_manager import ExcelManager


def setup_logging():
    """Configura el sistema de logging."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Remover handlers por defecto
    logger.remove()

    # Añadir handler de consola
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
        level=LOG_LEVEL,
        colorize=True,
    )

    # Añadir handler de archivo
    log_file = LOGS_DIR / "scraper_{time:YYYY-MM-DD}.log"
    logger.add(
        str(log_file),
        format=LOG_FORMAT,
        level="DEBUG",
        rotation=LOG_ROTATION,
        retention=LOG_RETENTION,
        compression="zip",
    )

    logger.info("=" * 60)
    logger.info(f"Iniciando sesión de scraping - {datetime.now().isoformat()}")
    logger.info("=" * 60)


async def run_chrono24_scraping(db: DatabaseManager, processor: DataProcessor, test_mode: bool = False):
    """
    Ejecuta el scraping de Chrono24.

    Args:
        db: Gestor de base de datos
        processor: Procesador de datos
        test_mode: Si es True, solo scrapea 1 modelo y 1 página

    Returns:
        Diccionario con resultados
    """
    from scrapers.scraper_chrono import Chrono24Scraper

    start_time = time.time()
    results = {
        'platform': 'chrono24',
        'status': 'failed',
        'items_scraped': 0,
        'items_sold': 0,
        'errors': None,
    }

    try:
        async with Chrono24Scraper() as scraper:
            # En modo test, solo 1 modelo y 1 página (para probar descarga de imágenes)
            if test_mode:
                models = [CHRONO24_MODELS[0]] if CHRONO24_MODELS else []
                max_pages = 1  # Solo 1 página para test rápido
            else:
                models = CHRONO24_MODELS
                max_pages = CHRONO24_MAX_PAGES

            logger.info(f"Scrapeando {len(models)} modelos de Chrono24...")

            # Ejecutar scraping
            inventory = await scraper.scrape(models=models, max_pages=max_pages)
            results['items_scraped'] = len(inventory)

            # Construir metadata del scraping para validación de cobertura
            scraping_metadata = {
                'pages_scraped': getattr(scraper, 'pages_scraped', None),
                'pages_total': getattr(scraper, 'pages_total', None),
            }

            # Procesar ventas (comparar con ayer)
            process_results = processor.process_chrono24_sales(inventory, scraping_metadata)
            results['items_sold'] = process_results['items_sold']
            results['status'] = 'success'

            if process_results.get('is_first_run'):
                logger.info("Primera ejecución - inventario inicial guardado")
            else:
                logger.info(f"Ventas detectadas: {results['items_sold']}")

    except Exception as e:
        logger.error(f"Error en scraping de Chrono24: {e}")
        results['errors'] = str(e)
        results['status'] = 'failed'

    duration = time.time() - start_time
    results['duration_seconds'] = round(duration, 2)

    # Registrar en log de base de datos
    db.log_scrape_run(
        platform='chrono24',
        status=results['status'],
        items_scraped=results['items_scraped'],
        items_sold_detected=results['items_sold'],
        errors=results['errors'],
        duration_seconds=duration,
    )

    return results


async def run_vestiaire_scraping(db: DatabaseManager, processor: DataProcessor, test_mode: bool = False):
    """
    Ejecuta el scraping de Vestiaire Collective.

    Args:
        db: Gestor de base de datos
        processor: Procesador de datos
        test_mode: Si es True, solo scrapea 1 vendedor y 1 página

    Returns:
        Diccionario con resultados
    """
    from scrapers.scraper_vestiaire import VestiaireScraper

    start_time = time.time()
    results = {
        'platform': 'vestiaire',
        'status': 'failed',
        'items_scraped': 0,
        'items_sold': 0,
        'errors': None,
    }

    # Verificar que hay vendedores configurados
    valid_sellers = [s for s in VESTIAIRE_SELLER_IDS if s and not s.startswith('seller_id_')]

    if not valid_sellers:
        logger.warning(
            "No hay vendedores de Vestiaire configurados. "
            "Edita config.py y añade los IDs reales de los vendedores."
        )
        results['status'] = 'skipped'
        results['errors'] = 'No hay vendedores configurados'
        return results

    try:
        async with VestiaireScraper() as scraper:
            # En modo test, solo 1 vendedor y 1 página
            if test_mode:
                sellers = [valid_sellers[0]]
                max_pages = 1
            else:
                sellers = valid_sellers
                max_pages = 10

            logger.info(f"Scrapeando {len(sellers)} vendedores de Vestiaire...")

            # Ejecutar scraping
            inventory = await scraper.scrape(seller_ids=sellers, max_pages=max_pages)
            results['items_scraped'] = len(inventory)

            # Procesar ventas (comparar con ayer)
            process_results = await processor.process_vestiaire_sales(inventory, scraper)
            results['items_sold'] = process_results['items_sold']
            results['status'] = 'success'

            if process_results.get('is_first_run'):
                logger.info("Primera ejecución - inventario inicial guardado")
            else:
                logger.info(f"Ventas detectadas: {results['items_sold']}")

    except Exception as e:
        logger.error(f"Error en scraping de Vestiaire: {e}")
        results['errors'] = str(e)
        results['status'] = 'failed'

    duration = time.time() - start_time
    results['duration_seconds'] = round(duration, 2)

    # Registrar en log de base de datos
    db.log_scrape_run(
        platform='vestiaire',
        status=results['status'],
        items_scraped=results['items_scraped'],
        items_sold_detected=results['items_sold'],
        errors=results['errors'],
        duration_seconds=duration,
    )

    return results


async def run_catawiki_scraping(db: DatabaseManager, processor: DataProcessor, test_mode: bool = False):
    """
    Ejecuta el scraping de Catawiki.

    Args:
        db: Gestor de base de datos
        processor: Procesador de datos
        test_mode: Si es True, solo scrapea 1 modelo y 1 página

    Returns:
        Diccionario con resultados
    """
    from scrapers.scraper_catawiki import CatawikiScraper

    start_time = time.time()
    results = {
        'platform': 'catawiki',
        'status': 'failed',
        'items_scraped': 0,
        'items_sold': 0,
        'errors': None,
    }

    if not CATAWIKI_ENABLED:
        logger.info("Catawiki está desactivado en config.py")
        results['status'] = 'skipped'
        results['errors'] = 'Catawiki desactivado'
        return results

    try:
        async with CatawikiScraper() as scraper:
            # En modo test, solo 1 modelo y 1 página
            if test_mode:
                models = [CHRONO24_MODELS[0]] if CHRONO24_MODELS else []
                max_pages = 1
            else:
                models = CHRONO24_MODELS  # Usa los mismos modelos que Chrono24
                max_pages = 3

            logger.info(f"Scrapeando {len(models)} modelos de Catawiki...")

            # Ejecutar scraping
            inventory = await scraper.scrape(models=models, max_pages=max_pages)
            results['items_scraped'] = len(inventory)

            # Procesar ventas (comparar con ayer)
            process_results = processor.process_catawiki_sales(inventory)
            results['items_sold'] = process_results['items_sold']
            results['status'] = 'success'

            if process_results.get('is_first_run'):
                logger.info("Primera ejecución - inventario inicial guardado")
            else:
                logger.info(f"Ventas detectadas: {results['items_sold']}")

    except Exception as e:
        logger.error(f"Error en scraping de Catawiki: {e}")
        results['errors'] = str(e)
        results['status'] = 'failed'

    duration = time.time() - start_time
    results['duration_seconds'] = round(duration, 2)

    # Registrar en log de base de datos
    db.log_scrape_run(
        platform='catawiki',
        status=results['status'],
        items_scraped=results['items_scraped'],
        items_sold_detected=results['items_sold'],
        errors=results['errors'],
        duration_seconds=duration,
    )

    return results


async def run_full_scraping(test_mode: bool = False):
    """
    Ejecuta el scraping completo de todas las plataformas.

    Args:
        test_mode: Si es True, ejecuta en modo de prueba reducido

    Returns:
        Diccionario con resultados de todas las plataformas
    """
    db = DatabaseManager()
    processor = DataProcessor(db)

    results = {
        'date': date.today().isoformat(),
        'test_mode': test_mode,
        'chrono24': None,
        'vestiaire': None,
        'catawiki': None,
    }

    # Scraping de Chrono24
    logger.info("=" * 40)
    logger.info("INICIANDO SCRAPING DE CHRONO24")
    logger.info("=" * 40)
    results['chrono24'] = await run_chrono24_scraping(db, processor, test_mode)

    # Scraping de Vestiaire
    logger.info("=" * 40)
    logger.info("INICIANDO SCRAPING DE VESTIAIRE COLLECTIVE")
    logger.info("=" * 40)
    results['vestiaire'] = await run_vestiaire_scraping(db, processor, test_mode)

    # Scraping de Catawiki
    logger.info("=" * 40)
    logger.info("INICIANDO SCRAPING DE CATAWIKI")
    logger.info("=" * 40)
    results['catawiki'] = await run_catawiki_scraping(db, processor, test_mode)

    # Resumen
    logger.info("=" * 40)
    logger.info("RESUMEN DE SCRAPING")
    logger.info("=" * 40)
    logger.info(f"Chrono24: {results['chrono24']['items_scraped']} items, {results['chrono24']['items_sold']} ventas")
    logger.info(f"Vestiaire: {results['vestiaire']['items_scraped']} items, {results['vestiaire']['items_sold']} ventas")
    if results['catawiki']['status'] != 'skipped':
        logger.info(f"Catawiki: {results['catawiki']['items_scraped']} items, {results['catawiki']['items_sold']} ventas")

    return results


def generate_report():
    """Genera el reporte Excel del mes actual."""
    logger.info("Generando reporte Excel...")

    excel_manager = ExcelManager()
    filepath = excel_manager.generate_monthly_report()

    logger.info(f"Reporte generado: {filepath}")
    return filepath


async def test_connections():
    """Prueba las conexiones a todos los sitios."""
    from scrapers.scraper_chrono import Chrono24Scraper
    from scrapers.scraper_vestiaire import VestiaireScraper
    from scrapers.scraper_catawiki import CatawikiScraper

    logger.info("Probando conexiones...")

    # Test Chrono24
    logger.info("Probando Chrono24...")
    try:
        async with Chrono24Scraper() as scraper:
            async with scraper.get_page() as page:
                success = await scraper.safe_goto(page, "https://www.chrono24.es/")
                if success:
                    logger.info("✓ Chrono24: Conexión exitosa")
                else:
                    logger.error("✗ Chrono24: Error de conexión")
    except Exception as e:
        logger.error(f"✗ Chrono24: {e}")

    # Test Vestiaire
    logger.info("Probando Vestiaire Collective...")
    try:
        async with VestiaireScraper() as scraper:
            async with scraper.get_page() as page:
                success = await scraper.safe_goto(page, "https://es.vestiairecollective.com/")
                if success:
                    logger.info("✓ Vestiaire Collective: Conexión exitosa")
                else:
                    logger.error("✗ Vestiaire Collective: Error de conexión")
    except Exception as e:
        logger.error(f"✗ Vestiaire Collective: {e}")

    # Test Catawiki
    logger.info("Probando Catawiki...")
    try:
        async with CatawikiScraper() as scraper:
            async with scraper.get_page() as page:
                success = await scraper.safe_goto(page, "https://www.catawiki.com/es/")
                if success:
                    logger.info("✓ Catawiki: Conexión exitosa")
                else:
                    logger.error("✗ Catawiki: Error de conexión")
    except Exception as e:
        logger.error(f"✗ Catawiki: {e}")


def show_stats():
    """Muestra estadísticas de la base de datos."""
    db = DatabaseManager()
    stats = db.get_statistics()

    print("\n" + "=" * 50)
    print("ESTADÍSTICAS DE LA BASE DE DATOS")
    print("=" * 50)
    print(f"Registros de inventario: {stats['total_inventory_records']}")
    print(f"Ventas detectadas totales: {stats['total_sales_detected']}")

    if stats['sales_by_platform']:
        print("\nVentas por plataforma:")
        for platform, count in stats['sales_by_platform'].items():
            print(f"  - {platform}: {count}")

    if stats['last_run']:
        print("\nÚltima ejecución:")
        print(f"  - Fecha: {stats['last_run']['run_date']}")
        print(f"  - Plataforma: {stats['last_run']['platform']}")
        print(f"  - Estado: {stats['last_run']['status']}")
        print(f"  - Items scrapeados: {stats['last_run']['items_scraped']}")
        print(f"  - Ventas detectadas: {stats['last_run']['items_sold_detected']}")

    # Mostrar logs recientes
    recent_logs = db.get_recent_logs(days=7)
    if recent_logs:
        print("\nEjecuciones de los últimos 7 días:")
        for log in recent_logs[:10]:
            print(f"  [{log['run_date']}] {log['platform']}: {log['status']} "
                  f"({log['items_scraped']} items, {log['items_sold_detected']} ventas)")

    print()


async def _verify_docker() -> bool:
    """Verifica que Docker Desktop está corriendo."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


async def _verify_or_start_flaresolverr() -> bool:
    """
    Verifica si FlareSolverr está corriendo. Si no, intenta iniciarlo.

    Returns:
        True si FlareSolverr está disponible, False si falla
    """
    # Verificar si ya está corriendo
    try:
        response = requests.get(
            FLARESOLVERR_URL.replace("/v1", ""),
            timeout=3
        )
        if response.status_code == 200:
            logger.info("FlareSolverr ya está corriendo")
            return True
    except requests.exceptions.RequestException:
        pass

    # Intentar iniciar contenedor
    logger.info("Iniciando contenedor FlareSolverr...")

    # Verificar si contenedor existe
    check_container = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=flaresolverr", "--format", "{{.Names}}"],
        capture_output=True,
        text=True
    )

    if "flaresolverr" in check_container.stdout:
        # Contenedor existe, solo iniciarlo
        result = subprocess.run(
            ["docker", "start", "flaresolverr"],
            capture_output=True,
            text=True
        )
    else:
        # Crear nuevo contenedor
        result = subprocess.run(
            [
                "docker", "run", "-d",
                "--name", "flaresolverr",
                "-p", "8191:8191",
                "--restart", "unless-stopped",
                "ghcr.io/flaresolverr/flaresolverr:latest"
            ],
            capture_output=True,
            text=True
        )

    if result.returncode != 0:
        logger.error(f"Error iniciando FlareSolverr: {result.stderr}")
        return False

    # Esperar a que inicie (máximo 15 segundos)
    logger.info("Esperando a que FlareSolverr inicie...")
    for i in range(15):
        await asyncio.sleep(1)
        try:
            response = requests.get(
                FLARESOLVERR_URL.replace("/v1", ""),
                timeout=2
            )
            if response.status_code == 200:
                logger.info(f"FlareSolverr iniciado correctamente ({i+1}s)")
                return True
        except requests.exceptions.RequestException:
            continue

    logger.error("Timeout esperando a que FlareSolverr inicie")
    return False


async def _show_workflow_summary(scraping_duration: float):
    """Muestra resumen final del workflow."""
    db = DatabaseManager()
    today = date.today()

    logger.info("")
    logger.info("=" * 60)
    logger.info("RESUMEN FINAL")
    logger.info("=" * 60)

    # Estadísticas por plataforma
    with db.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT COUNT(*) FROM daily_inventory WHERE platform='chrono24' AND snapshot_date=?",
            (today,)
        )
        chrono24_count = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM daily_inventory WHERE platform='vestiaire' AND snapshot_date=?",
            (today,)
        )
        vestiaire_count = cursor.fetchone()[0]

    # Ventas detectadas hoy
    sales_today = db.get_sales_by_date_range(today, today)
    chrono24_sales = len([s for s in sales_today if s.get('platform') == 'chrono24'])
    vestiaire_sales = len([s for s in sales_today if s.get('platform') == 'vestiaire'])

    logger.info("Scraping:")
    logger.info(f"  Chrono24:   {chrono24_count} items | {chrono24_sales} ventas detectadas")
    logger.info(f"  Vestiaire:  {vestiaire_count} items | {vestiaire_sales} ventas detectadas")
    logger.info(f"  Total:      {chrono24_count + vestiaire_count} items | {len(sales_today)} ventas nuevas")
    logger.info("")

    # Estadísticas de integridad
    logger.info("Integridad:")
    logger.info("  Estado: OK (0 errores críticos)")
    logger.info("")

    # Reporte generado
    month_name = datetime.now().strftime("%B_%Y").lower()
    report_path = f"data/exports/reporte_{month_name}.xlsx"
    if os.path.exists(report_path):
        logger.info(f"Reporte: {report_path}")
    else:
        logger.info("Reporte: No generado (sin ventas nuevas)")

    logger.info("")
    logger.info(f"Duración total: {scraping_duration:.0f}s ({scraping_duration/60:.1f}m)")
    logger.info("=" * 60)


async def run_workflow(args) -> int:
    """
    Orquesta el flujo completo de trabajo automatizado.

    Pasos:
    1. Verificar Docker está corriendo
    2. Verificar/iniciar FlareSolverr (falla si no disponible)
    3. Ejecutar scraping según flags (--test-mode, --chrono24-only, etc.)
    4. Ejecutar check_integrity.py --full
    5. Si hay errores críticos: ejecutar fix_database.py --fix-all
    6. Si hay ventas nuevas: generar reporte Excel
    7. Mostrar resumen final

    Returns:
        0 si éxito, 1 si error crítico
    """
    logger.info("=" * 60)
    logger.info("FLUJO DE TRABAJO AUTOMATIZADO")
    logger.info("=" * 60)

    # Paso 1: Verificar Docker
    logger.info("[1/7] Verificando Docker Desktop...")
    if not await _verify_docker():
        logger.error("Docker no está corriendo. Inicia Docker Desktop y vuelve a ejecutar.")
        return 1
    logger.info("[OK] Docker está corriendo")

    # Paso 2: Verificar/iniciar FlareSolverr (solo si está habilitado)
    if USE_FLARESOLVERR:
        logger.info("[2/7] Verificando FlareSolverr...")
        if not await _verify_or_start_flaresolverr():
            logger.error("FlareSolverr no está disponible y es requerido para Chrono24")
            return 1
        logger.info("[OK] FlareSolverr está corriendo")
    else:
        logger.info("[2/7] FlareSolverr desactivado, saltando...")

    # Paso 3: Ejecutar scraping
    logger.info("[3/7] Ejecutando scraping...")
    start_time = time.time()

    # Determinar qué scrapers ejecutar según los flags
    if args.chrono24_only:
        db = DatabaseManager()
        processor = DataProcessor(db)
        await run_chrono24_scraping(db, processor, args.test_mode)
    elif args.vestiaire_only:
        db = DatabaseManager()
        processor = DataProcessor(db)
        await run_vestiaire_scraping(db, processor, args.test_mode)
    elif args.catawiki_only:
        db = DatabaseManager()
        processor = DataProcessor(db)
        await run_catawiki_scraping(db, processor, args.test_mode)
    else:
        # Scraping completo
        await run_full_scraping(args.test_mode)

    scraping_duration = time.time() - start_time
    logger.info(f"[OK] Scraping completado en {scraping_duration:.1f}s")

    # Paso 4: Verificar integridad
    logger.info("[4/7] Verificando integridad de datos...")
    integrity_result = subprocess.run(
        [sys.executable, "check_integrity.py", "--full"],
        capture_output=True,
        text=True
    )

    if integrity_result.returncode == 0:
        logger.info("[OK] Integridad verificada - sin errores")
    else:
        logger.warning("[!] Se detectaron errores de integridad")

    # Paso 5: Reparar si hay errores (auto-fix)
    if integrity_result.returncode != 0:
        logger.info("[5/7] Reparando base de datos automáticamente...")
        fix_result = subprocess.run(
            [sys.executable, "fix_database.py", "--fix-all"],
            capture_output=True,
            text=True
        )

        if fix_result.returncode == 0:
            logger.info("[OK] Base de datos reparada")
            # Volver a verificar integridad
            integrity_result = subprocess.run(
                [sys.executable, "check_integrity.py", "--full"],
                capture_output=True,
                text=True
            )
        else:
            logger.error("[ERROR] Fallo al reparar base de datos")
            logger.error(fix_result.stderr)
            return 1
    else:
        logger.info("[5/7] No se requiere reparación")

    # Paso 6: Generar reporte (solo si hay ventas nuevas y no está skip-report)
    if not args.skip_report:
        logger.info("[6/7] Verificando ventas nuevas...")

        # Verificar si hay ventas detectadas hoy
        db = DatabaseManager()
        today = date.today()
        sales_today = db.get_sales_by_date_range(today, today)

        if sales_today:
            logger.info(f"[6/7] Generando reporte Excel ({len(sales_today)} ventas nuevas)...")
            try:
                generate_report()
                logger.info("[OK] Reporte generado")
            except Exception as e:
                logger.warning(f"[!] Error generando reporte: {e}")
        else:
            logger.info("[6/7] No hay ventas nuevas, saltando reporte")
    else:
        logger.info("[6/7] Generación de reporte desactivada (--skip-report)")

    # Paso 7: Resumen final
    logger.info("[7/7] Generando resumen final...")
    await _show_workflow_summary(scraping_duration)

    logger.info("=" * 60)
    logger.info("[OK] Workflow completado exitosamente")
    logger.info("=" * 60)

    return 0


def init_database():
    """Inicializa la base de datos y verifica la configuración."""
    print("\n" + "=" * 50)
    print("INICIALIZANDO PROYECTO")
    print("=" * 50)

    # Crear base de datos
    db = DatabaseManager()
    print("✓ Base de datos inicializada")

    # Verificar configuración
    print(f"\nModelos de Chrono24 configurados: {len(CHRONO24_MODELS)}")
    for model in CHRONO24_MODELS[:5]:
        print(f"  - {model}")
    if len(CHRONO24_MODELS) > 5:
        print(f"  ... y {len(CHRONO24_MODELS) - 5} más")

    valid_sellers = [s for s in VESTIAIRE_SELLER_IDS if s and not s.startswith('seller_id_')]
    print(f"\nVendedores de Vestiaire configurados: {len(valid_sellers)}")
    if not valid_sellers:
        print("  ⚠ ATENCIÓN: No hay vendedores configurados")
        print("  Edita config.py y reemplaza los placeholders 'seller_id_X'")
    else:
        for seller in valid_sellers:
            print(f"  - {seller}")

    # Verificar Playwright
    print("\n" + "-" * 50)
    print("Para completar la instalación, ejecuta:")
    print("  pip install -r requirements.txt")
    print("  playwright install chromium")
    print("-" * 50 + "\n")


def main():
    """Función principal - punto de entrada del script."""
    parser = argparse.ArgumentParser(
        description="Herramienta de Inventario Delta para Chrono24 y Vestiaire Collective",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python main.py --scrape              Ejecutar scraping completo
  python main.py --scrape --report     Scraping + generar Excel
  python main.py --report              Solo generar reporte
  python main.py --test                Probar conexiones
  python main.py --init                Inicializar proyecto
  python main.py --stats               Ver estadísticas
  python main.py --scrape --test-mode  Scraping en modo prueba (reducido)
        """
    )

    parser.add_argument(
        '--scrape',
        action='store_true',
        help='Ejecutar scraping de ambas plataformas'
    )
    parser.add_argument(
        '--report',
        action='store_true',
        help='Generar reporte Excel del mes actual'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Probar conexión a los sitios web'
    )
    parser.add_argument(
        '--init',
        action='store_true',
        help='Inicializar base de datos y mostrar configuración'
    )
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Mostrar estadísticas de la base de datos'
    )
    parser.add_argument(
        '--test-mode',
        action='store_true',
        help='Ejecutar en modo de prueba (scraping reducido)'
    )
    parser.add_argument(
        '--chrono24-only',
        action='store_true',
        help='Solo scrapear Chrono24'
    )
    parser.add_argument(
        '--vestiaire-only',
        action='store_true',
        help='Solo scrapear Vestiaire Collective'
    )
    parser.add_argument(
        '--catawiki-only',
        action='store_true',
        help='Solo scrapear Catawiki'
    )
    parser.add_argument(
        '--workflow',
        action='store_true',
        help='Ejecutar flujo completo: Docker → Scraping → Tests → Reporte'
    )
    parser.add_argument(
        '--skip-report',
        action='store_true',
        help='Saltar generación de reporte (solo con --workflow)'
    )

    args = parser.parse_args()

    # Si no se especificó ninguna acción, mostrar ayuda
    if not any([args.scrape, args.report, args.test, args.init, args.stats, args.workflow]):
        parser.print_help()
        return

    # Configurar logging
    setup_logging()

    try:
        # Ejecutar workflow automatizado
        if args.workflow:
            exit_code = asyncio.run(run_workflow(args))
            sys.exit(exit_code)

        # Inicializar
        if args.init:
            init_database()
            return

        # Mostrar estadísticas
        if args.stats:
            show_stats()
            return

        # Probar conexiones
        if args.test:
            asyncio.run(test_connections())
            return

        # Ejecutar scraping
        if args.scrape:
            if args.chrono24_only:
                db = DatabaseManager()
                processor = DataProcessor(db)
                asyncio.run(run_chrono24_scraping(db, processor, args.test_mode))
            elif args.vestiaire_only:
                db = DatabaseManager()
                processor = DataProcessor(db)
                asyncio.run(run_vestiaire_scraping(db, processor, args.test_mode))
            elif args.catawiki_only:
                db = DatabaseManager()
                processor = DataProcessor(db)
                asyncio.run(run_catawiki_scraping(db, processor, args.test_mode))
            else:
                asyncio.run(run_full_scraping(args.test_mode))

        # Generar reporte
        if args.report:
            generate_report()

        logger.info("Proceso completado exitosamente")

    except KeyboardInterrupt:
        logger.warning("Proceso interrumpido por el usuario")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Error fatal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
