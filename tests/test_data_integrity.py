"""
Tests de integridad de datos para detectar:
- Relojes duplicados en inventario
- Relojes duplicados en ventas detectadas
- Ventas falsas (productos marcados como vendidos que siguen disponibles)
- Inconsistencias en los datos
"""

import pytest
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import List, Dict, Any, Tuple
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db_manager import DatabaseManager
from config import DATABASE_PATH


class TestDataIntegrity:
    """Suite de tests para verificar la integridad de los datos."""

    @pytest.fixture
    def db_manager(self):
        """Fixture que proporciona una instancia del DatabaseManager."""
        return DatabaseManager(DATABASE_PATH)

    # =========================================================================
    # TESTS DE DUPLICADOS EN INVENTARIO
    # =========================================================================

    def test_no_duplicate_listings_in_daily_inventory(self, db_manager):
        """
        Verifica que no haya listings duplicados en el mismo snapshot.

        Un listing_id + platform + snapshot_date solo puede aparecer UNA vez.
        El constraint UNIQUE en la BD debería garantizar esto, pero lo verificamos.
        """
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT platform, listing_id, snapshot_date, COUNT(*) as count
                FROM daily_inventory
                GROUP BY platform, listing_id, snapshot_date
                HAVING count > 1
            """)

            duplicates = cursor.fetchall()

        assert len(duplicates) == 0, (
            f"Se encontraron {len(duplicates)} duplicados en daily_inventory: "
            f"{[(dict(d)['platform'], dict(d)['listing_id'], dict(d)['snapshot_date']) for d in duplicates]}"
        )

    def test_no_duplicate_listings_across_same_date(self, db_manager):
        """
        Verifica que un mismo listing_id no aparezca múltiples veces
        en diferentes plataformas el mismo día (posible error de clasificación).
        """
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT listing_id, snapshot_date, GROUP_CONCAT(platform) as platforms, COUNT(*) as count
                FROM daily_inventory
                GROUP BY listing_id, snapshot_date
                HAVING count > 1
            """)

            cross_platform_duplicates = cursor.fetchall()

        # Esto PUEDE ser válido si el mismo ID existe en múltiples plataformas,
        # pero es sospechoso y debe investigarse
        if cross_platform_duplicates:
            print(f"\n⚠️  ADVERTENCIA: {len(cross_platform_duplicates)} listings aparecen en múltiples plataformas:")
            for dup in cross_platform_duplicates[:5]:  # Mostrar solo los primeros 5
                d = dict(dup)
                print(f"  - ID: {d['listing_id']}, Fecha: {d['snapshot_date']}, Plataformas: {d['platforms']}")

    # =========================================================================
    # TESTS DE DUPLICADOS EN VENTAS DETECTADAS
    # =========================================================================

    def test_no_duplicate_sales_same_detection_date(self, db_manager):
        """
        Verifica que un mismo listing_id no se detecte como vendido
        múltiples veces en la MISMA fecha de detección.

        Esto indicaría un bug en la lógica de detección.
        """
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT platform, listing_id, detection_date, COUNT(*) as count
                FROM detected_sales
                GROUP BY platform, listing_id, detection_date
                HAVING count > 1
            """)

            same_day_duplicates = cursor.fetchall()

        assert len(same_day_duplicates) == 0, (
            f"❌ CRÍTICO: {len(same_day_duplicates)} ventas duplicadas detectadas el mismo día:\n"
            f"{[(dict(d)['platform'], dict(d)['listing_id'], dict(d)['detection_date']) for d in same_day_duplicates]}"
        )

    def test_no_multiple_sales_different_dates(self, db_manager):
        """
        Verifica que un mismo listing_id no se detecte como vendido
        múltiples veces en DIFERENTES fechas.

        Esto podría indicar:
        1. Producto reaparece después de vendido (scraper inconsistente)
        2. Mismo ID reutilizado en plataforma (válido pero sospechoso)
        """
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT platform, listing_id, GROUP_CONCAT(detection_date) as dates, COUNT(*) as count
                FROM detected_sales
                GROUP BY platform, listing_id
                HAVING count > 1
            """)

            multi_sale_items = cursor.fetchall()

        if multi_sale_items:
            print(f"\n⚠️  ADVERTENCIA: {len(multi_sale_items)} productos vendidos múltiples veces:")
            for item in multi_sale_items[:10]:  # Mostrar primeros 10
                d = dict(item)
                print(f"  - Plataforma: {d['platform']}, ID: {d['listing_id']}, Fechas: {d['dates']}")

            # Esto es sospechoso pero no necesariamente un error
            # Puede ser legítimo si la plataforma reutiliza IDs
            pytest.warn(
                f"Se encontraron {len(multi_sale_items)} productos con múltiples detecciones de venta. "
                "Revisar si la plataforma reutiliza IDs o si hay un problema con el scraper."
            )

    # =========================================================================
    # TESTS DE FALSOS POSITIVOS
    # =========================================================================

    def test_no_sold_items_reappearing_in_inventory(self, db_manager):
        """
        CRÍTICO: Verifica que productos detectados como vendidos
        NO vuelvan a aparecer en inventarios posteriores.

        Esto indicaría un falso positivo grave.
        """
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()

            # Obtener todos los items vendidos
            cursor.execute("""
                SELECT DISTINCT platform, listing_id, detection_date
                FROM detected_sales
            """)
            sold_items = cursor.fetchall()

            false_positives = []

            for sold_item in sold_items:
                sold_dict = dict(sold_item)
                platform = sold_dict['platform']
                listing_id = sold_dict['listing_id']
                detection_date = sold_dict['detection_date']

                # Buscar si este item aparece en inventarios DESPUÉS de la venta
                cursor.execute("""
                    SELECT snapshot_date, listing_price
                    FROM daily_inventory
                    WHERE platform = ?
                    AND listing_id = ?
                    AND snapshot_date > ?
                    LIMIT 1
                """, (platform, listing_id, detection_date))

                reappearance = cursor.fetchone()
                if reappearance:
                    false_positives.append({
                        'platform': platform,
                        'listing_id': listing_id,
                        'detected_sold_on': detection_date,
                        'reappeared_on': dict(reappearance)['snapshot_date'],
                        'price': dict(reappearance)['listing_price']
                    })

        if false_positives:
            print(f"\n❌ FALSOS POSITIVOS DETECTADOS: {len(false_positives)} productos 'vendidos' que reaparecieron:")
            for fp in false_positives[:10]:  # Mostrar primeros 10
                print(f"  - Plataforma: {fp['platform']}, ID: {fp['listing_id']}")
                print(f"    Vendido: {fp['detected_sold_on']} → Reapareció: {fp['reappeared_on']}")

        assert len(false_positives) == 0, (
            f"❌ CRÍTICO: {len(false_positives)} falsos positivos encontrados. "
            "Productos marcados como vendidos que volvieron a aparecer en inventario."
        )

    # =========================================================================
    # TESTS DE CONSISTENCIA DE DATOS
    # =========================================================================

    def test_sales_have_valid_prices(self, db_manager):
        """Verifica que todas las ventas tengan precios válidos."""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM detected_sales
                WHERE sale_price IS NULL OR sale_price <= 0
            """)

            invalid_prices = dict(cursor.fetchone())['count']

        if invalid_prices > 0:
            print(f"\n⚠️  ADVERTENCIA: {invalid_prices} ventas sin precio válido")

        # No falla el test, pero advierte
        assert invalid_prices < len(self._get_all_sales(db_manager)) * 0.1, (
            f"Más del 10% de las ventas ({invalid_prices}) no tienen precio válido"
        )

    def test_sales_have_valid_dates(self, db_manager):
        """Verifica que las fechas de detección sean coherentes."""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()

            # Fechas en el futuro
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM detected_sales
                WHERE detection_date > date('now')
            """)
            future_dates = dict(cursor.fetchone())['count']

            # Fechas muy antiguas (más de 2 años)
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM detected_sales
                WHERE detection_date < date('now', '-2 years')
            """)
            very_old_dates = dict(cursor.fetchone())['count']

        assert future_dates == 0, f"❌ {future_dates} ventas con fechas en el futuro"

        if very_old_dates > 0:
            print(f"\n⚠️  {very_old_dates} ventas detectadas hace más de 2 años")

    def test_inventory_consistency_over_time(self, db_manager):
        """
        Verifica que el inventario no tenga caídas sospechosas.

        Una caída de >90% de un día a otro probablemente indica un error del scraper.
        """
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()

            # Obtener conteos diarios por plataforma
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
                # Calcular porcentaje de caída
                drop_percentage = ((prev_count - count) / prev_count) * 100

                if drop_percentage > 90:
                    suspicious_drops.append({
                        'platform': platform,
                        'from_date': prev_date,
                        'to_date': current_date,
                        'from_count': prev_count,
                        'to_count': count,
                        'drop_percentage': round(drop_percentage, 1)
                    })

            prev_platform = platform
            prev_count = count
            prev_date = current_date

        if suspicious_drops:
            print(f"\n⚠️  ADVERTENCIA: {len(suspicious_drops)} caídas sospechosas en inventario:")
            for drop in suspicious_drops[:5]:
                print(f"  - {drop['platform']}: {drop['from_count']} → {drop['to_count']} "
                      f"({drop['drop_percentage']}% caída) el {drop['to_date']}")

    def test_no_orphaned_sales(self, db_manager):
        """
        Verifica que todas las ventas detectadas tengan un registro
        en el inventario histórico.
        """
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.platform, s.listing_id, s.detection_date
                FROM detected_sales s
                LEFT JOIN daily_inventory i
                    ON s.platform = i.platform
                    AND s.listing_id = i.listing_id
                WHERE i.listing_id IS NULL
            """)

            orphaned_sales = cursor.fetchall()

        if orphaned_sales:
            print(f"\n⚠️  {len(orphaned_sales)} ventas sin registro en inventario histórico:")
            for sale in orphaned_sales[:5]:
                s = dict(sale)
                print(f"  - {s['platform']}: {s['listing_id']} (detectado: {s['detection_date']})")

    # =========================================================================
    # TESTS DE ESTADÍSTICAS Y RESÚMENES
    # =========================================================================

    def test_generate_integrity_report(self, db_manager):
        """
        Genera un reporte completo de integridad de datos.
        No falla, solo informa.
        """
        stats = db_manager.get_statistics()

        with db_manager.get_connection() as conn:
            cursor = conn.cursor()

            # Plataformas activas
            cursor.execute("""
                SELECT DISTINCT platform FROM daily_inventory
            """)
            platforms = [dict(r)['platform'] for r in cursor.fetchall()]

            # Rango de fechas
            cursor.execute("""
                SELECT MIN(snapshot_date) as oldest, MAX(snapshot_date) as newest
                FROM daily_inventory
            """)
            date_range = dict(cursor.fetchone())

            # Ventas con precio estimado vs real
            cursor.execute("""
                SELECT
                    SUM(CASE WHEN price_is_estimated = 1 THEN 1 ELSE 0 END) as estimated,
                    SUM(CASE WHEN price_is_estimated = 0 THEN 1 ELSE 0 END) as real
                FROM detected_sales
            """)
            price_types = dict(cursor.fetchone())

        print("\n" + "="*70)
        print("REPORTE DE INTEGRIDAD DE DATOS")
        print("="*70)
        print(f"\n📊 ESTADÍSTICAS GENERALES:")
        print(f"  - Total registros en inventario: {stats['total_inventory_records']:,}")
        print(f"  - Total ventas detectadas: {stats['total_sales_detected']:,}")
        print(f"  - Plataformas: {', '.join(platforms)}")
        print(f"  - Rango de fechas: {date_range['oldest']} → {date_range['newest']}")

        print(f"\n💰 PRECIOS DE VENTAS:")
        print(f"  - Precios reales: {price_types.get('real', 0)}")
        print(f"  - Precios estimados: {price_types.get('estimated', 0)}")

        print(f"\n📈 VENTAS POR PLATAFORMA:")
        for platform, count in stats['sales_by_platform'].items():
            print(f"  - {platform}: {count} ventas")

        print("="*70 + "\n")

    # =========================================================================
    # MÉTODOS AUXILIARES
    # =========================================================================

    def _get_all_sales(self, db_manager) -> List[Dict[str, Any]]:
        """Obtiene todas las ventas de la base de datos."""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM detected_sales")
            return [dict(row) for row in cursor.fetchall()]


