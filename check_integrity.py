#!/usr/bin/env python3
"""
Script de verificación rápida de integridad de datos.
No requiere pytest - ejecuta verificaciones directamente.

Uso:
    python check_integrity.py [--full] [--report-only]
"""

import sys
import argparse
from pathlib import Path
from datetime import date, timedelta
from typing import List, Dict, Any

# Añadir directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent))

from database.db_manager import DatabaseManager
from config import DATABASE_PATH


class IntegrityChecker:
    """Verificador de integridad de datos sin dependencias externas."""

    def __init__(self, db_path=None):
        self.db = DatabaseManager(db_path or DATABASE_PATH)
        self.errors = []
        self.warnings = []
        self.passed_checks = []

    def check(self, test_name: str, condition: bool, error_msg: str, is_warning: bool = False):
        """Registra el resultado de una verificación."""
        if condition:
            self.passed_checks.append(test_name)
            print(f"[OK] {test_name}")
        else:
            if is_warning:
                self.warnings.append((test_name, error_msg))
                print(f"[!] {test_name}: {error_msg}")
            else:
                self.errors.append((test_name, error_msg))
                print(f"[X] {test_name}: {error_msg}")

    def run_all_checks(self, quick: bool = False):
        """Ejecuta todas las verificaciones de integridad."""
        print("\n" + "="*70)
        print("VERIFICACION DE INTEGRIDAD DE DATOS")
        print("="*70 + "\n")

        # 1. Duplicados en inventario diario
        print("[*] Verificando duplicados en inventario...")
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as count FROM (
                    SELECT platform, listing_id, snapshot_date, COUNT(*) as cnt
                    FROM daily_inventory
                    GROUP BY platform, listing_id, snapshot_date
                    HAVING cnt > 1
                )
            """)
            dup_count = dict(cursor.fetchone())['count']

        self.check(
            "No hay duplicados en inventario diario",
            dup_count == 0,
            f"Se encontraron {dup_count} duplicados en daily_inventory"
        )

        # 2. Duplicados en ventas (mismo día)
        print("\n[*] Verificando duplicados en ventas...")
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as count FROM (
                    SELECT platform, listing_id, detection_date, COUNT(*) as cnt
                    FROM detected_sales
                    GROUP BY platform, listing_id, detection_date
                    HAVING cnt > 1
                )
            """)
            sales_dup = dict(cursor.fetchone())['count']

        self.check(
            "No hay ventas duplicadas en la misma fecha",
            sales_dup == 0,
            f"[X] CRITICO: {sales_dup} ventas duplicadas detectadas el mismo dia"
        )

        # 3. CRÍTICO: Falsos positivos
        print("\n[*] Verificando falsos positivos (productos vendidos que reaparecen)...")
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT s.platform, s.listing_id, s.detection_date
                FROM detected_sales s
            """)
            sold_items = cursor.fetchall()

            false_positives = []
            for sold_item in sold_items:
                sold_dict = dict(sold_item)
                platform = sold_dict['platform']
                listing_id = sold_dict['listing_id']
                detection_date = sold_dict['detection_date']

                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM daily_inventory
                    WHERE platform = ? AND listing_id = ? AND snapshot_date >= ?
                """, (platform, listing_id, detection_date))

                reappearance_count = dict(cursor.fetchone())['count']
                if reappearance_count > 0:
                    false_positives.append((platform, listing_id, detection_date))

        self.check(
            "No hay productos vendidos que reaparezcan",
            len(false_positives) == 0,
            f"[X] CRITICO: {len(false_positives)} falsos positivos (productos 'vendidos' que reaparecieron)"
        )

        if false_positives and len(false_positives) <= 10:
            print("   Ejemplos de falsos positivos:")
            for platform, listing_id, det_date in false_positives[:5]:
                print(f"     - {platform}: {listing_id} (detectado vendido: {det_date})")

        # 4. Ventas con precios válidos
        print("\n[*] Verificando precios de ventas...")
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN sale_price IS NULL OR sale_price <= 0 THEN 1 ELSE 0 END) as invalid
                FROM detected_sales
            """)
            price_stats = dict(cursor.fetchone())

        total_sales = price_stats['total']
        invalid_prices = price_stats['invalid']

        if total_sales > 0:
            invalid_pct = (invalid_prices / total_sales) * 100
            self.check(
                "Menos del 10% de ventas sin precio válido",
                invalid_pct < 10,
                f"{invalid_prices}/{total_sales} ventas sin precio válido ({invalid_pct:.1f}%)",
                is_warning=(invalid_pct < 20)  # Warning si <20%, error si >=20%
            )

        # 5. Fechas coherentes
        print("\n[*] Verificando fechas...")
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM detected_sales
                WHERE detection_date > date('now')
            """)
            future_dates = dict(cursor.fetchone())['count']

        self.check(
            "No hay ventas con fechas futuras",
            future_dates == 0,
            f"{future_dates} ventas con fechas en el futuro"
        )

        # 6. Caídas sospechosas en inventario (solo si no es quick)
        if not quick:
            print("\n[*] Verificando consistencia de inventario en el tiempo...")
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT platform, snapshot_date, COUNT(*) as count
                    FROM daily_inventory
                    GROUP BY platform, snapshot_date
                    ORDER BY platform, snapshot_date
                """)
                daily_counts = cursor.fetchall()

            suspicious_drops = []
            prev_platform = None
            prev_count = None
            prev_date = None

            for row in daily_counts:
                d = dict(row)
                platform = d['platform']
                current_date = d['snapshot_date']
                count = d['count']

                if platform == prev_platform and prev_count is not None:
                    drop_percentage = ((prev_count - count) / prev_count) * 100
                    if drop_percentage > 90:
                        suspicious_drops.append({
                            'platform': platform,
                            'from_date': prev_date,
                            'to_date': current_date,
                            'drop': f"{prev_count} → {count}",
                            'drop_pct': round(drop_percentage, 1)
                        })

                prev_platform = platform
                prev_count = count
                prev_date = current_date

            self.check(
                "No hay caídas sospechosas de inventario (>90%)",
                len(suspicious_drops) == 0,
                f"{len(suspicious_drops)} caídas sospechosas detectadas",
                is_warning=True
            )

            if suspicious_drops:
                print("   Caídas detectadas:")
                for drop in suspicious_drops[:3]:
                    print(f"     - {drop['platform']}: {drop['drop']} ({drop['drop_pct']}%) el {drop['to_date']}")

        # Resumen final
        print("\n" + "="*70)
        print("RESUMEN")
        print("="*70)
        print(f"[OK] Verificaciones pasadas: {len(self.passed_checks)}")
        print(f"[!] Advertencias: {len(self.warnings)}")
        print(f"[X] Errores criticos: {len(self.errors)}")
        print("="*70 + "\n")

        if self.errors:
            print("[X] ERRORES CRITICOS DETECTADOS:")
            for test_name, error_msg in self.errors:
                print(f"   - {test_name}: {error_msg}")
            print()

        if self.warnings:
            print("[!] ADVERTENCIAS:")
            for test_name, warning_msg in self.warnings:
                print(f"   - {test_name}: {warning_msg}")
            print()

        return len(self.errors) == 0

    def generate_report(self):
        """Genera un reporte completo de estadísticas."""
        stats = self.db.get_statistics()

        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Plataformas activas
            cursor.execute("SELECT DISTINCT platform FROM daily_inventory")
            platforms = [dict(r)['platform'] for r in cursor.fetchall()]

            # Rango de fechas
            cursor.execute("""
                SELECT MIN(snapshot_date) as oldest, MAX(snapshot_date) as newest
                FROM daily_inventory
            """)
            date_range = dict(cursor.fetchone())

            # Precios estimados vs reales
            cursor.execute("""
                SELECT
                    SUM(CASE WHEN price_is_estimated = 1 THEN 1 ELSE 0 END) as estimated,
                    SUM(CASE WHEN price_is_estimated = 0 THEN 1 ELSE 0 END) as real
                FROM detected_sales
            """)
            price_types = dict(cursor.fetchone())

            # Ventas del último mes
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM detected_sales
                WHERE detection_date >= date('now', '-30 days')
            """)
            recent_sales = dict(cursor.fetchone())['count']

        print("\n" + "="*70)
        print("REPORTE DE INTEGRIDAD DE DATOS")
        print("="*70)
        print(f"\n[ESTADISTICAS GENERALES]")
        print(f"  - Total registros en inventario: {stats['total_inventory_records']:,}")
        print(f"  - Total ventas detectadas: {stats['total_sales_detected']:,}")
        print(f"  - Ventas ultimos 30 dias: {recent_sales:,}")
        print(f"  - Plataformas: {', '.join(platforms)}")

        if date_range['oldest'] and date_range['newest']:
            print(f"  - Rango de fechas: {date_range['oldest']} -> {date_range['newest']}")

        print(f"\n[PRECIOS DE VENTAS]")
        print(f"  - Precios reales: {price_types.get('real', 0):,}")
        print(f"  - Precios estimados: {price_types.get('estimated', 0):,}")

        print(f"\n[VENTAS POR PLATAFORMA]")
        for platform, count in stats['sales_by_platform'].items():
            print(f"  - {platform}: {count:,} ventas")

        if stats.get('last_run'):
            last_run = stats['last_run']
            print(f"\n[ULTIMA EJECUCION]")
            print(f"  - Fecha: {last_run['run_date']}")
            print(f"  - Plataforma: {last_run['platform']}")
            print(f"  - Estado: {last_run['status']}")
            print(f"  - Items scrapeados: {last_run['items_scraped']}")

        print("="*70 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Verificación de integridad de datos del scraper"
    )
    parser.add_argument(
        '--full',
        action='store_true',
        help='Ejecutar verificación completa (incluye checks lentos)'
    )
    parser.add_argument(
        '--report-only',
        action='store_true',
        help='Solo generar reporte de estadísticas (sin verificar integridad)'
    )

    args = parser.parse_args()

    checker = IntegrityChecker()

    if args.report_only:
        checker.generate_report()
        return 0

    # Ejecutar verificaciones
    quick = not args.full
    all_passed = checker.run_all_checks(quick=quick)

    # Generar reporte
    checker.generate_report()

    # Retornar código de salida
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
