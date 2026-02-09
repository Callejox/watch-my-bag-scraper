#!/usr/bin/env python3
"""
Eliminación Masiva de Ventas Falsas de Chrono24

Elimina TODAS las ventas de Chrono24 de la base de datos.
Estas ventas son falsos positivos causados por cobertura insuficiente
del scraper (bug max_pages=5 corregido).

Uso:
    py bulk_delete_chrono24.py              # Preview
    py bulk_delete_chrono24.py --execute    # Eliminar

Requiere confirmación explícita del usuario.
Backup automático antes de eliminar.

Autor: Generado con Claude Code
Fecha: 2026-02-09
"""

import argparse
import shutil
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

# Importar configuración del proyecto
import sys
sys.path.insert(0, str(Path(__file__).parent))
from database.db_manager import DatabaseManager
from config import DATABASE_PATH


def create_backup(db_path: Path) -> Path:
    """
    Crea backup de la base de datos con timestamp.

    Args:
        db_path: Path a la base de datos

    Returns:
        Path del archivo de backup creado
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"{db_path.stem}_before_chrono24_cleanup_{timestamp}{db_path.suffix}"
    backup_path = db_path.parent / backup_filename

    shutil.copy2(db_path, backup_path)
    print(f"[OK] Backup creado: {backup_path.name}")
    return backup_path


def preview_chrono24_sales(db: DatabaseManager) -> tuple:
    """
    Muestra preview de ventas a eliminar.

    Args:
        db: Instancia de DatabaseManager

    Returns:
        tuple: (total_count, sample_sales)
    """
    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Contar total
        cursor.execute("SELECT COUNT(*) FROM detected_sales WHERE platform='chrono24'")
        total = cursor.fetchone()[0]

        # Obtener muestra
        cursor.execute("""
            SELECT listing_id, detection_date, sale_price, specific_model, url
            FROM detected_sales
            WHERE platform='chrono24'
            ORDER BY detection_date DESC
            LIMIT 10
        """)
        sample = [dict(row) for row in cursor.fetchall()]

    return total, sample


def display_preview(total: int, sample: list):
    """
    Muestra preview formateado en consola.

    Args:
        total: Número total de ventas a eliminar
        sample: Lista de diccionarios con muestra de ventas
    """
    print("\n" + "="*80)
    print("PREVIEW: Ventas de Chrono24 a Eliminar")
    print("="*80)
    print(f"\n[!] Total a eliminar: {total} ventas\n")

    if sample:
        print("Muestra (primeras 10):")
        for sale in sample:
            price = f"€{sale['sale_price']:.0f}" if sale['sale_price'] else "Sin precio"
            model = sale['specific_model'] or "Sin modelo"
            print(f"  {sale['listing_id']:12} | {sale['detection_date']} | {price:10} | {model[:40]}")

    print("\n" + "="*80 + "\n")


def delete_chrono24_sales(db: DatabaseManager) -> int:
    """
    Elimina TODAS las ventas de Chrono24.

    Args:
        db: Instancia de DatabaseManager

    Returns:
        Número de registros eliminados
    """
    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Eliminar todas las ventas de Chrono24
        cursor.execute("DELETE FROM detected_sales WHERE platform='chrono24'")
        deleted_count = cursor.rowcount

        # Logging en scrape_logs para auditoría
        cursor.execute("""
            INSERT INTO scrape_logs (
                platform, status, items_scraped, items_sold_detected,
                errors, duration_seconds, run_date
            ) VALUES (?, ?, ?, ?, ?, ?, date('now'))
        """, (
            'chrono24_cleanup',
            'success',
            0,
            -deleted_count,  # Negativo para indicar eliminación
            f'Eliminación masiva de {deleted_count} falsos positivos de Chrono24 (bug max_pages corregido)',
            0
        ))

        conn.commit()

    return deleted_count


def run_integrity_check() -> bool:
    """
    Ejecuta check_integrity.py --full automáticamente.

    Returns:
        True si pasó todas las verificaciones
    """
    print("\n[*] Ejecutando verificación de integridad...\n")
    try:
        result = subprocess.run(
            ["py", "check_integrity.py", "--full"],
            capture_output=False,
            cwd=Path(__file__).parent
        )
        return result.returncode == 0
    except Exception as e:
        print(f"[!] Error ejecutando check_integrity.py: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Eliminación masiva de ventas falsas de Chrono24",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  py bulk_delete_chrono24.py              # Ver preview sin modificar
  py bulk_delete_chrono24.py --execute    # Ejecutar eliminación
        """
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Ejecutar eliminación (requiere confirmación explícita)'
    )
    args = parser.parse_args()

    # Header
    print("="*80)
    print("ELIMINACIÓN MASIVA DE VENTAS DE CHRONO24")
    print("="*80)
    print("\n[CONTEXTO]")
    print("  Estas ventas son falsos positivos causados por:")
    print("  - Bug en main.py (max_pages=5 hardcoded, ya corregido)")
    print("  - Cobertura insuficiente: 5/352 páginas (1.4%)")
    print("  - Productos en páginas 6-352 nunca detectados")
    print("\n" + "="*80 + "\n")

    # Conectar a base de datos
    try:
        db = DatabaseManager(DATABASE_PATH)
    except Exception as e:
        print(f"[X] Error conectando a base de datos: {e}")
        return 1

    # Preview de ventas a eliminar
    try:
        total, sample = preview_chrono24_sales(db)
    except Exception as e:
        print(f"[X] Error obteniendo preview: {e}")
        return 1

    if total == 0:
        print("[OK] No hay ventas de Chrono24 para eliminar\n")
        return 0

    display_preview(total, sample)

    # Modo preview (sin --execute)
    if not args.execute:
        print("[INFO] Modo PREVIEW")
        print("Para ejecutar eliminación:")
        print("  py bulk_delete_chrono24.py --execute\n")
        return 0

    # Confirmación explícita del usuario
    print("[!] ADVERTENCIA: Esta operación eliminará TODAS las ventas de Chrono24")
    print(f"[!] Total a eliminar: {total} registros")
    print("\n[!] Esta operación es irreversible (excepto por restauración de backup)")
    confirmation = input(f"\n¿Eliminar {total} ventas de Chrono24? (escriba 'ELIMINAR' para confirmar): ")

    if confirmation != "ELIMINAR":
        print("\n[INFO] Operación cancelada por el usuario\n")
        return 0

    # Crear backup antes de modificar
    print("\n[*] Creando backup de la base de datos...")
    try:
        backup_path = create_backup(DATABASE_PATH)
    except Exception as e:
        print(f"[X] Error creando backup: {e}")
        print("[X] Operación abortada por seguridad")
        return 1

    # Eliminar ventas
    print(f"[*] Eliminando {total} ventas de Chrono24...")
    try:
        deleted = delete_chrono24_sales(db)
    except Exception as e:
        print(f"[X] Error eliminando ventas: {e}")
        print(f"[!] Restaurar desde backup: {backup_path}")
        return 1

    # Resumen de eliminación
    print("\n" + "="*80)
    print("ELIMINACIÓN COMPLETADA")
    print("="*80)
    print(f"\n[OK] Eliminadas: {deleted} ventas de Chrono24")
    print(f"[OK] Backup: {backup_path.name}")
    print("\n" + "="*80 + "\n")

    # Verificación de integridad automática
    integrity_ok = run_integrity_check()

    # Próximos pasos recomendados
    print("\n" + "="*80)
    print("PRÓXIMOS PASOS")
    print("="*80)

    if integrity_ok:
        print("[OK] Base de datos verificada correctamente")
    else:
        print("[!] Se detectaron problemas de integridad")
        print("[!] Revisar output de check_integrity.py arriba")

    print("\nRecomendado:")
    print("  1. Ejecutar scraping con nueva configuración:")
    print("     py main.py --scrape --chrono24-only")
    print("\n  2. Verificar que max_pages=20 en config.py:")
    print("     py -c \"from config import CHRONO24_MAX_PAGES; print(f'max_pages={CHRONO24_MAX_PAGES}')\"")
    print("\n  3. Monitorear logs para confirmar cobertura mejorada")
    print("     - Logs: logs/scraper_YYYY-MM-DD.log")
    print("     - Buscar: 'PRE-SCRAPING' para ver páginas detectadas vs scrapeadas")
    print("\n  4. Verificar tests avanzados (día 1-3):")
    print("     py check_sales_validity.py")
    print("="*80 + "\n")

    return 0 if integrity_ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