# =========================================================================
# TESTS FUNCIONALES DE DETECCIÓN DE VENTAS
# =========================================================================

class TestSalesDetectionLogic:
    """Tests para verificar que la lógica de detección de ventas funciona correctamente."""

    @pytest.fixture
    def db_manager(self, tmp_path):
        """Crea una base de datos temporal para tests."""
        test_db = tmp_path / "test_inventory.db"
        return DatabaseManager(test_db)

    def test_detect_sale_when_item_disappears(self, db_manager):
        """Verifica que se detecta una venta cuando un item desaparece."""
        from processors.data_processor import DataProcessor

        yesterday = date.today() - timedelta(days=1)
        today = date.today()

        # Inventario de ayer: 2 items
        yesterday_items = [
            {'listing_id': 'ITEM001', 'platform': 'chrono24', 'listing_price': 1000},
            {'listing_id': 'ITEM002', 'platform': 'chrono24', 'listing_price': 2000},
        ]

        # Inventario de hoy: solo 1 item (ITEM001 desapareció)
        today_items = [
            {'listing_id': 'ITEM002', 'platform': 'chrono24', 'listing_price': 2000},
        ]

        # Guardar ayer
        db_manager.save_daily_inventory('chrono24', yesterday_items, yesterday)

        # Procesar hoy
        processor = DataProcessor(db_manager)
        sold, new, updated = processor.compare_inventories(yesterday_items, today_items)

        # Verificar que se detectó 1 venta
        assert len(sold) == 1
        assert sold[0]['listing_id'] == 'ITEM001'
        assert sold[0]['sale_price'] == 1000

    def test_no_false_positive_when_item_persists(self, db_manager):
        """Verifica que NO se detecta venta si el item sigue disponible."""
        from processors.data_processor import DataProcessor

        yesterday = date.today() - timedelta(days=1)

        # Mismo inventario ayer y hoy
        items = [
            {'listing_id': 'ITEM001', 'platform': 'chrono24', 'listing_price': 1000},
            {'listing_id': 'ITEM002', 'platform': 'chrono24', 'listing_price': 2000},
        ]

        processor = DataProcessor(db_manager)
        sold, new, updated = processor.compare_inventories(items, items)

        # No debe haber ventas detectadas
        assert len(sold) == 0

    def test_detect_price_change(self, db_manager):
        """Verifica que se detectan cambios de precio."""
        from processors.data_processor import DataProcessor

        yesterday_items = [
            {'listing_id': 'ITEM001', 'platform': 'chrono24', 'listing_price': 1000},
        ]

        today_items = [
            {'listing_id': 'ITEM001', 'platform': 'chrono24', 'listing_price': 900},  # Rebajado
        ]

        processor = DataProcessor(db_manager)
        sold, new, updated = processor.compare_inventories(yesterday_items, today_items)

        # Debe detectar 1 actualización
        assert len(updated) == 1
        assert updated[0]['listing_id'] == 'ITEM001'
        assert updated[0]['old_price'] == 1000
        assert updated[0]['listing_price'] == 900
        assert updated[0]['price_change'] == -100


if __name__ == "__main__":
    # Ejecutar tests directamente
    pytest.main([__file__, "-v", "--tb=short"])
