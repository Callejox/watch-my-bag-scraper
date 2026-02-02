"""
Gestor de base de datos SQLite para almacenar inventarios y ventas detectadas.
"""

import sqlite3
import json
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Any
from pathlib import Path
from contextlib import contextmanager

from loguru import logger

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATABASE_PATH, DATA_DIR


class DatabaseManager:
    """
    Gestiona todas las operaciones de base de datos SQLite.

    Tablas:
    - daily_inventory: Snapshots diarios de inventario
    - detected_sales: Ventas detectadas por comparación delta
    - scrape_logs: Registro de ejecuciones del scraper
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DATABASE_PATH
        self._ensure_data_directory()
        self._init_database()

    def _ensure_data_directory(self):
        """Asegura que el directorio de datos existe."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def get_connection(self):
        """Context manager para conexiones a la base de datos."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Error en transacción de base de datos: {e}")
            raise
        finally:
            conn.close()

    def _init_database(self):
        """Inicializa las tablas de la base de datos."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Tabla de inventario diario
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_inventory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    listing_id TEXT NOT NULL,
                    snapshot_date DATE NOT NULL,
                    generic_model TEXT,
                    specific_model TEXT,
                    reference_number TEXT,
                    seller_id TEXT,
                    brand TEXT,
                    upload_date DATE,
                    listing_price REAL,
                    currency TEXT DEFAULT 'EUR',
                    seller_location TEXT,
                    url TEXT,
                    image_url TEXT,
                    image_local_path TEXT,
                    description TEXT,
                    condition TEXT,
                    year_of_production TEXT,
                    case_material TEXT,
                    dial_color TEXT,
                    raw_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(platform, listing_id, snapshot_date)
                )
            """)

            # Índices para búsquedas rápidas
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_inventory_platform_date
                ON daily_inventory(platform, snapshot_date)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_inventory_listing
                ON daily_inventory(listing_id)
            """)

            # Tabla de ventas detectadas
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS detected_sales (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    listing_id TEXT NOT NULL,
                    detection_date DATE NOT NULL,
                    generic_model TEXT,
                    specific_model TEXT,
                    reference_number TEXT,
                    seller_id TEXT,
                    brand TEXT,
                    upload_date DATE,
                    sale_price REAL,
                    currency TEXT DEFAULT 'EUR',
                    price_is_estimated BOOLEAN DEFAULT 0,
                    days_on_sale INTEGER,
                    seller_location TEXT,
                    url TEXT,
                    image_url TEXT,
                    image_local_path TEXT,
                    description TEXT,
                    condition TEXT,
                    year_of_production TEXT,
                    case_material TEXT,
                    dial_color TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Índices para ventas
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sales_platform_date
                ON detected_sales(platform, detection_date)
            """)

            # Tabla de logs de ejecución
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scrape_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_date DATE NOT NULL,
                    platform TEXT NOT NULL,
                    status TEXT,
                    items_scraped INTEGER DEFAULT 0,
                    items_sold_detected INTEGER DEFAULT 0,
                    errors TEXT,
                    duration_seconds REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            logger.info("Base de datos inicializada correctamente")

    # =========================================================================
    # OPERACIONES DE INVENTARIO
    # =========================================================================

    def save_daily_inventory(
        self,
        platform: str,
        items: List[Dict[str, Any]],
        snapshot_date: Optional[date] = None
    ) -> int:
        """
        Guarda el inventario diario para una plataforma.

        Args:
            platform: 'chrono24' o 'vestiaire'
            items: Lista de diccionarios con datos de cada artículo
            snapshot_date: Fecha del snapshot (default: hoy)

        Returns:
            Número de items guardados
        """
        snapshot_date = snapshot_date or date.today()
        saved_count = 0

        with self.get_connection() as conn:
            cursor = conn.cursor()

            for item in items:
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO daily_inventory (
                            platform, listing_id, snapshot_date, generic_model,
                            specific_model, reference_number, seller_id, brand,
                            upload_date, listing_price, currency, seller_location,
                            url, image_url, image_local_path, description,
                            condition, year_of_production, case_material, bracelet_material, dial_color,
                            raw_data
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        platform,
                        item.get('listing_id'),
                        snapshot_date.isoformat(),
                        item.get('generic_model'),
                        item.get('specific_model'),
                        item.get('reference_number'),
                        item.get('seller_id'),
                        item.get('brand'),
                        item.get('upload_date'),
                        item.get('listing_price'),
                        item.get('currency', 'EUR'),
                        item.get('seller_location'),
                        item.get('url'),
                        item.get('image_url'),
                        item.get('image_local_path'),
                        item.get('description'),
                        item.get('condition'),
                        item.get('year_of_production'),
                        item.get('case_material'),
                        item.get('bracelet_material'),
                        item.get('dial_color'),
                        json.dumps(item.get('raw_data', {}))
                    ))
                    saved_count += 1
                except Exception as e:
                    logger.warning(f"Error guardando item {item.get('listing_id')}: {e}")

        logger.info(f"Guardados {saved_count}/{len(items)} items de {platform}")
        return saved_count

    def get_inventory_by_date(
        self,
        platform: str,
        snapshot_date: date
    ) -> List[Dict[str, Any]]:
        """
        Obtiene el inventario de una fecha específica.

        Args:
            platform: 'chrono24' o 'vestiaire'
            snapshot_date: Fecha del snapshot

        Returns:
            Lista de diccionarios con los items del inventario
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM daily_inventory
                WHERE platform = ? AND snapshot_date = ?
            """, (platform, snapshot_date.isoformat()))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_yesterday_inventory(self, platform: str) -> List[Dict[str, Any]]:
        """Obtiene el inventario de ayer para una plataforma."""
        yesterday = date.today() - timedelta(days=1)
        return self.get_inventory_by_date(platform, yesterday)

    def get_inventory_listing_ids(
        self,
        platform: str,
        snapshot_date: date
    ) -> set:
        """
        Obtiene solo los IDs de listings de un inventario.
        Útil para comparaciones rápidas.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT listing_id FROM daily_inventory
                WHERE platform = ? AND snapshot_date = ?
            """, (platform, snapshot_date.isoformat()))

            return {row['listing_id'] for row in cursor.fetchall()}

    # =========================================================================
    # OPERACIONES DE VENTAS
    # =========================================================================

    def save_detected_sales(self, sales: List[Dict[str, Any]]) -> int:
        """
        Guarda las ventas detectadas.

        Args:
            sales: Lista de diccionarios con datos de cada venta

        Returns:
            Número de ventas guardadas
        """
        saved_count = 0

        with self.get_connection() as conn:
            cursor = conn.cursor()

            for sale in sales:
                try:
                    # Calcular días en venta si tenemos fecha de subida
                    days_on_sale = None
                    if sale.get('upload_date') and sale.get('detection_date'):
                        try:
                            upload = datetime.strptime(sale['upload_date'], '%Y-%m-%d').date()
                            detection = datetime.strptime(sale['detection_date'], '%Y-%m-%d').date()
                            days_on_sale = (detection - upload).days
                        except (ValueError, TypeError):
                            pass

                    cursor.execute("""
                        INSERT INTO detected_sales (
                            platform, listing_id, detection_date, generic_model,
                            specific_model, reference_number, seller_id, brand,
                            upload_date, sale_price, currency, price_is_estimated,
                            days_on_sale, seller_location, url, image_url,
                            image_local_path, description, condition,
                            year_of_production, case_material, dial_color, bracelet_material
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        sale.get('platform'),
                        sale.get('listing_id'),
                        sale.get('detection_date'),
                        sale.get('generic_model'),
                        sale.get('specific_model'),
                        sale.get('reference_number'),
                        sale.get('seller_id'),
                        sale.get('brand'),
                        sale.get('upload_date'),
                        sale.get('sale_price'),
                        sale.get('currency', 'EUR'),
                        sale.get('price_is_estimated', False),
                        days_on_sale,
                        sale.get('seller_location'),
                        sale.get('url'),
                        sale.get('image_url'),
                        sale.get('image_local_path'),
                        sale.get('description'),
                        sale.get('condition'),
                        sale.get('year_of_production'),
                        sale.get('case_material'),
                        sale.get('dial_color'),
                        sale.get('bracelet_material')
                    ))
                    saved_count += 1
                except Exception as e:
                    logger.warning(f"Error guardando venta {sale.get('listing_id')}: {e}")

        logger.info(f"Guardadas {saved_count}/{len(sales)} ventas detectadas")
        return saved_count

    def get_sales_by_date_range(
        self,
        start_date: date,
        end_date: date,
        platform: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Obtiene ventas detectadas en un rango de fechas.

        Args:
            start_date: Fecha inicial
            end_date: Fecha final
            platform: Filtrar por plataforma (opcional)

        Returns:
            Lista de ventas
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if platform:
                cursor.execute("""
                    SELECT * FROM detected_sales
                    WHERE detection_date BETWEEN ? AND ?
                    AND platform = ?
                    ORDER BY detection_date DESC
                """, (start_date.isoformat(), end_date.isoformat(), platform))
            else:
                cursor.execute("""
                    SELECT * FROM detected_sales
                    WHERE detection_date BETWEEN ? AND ?
                    ORDER BY detection_date DESC
                """, (start_date.isoformat(), end_date.isoformat()))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_sales_for_month(
        self,
        year: int,
        month: int,
        platform: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Obtiene todas las ventas de un mes específico."""
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)

        return self.get_sales_by_date_range(start_date, end_date, platform)

    # =========================================================================
    # OPERACIONES DE LOGS
    # =========================================================================

    def log_scrape_run(
        self,
        platform: str,
        status: str,
        items_scraped: int = 0,
        items_sold_detected: int = 0,
        errors: Optional[str] = None,
        duration_seconds: Optional[float] = None
    ):
        """
        Registra una ejecución del scraper.

        Args:
            platform: 'chrono24', 'vestiaire' o 'all'
            status: 'success', 'partial', 'failed'
            items_scraped: Número de items obtenidos
            items_sold_detected: Número de ventas detectadas
            errors: Descripción de errores (si los hay)
            duration_seconds: Duración de la ejecución
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO scrape_logs (
                    run_date, platform, status, items_scraped,
                    items_sold_detected, errors, duration_seconds
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                date.today().isoformat(),
                platform,
                status,
                items_scraped,
                items_sold_detected,
                errors,
                duration_seconds
            ))

        logger.info(f"Log registrado: {platform} - {status} - {items_scraped} items")

    def get_recent_logs(self, days: int = 7) -> List[Dict[str, Any]]:
        """Obtiene los logs de los últimos N días."""
        start_date = date.today() - timedelta(days=days)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM scrape_logs
                WHERE run_date >= ?
                ORDER BY created_at DESC
            """, (start_date.isoformat(),))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    # =========================================================================
    # UTILIDADES
    # =========================================================================

    def cleanup_old_inventory(self, days_to_keep: int = 30):
        """
        Elimina inventarios antiguos para ahorrar espacio.

        Args:
            days_to_keep: Número de días de inventario a conservar
        """
        cutoff_date = date.today() - timedelta(days=days_to_keep)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM daily_inventory
                WHERE snapshot_date < ?
            """, (cutoff_date.isoformat(),))

            deleted = cursor.rowcount
            logger.info(f"Eliminados {deleted} registros de inventario antiguos")
            return deleted

    def get_latest_inventory(
        self,
        platform: str
    ) -> List[Dict[str, Any]]:
        """
        Obtiene el inventario más reciente de una plataforma.

        Args:
            platform: 'chrono24' o 'vestiaire'

        Returns:
            Lista de diccionarios con los items del inventario
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Primero obtener la fecha más reciente
            cursor.execute("""
                SELECT MAX(snapshot_date) FROM daily_inventory
                WHERE platform = ?
            """, (platform,))
            latest_date = cursor.fetchone()[0]

            if not latest_date:
                return []

            cursor.execute("""
                SELECT * FROM daily_inventory
                WHERE platform = ? AND snapshot_date = ?
                ORDER BY listing_price DESC
            """, (platform, latest_date))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_inventory_for_month(
        self,
        year: int,
        month: int,
        platform: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Obtiene el inventario más reciente del mes especificado.

        Args:
            year: Año
            month: Mes
            platform: Filtrar por plataforma (opcional)

        Returns:
            Lista de items del inventario
        """
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Obtener la fecha más reciente dentro del mes
            if platform:
                cursor.execute("""
                    SELECT MAX(snapshot_date) FROM daily_inventory
                    WHERE platform = ? AND snapshot_date BETWEEN ? AND ?
                """, (platform, start_date.isoformat(), end_date.isoformat()))
            else:
                cursor.execute("""
                    SELECT MAX(snapshot_date) FROM daily_inventory
                    WHERE snapshot_date BETWEEN ? AND ?
                """, (start_date.isoformat(), end_date.isoformat()))

            latest_date = cursor.fetchone()[0]

            if not latest_date:
                return []

            if platform:
                cursor.execute("""
                    SELECT * FROM daily_inventory
                    WHERE platform = ? AND snapshot_date = ?
                    ORDER BY listing_price DESC
                """, (platform, latest_date))
            else:
                cursor.execute("""
                    SELECT * FROM daily_inventory
                    WHERE snapshot_date = ?
                    ORDER BY platform, listing_price DESC
                """, (latest_date,))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_statistics(self) -> Dict[str, Any]:
        """Obtiene estadísticas generales de la base de datos."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Total de items en inventario
            cursor.execute("SELECT COUNT(*) FROM daily_inventory")
            total_inventory = cursor.fetchone()[0]

            # Total de ventas detectadas
            cursor.execute("SELECT COUNT(*) FROM detected_sales")
            total_sales = cursor.fetchone()[0]

            # Ventas por plataforma
            cursor.execute("""
                SELECT platform, COUNT(*) as count
                FROM detected_sales
                GROUP BY platform
            """)
            sales_by_platform = dict(cursor.fetchall())

            # Última ejecución
            cursor.execute("""
                SELECT * FROM scrape_logs
                ORDER BY created_at DESC LIMIT 1
            """)
            last_run = cursor.fetchone()

            return {
                'total_inventory_records': total_inventory,
                'total_sales_detected': total_sales,
                'sales_by_platform': sales_by_platform,
                'last_run': dict(last_run) if last_run else None
            }
