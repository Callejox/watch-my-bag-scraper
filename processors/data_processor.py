"""
Procesador de datos para detectar ventas mediante comparación delta.
Compara el inventario de ayer con el de hoy para identificar artículos vendidos.
"""

from datetime import date, timedelta
from typing import List, Dict, Any, Set, Tuple
from loguru import logger

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db_manager import DatabaseManager


class DataProcessor:
    """
    Procesa los datos de inventario para detectar ventas.

    Lógica de Inventario Delta:
    - Carga el inventario de ayer desde la base de datos
    - Compara con el inventario de hoy
    - Items que estaban ayer pero NO están hoy = VENDIDOS
    """

    def __init__(self, db_manager: DatabaseManager = None):
        self.db = db_manager or DatabaseManager()
        self.logger = logger.bind(module="data_processor")

    def compare_inventories(
        self,
        yesterday_items: List[Dict[str, Any]],
        today_items: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Compara dos inventarios y detecta cambios.

        Args:
            yesterday_items: Inventario de ayer
            today_items: Inventario de hoy

        Returns:
            Tupla con (vendidos, nuevos, actualizados)
        """
        # Crear sets de IDs para comparación rápida
        yesterday_ids = {item['listing_id'] for item in yesterday_items}
        today_ids = {item['listing_id'] for item in today_items}

        # Items que desaparecieron = vendidos
        sold_ids = yesterday_ids - today_ids

        # Items nuevos (aparecieron hoy)
        new_ids = today_ids - yesterday_ids

        # Items que siguen (para detectar cambios de precio)
        common_ids = yesterday_ids & today_ids

        # Crear diccionarios para acceso rápido
        yesterday_by_id = {item['listing_id']: item for item in yesterday_items}
        today_by_id = {item['listing_id']: item for item in today_items}

        # Procesar vendidos
        sold_items = []
        for listing_id in sold_ids:
            item = yesterday_by_id[listing_id].copy()
            item['detection_date'] = date.today().isoformat()
            item['sale_price'] = item.get('listing_price')  # Precio estimado
            item['price_is_estimated'] = True
            sold_items.append(item)

        # Procesar nuevos
        new_items = [today_by_id[listing_id] for listing_id in new_ids]

        # Detectar cambios de precio
        updated_items = []
        for listing_id in common_ids:
            yesterday = yesterday_by_id[listing_id]
            today = today_by_id[listing_id]

            # Comparar precios
            old_price = yesterday.get('listing_price')
            new_price = today.get('listing_price')

            if old_price and new_price and old_price != new_price:
                updated_item = today.copy()
                updated_item['old_price'] = old_price
                updated_item['price_change'] = new_price - old_price
                updated_items.append(updated_item)

        return sold_items, new_items, updated_items

    def _validate_scraping_coverage(
        self,
        platform: str,
        today_count: int,
        yesterday_count: int,
        pages_scraped: int = None,
        pages_total: int = None
    ) -> tuple[bool, str]:
        """
        Valida si la cobertura de scraping es suficiente para detectar ventas.

        Args:
            platform: Nombre de la plataforma
            today_count: Items scrapeados hoy
            yesterday_count: Items scrapeados ayer
            pages_scraped: Páginas scrapeadas (opcional)
            pages_total: Total de páginas disponibles (opcional)

        Returns:
            tuple[bool, str]: (is_valid, reason)
        """
        from config import MAX_COVERAGE_CHANGE_PERCENT

        # Regla 1: Cobertura debe ser consistente (±10%)
        if yesterday_count > 0:
            coverage_change_pct = abs((today_count - yesterday_count) / yesterday_count) * 100
            if coverage_change_pct > MAX_COVERAGE_CHANGE_PERCENT:
                return False, f"Cobertura cambió {coverage_change_pct:.1f}% (ayer: {yesterday_count}, hoy: {today_count})"

        # Regla 2: Si conocemos páginas scrapeadas/total, verificar cobertura
        if pages_scraped is not None and pages_total is not None and pages_total > 0:
            coverage_pct = (pages_scraped / pages_total) * 100
            if coverage_pct < 10:
                return False, f"Cobertura muy baja: {pages_scraped}/{pages_total} páginas ({coverage_pct:.1f}%)"

        # Regla 3: Count de hoy debe ser razonable
        if today_count < 100:
            return False, f"Count muy bajo: {today_count} items"

        return True, "Cobertura aceptable"

    def process_chrono24_sales(
        self,
        today_inventory: List[Dict[str, Any]],
        scraping_metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Procesa las ventas de Chrono24.
        Compara con el inventario de ayer y detecta ventas.

        Args:
            today_inventory: Inventario obtenido hoy
            scraping_metadata: Metadata del scraping (pages_scraped, pages_total, etc.)

        Returns:
            Diccionario con estadísticas y ventas detectadas
        """
        platform = "chrono24"
        today = date.today()
        yesterday = today - timedelta(days=1)

        # Obtener inventario de ayer
        yesterday_inventory = self.db.get_inventory_by_date(platform, yesterday)

        self.logger.info(
            f"Chrono24: Ayer={len(yesterday_inventory)} items, "
            f"Hoy={len(today_inventory)} items"
        )

        # Si no hay inventario de ayer, solo guardamos el de hoy
        if not yesterday_inventory:
            self.logger.info("No hay inventario previo. Guardando inventario inicial.")
            self.db.save_daily_inventory(platform, today_inventory, today)
            return {
                'platform': platform,
                'items_scraped': len(today_inventory),
                'items_sold': 0,
                'items_new': len(today_inventory),
                'sales': [],
                'is_first_run': True,
            }

        # Verificar que today_inventory no esté vacío (posible fallo del scraper)
        if not today_inventory:
            self.logger.error(
                f"{platform.capitalize()}: Scraper retornó 0 items (posible fallo). "
                f"No se compararán inventarios para evitar falsos positivos."
            )
            # No guardar nada, no detectar ventas
            return {
                'platform': platform,
                'items_scraped': 0,
                'items_sold': 0,
                'items_new': 0,
                'items_updated': 0,
                'sales': [],
                'new_items': [],
                'updated_items': [],
                'is_first_run': False,
                'scraper_failed': True,  # Flag para indicar fallo
            }

        # Validar cobertura de scraping antes de comparar
        pages_scraped = scraping_metadata.get('pages_scraped') if scraping_metadata else None
        pages_total = scraping_metadata.get('pages_total') if scraping_metadata else None

        is_valid, reason = self._validate_scraping_coverage(
            platform,
            len(today_inventory),
            len(yesterday_inventory),
            pages_scraped,
            pages_total
        )

        if not is_valid:
            self.logger.warning(f"Chrono24: Saltando detección de ventas - {reason}")
            # Guardar inventario pero NO detectar ventas
            self.db.save_daily_inventory(platform, today_inventory, today)
            return {
                'platform': platform,
                'items_scraped': len(today_inventory),
                'items_sold': 0,  # NO detectar ventas falsas
                'items_new': 0,
                'items_updated': 0,
                'sales': [],
                'new_items': [],
                'updated_items': [],
                'is_first_run': False,
                'scraper_incomplete': True,  # Flag para indicar cobertura insuficiente
                'incomplete_reason': reason,
            }

        # Comparar inventarios
        sold_items, new_items, updated_items = self.compare_inventories(
            yesterday_inventory,
            today_inventory
        )

        self.logger.info(
            f"Chrono24: {len(sold_items)} vendidos, "
            f"{len(new_items)} nuevos, "
            f"{len(updated_items)} actualizados"
        )

        # Guardar inventario de hoy
        self.db.save_daily_inventory(platform, today_inventory, today)

        # Guardar ventas detectadas
        if sold_items:
            # Añadir campos necesarios para ventas de Chrono24
            for sale in sold_items:
                sale['platform'] = platform
                sale['price_is_estimated'] = True

            self.db.save_detected_sales(sold_items)

        return {
            'platform': platform,
            'items_scraped': len(today_inventory),
            'items_sold': len(sold_items),
            'items_new': len(new_items),
            'items_updated': len(updated_items),
            'sales': sold_items,
            'new_items': new_items,
            'updated_items': updated_items,
            'is_first_run': False,
        }

    async def process_vestiaire_sales(
        self,
        today_inventory: List[Dict[str, Any]],
        scraper=None
    ) -> Dict[str, Any]:
        """
        Procesa las ventas de Vestiaire Collective.
        Intenta obtener el precio real de venta para cada artículo vendido.

        Args:
            today_inventory: Inventario obtenido hoy
            scraper: Instancia del scraper de Vestiaire (para obtener precios reales)

        Returns:
            Diccionario con estadísticas y ventas detectadas
        """
        platform = "vestiaire"
        today = date.today()
        yesterday = today - timedelta(days=1)

        # Obtener inventario de ayer
        yesterday_inventory = self.db.get_inventory_by_date(platform, yesterday)

        self.logger.info(
            f"Vestiaire: Ayer={len(yesterday_inventory)} items, "
            f"Hoy={len(today_inventory)} items"
        )

        # Si no hay inventario de ayer, solo guardamos el de hoy
        if not yesterday_inventory:
            self.logger.info("No hay inventario previo. Guardando inventario inicial.")
            self.db.save_daily_inventory(platform, today_inventory, today)
            return {
                'platform': platform,
                'items_scraped': len(today_inventory),
                'items_sold': 0,
                'items_new': len(today_inventory),
                'sales': [],
                'is_first_run': True,
            }

        # Verificar que today_inventory no esté vacío (posible fallo del scraper)
        if not today_inventory:
            self.logger.error(
                f"{platform.capitalize()}: Scraper retornó 0 items (posible fallo). "
                f"No se compararán inventarios para evitar falsos positivos."
            )
            # No guardar nada, no detectar ventas
            return {
                'platform': platform,
                'items_scraped': 0,
                'items_sold': 0,
                'items_new': 0,
                'items_updated': 0,
                'sales': [],
                'new_items': [],
                'updated_items': [],
                'is_first_run': False,
                'scraper_failed': True,  # Flag para indicar fallo
            }

        # Comparar inventarios
        sold_items, new_items, updated_items = self.compare_inventories(
            yesterday_inventory,
            today_inventory
        )

        self.logger.info(
            f"Vestiaire: {len(sold_items)} vendidos, "
            f"{len(new_items)} nuevos, "
            f"{len(updated_items)} actualizados"
        )

        # Intentar obtener precios reales de venta
        if sold_items and scraper:
            self.logger.info("Obteniendo precios reales de venta...")
            for sale in sold_items:
                try:
                    url = sale.get('url')
                    if url:
                        details = await scraper.get_sold_item_details(url)
                        if details and details.get('sale_price'):
                            sale['sale_price'] = details['sale_price']
                            sale['price_is_estimated'] = False
                            self.logger.debug(
                                f"Precio real obtenido para {sale['listing_id']}: "
                                f"{sale['sale_price']}"
                            )
                except Exception as e:
                    self.logger.warning(
                        f"No se pudo obtener precio real para {sale.get('listing_id')}: {e}"
                    )

        # Guardar inventario de hoy
        self.db.save_daily_inventory(platform, today_inventory, today)

        # Guardar ventas detectadas
        if sold_items:
            for sale in sold_items:
                sale['platform'] = platform
                # Si no se pudo obtener precio real, usar el último precio conocido
                if 'price_is_estimated' not in sale:
                    sale['price_is_estimated'] = True

            self.db.save_detected_sales(sold_items)

        return {
            'platform': platform,
            'items_scraped': len(today_inventory),
            'items_sold': len(sold_items),
            'items_new': len(new_items),
            'items_updated': len(updated_items),
            'sales': sold_items,
            'new_items': new_items,
            'updated_items': updated_items,
            'is_first_run': False,
        }

    def process_catawiki_sales(
        self,
        today_inventory: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Procesa las ventas de Catawiki.
        Compara con el inventario de ayer y detecta ventas.

        Args:
            today_inventory: Inventario obtenido hoy

        Returns:
            Diccionario con estadísticas y ventas detectadas
        """
        platform = "catawiki"
        today = date.today()
        yesterday = today - timedelta(days=1)

        # Obtener inventario de ayer
        yesterday_inventory = self.db.get_inventory_by_date(platform, yesterday)

        self.logger.info(
            f"Catawiki: Ayer={len(yesterday_inventory)} items, "
            f"Hoy={len(today_inventory)} items"
        )

        # Si no hay inventario de ayer, solo guardamos el de hoy
        if not yesterday_inventory:
            self.logger.info("No hay inventario previo. Guardando inventario inicial.")
            self.db.save_daily_inventory(platform, today_inventory, today)
            return {
                'platform': platform,
                'items_scraped': len(today_inventory),
                'items_sold': 0,
                'items_new': len(today_inventory),
                'sales': [],
                'is_first_run': True,
            }

        # Verificar que today_inventory no esté vacío (posible fallo del scraper)
        if not today_inventory:
            self.logger.error(
                f"{platform.capitalize()}: Scraper retornó 0 items (posible fallo). "
                f"No se compararán inventarios para evitar falsos positivos."
            )
            # No guardar nada, no detectar ventas
            return {
                'platform': platform,
                'items_scraped': 0,
                'items_sold': 0,
                'items_new': 0,
                'items_updated': 0,
                'sales': [],
                'new_items': [],
                'updated_items': [],
                'is_first_run': False,
                'scraper_failed': True,  # Flag para indicar fallo
            }

        # Comparar inventarios
        sold_items, new_items, updated_items = self.compare_inventories(
            yesterday_inventory,
            today_inventory
        )

        self.logger.info(
            f"Catawiki: {len(sold_items)} vendidos, "
            f"{len(new_items)} nuevos, "
            f"{len(updated_items)} actualizados"
        )

        # Guardar inventario de hoy
        self.db.save_daily_inventory(platform, today_inventory, today)

        # Guardar ventas detectadas
        if sold_items:
            # Añadir campos necesarios para ventas de Catawiki
            for sale in sold_items:
                sale['platform'] = platform
                # En Catawiki el precio final de subasta es conocido
                sale['price_is_estimated'] = False

            self.db.save_detected_sales(sold_items)

        return {
            'platform': platform,
            'items_scraped': len(today_inventory),
            'items_sold': len(sold_items),
            'items_new': len(new_items),
            'items_updated': len(updated_items),
            'sales': sold_items,
            'new_items': new_items,
            'updated_items': updated_items,
            'is_first_run': False,
        }

    def calculate_days_on_sale(
        self,
        upload_date: str,
        sale_date: str = None
    ) -> int:
        """
        Calcula los días que un artículo estuvo en venta.

        Args:
            upload_date: Fecha de subida (YYYY-MM-DD)
            sale_date: Fecha de venta (YYYY-MM-DD), default=hoy

        Returns:
            Número de días en venta
        """
        if not upload_date:
            return 0

        try:
            from datetime import datetime

            upload = datetime.strptime(upload_date, '%Y-%m-%d').date()
            sale = (
                datetime.strptime(sale_date, '%Y-%m-%d').date()
                if sale_date
                else date.today()
            )

            return (sale - upload).days

        except (ValueError, TypeError):
            return 0

    def get_sales_summary(
        self,
        start_date: date = None,
        end_date: date = None
    ) -> Dict[str, Any]:
        """
        Genera un resumen de ventas para un período.

        Args:
            start_date: Fecha inicial (default: inicio del mes)
            end_date: Fecha final (default: hoy)

        Returns:
            Diccionario con resumen de ventas
        """
        # Defaults
        today = date.today()
        start_date = start_date or date(today.year, today.month, 1)
        end_date = end_date or today

        # Obtener ventas
        chrono24_sales = self.db.get_sales_by_date_range(start_date, end_date, "chrono24")
        vestiaire_sales = self.db.get_sales_by_date_range(start_date, end_date, "vestiaire")

        # Calcular totales
        chrono24_volume = sum(s.get('sale_price', 0) or 0 for s in chrono24_sales)
        vestiaire_volume = sum(s.get('sale_price', 0) or 0 for s in vestiaire_sales)

        # Promedio de días en venta
        chrono24_days = [s.get('days_on_sale', 0) for s in chrono24_sales if s.get('days_on_sale')]
        vestiaire_days = [s.get('days_on_sale', 0) for s in vestiaire_sales if s.get('days_on_sale')]

        avg_days_chrono24 = sum(chrono24_days) / len(chrono24_days) if chrono24_days else 0
        avg_days_vestiaire = sum(vestiaire_days) / len(vestiaire_days) if vestiaire_days else 0

        return {
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat(),
            },
            'chrono24': {
                'total_sales': len(chrono24_sales),
                'total_volume': chrono24_volume,
                'avg_days_on_sale': round(avg_days_chrono24, 1),
                'sales': chrono24_sales,
            },
            'vestiaire': {
                'total_sales': len(vestiaire_sales),
                'total_volume': vestiaire_volume,
                'avg_days_on_sale': round(avg_days_vestiaire, 1),
                'sales': vestiaire_sales,
            },
            'combined': {
                'total_sales': len(chrono24_sales) + len(vestiaire_sales),
                'total_volume': chrono24_volume + vestiaire_volume,
            }
        }

    def get_daily_summary(self, target_date: date = None) -> Dict[str, Any]:
        """
        Genera un resumen de ventas para un día específico.

        Args:
            target_date: Fecha objetivo (default: hoy)

        Returns:
            Diccionario con resumen diario
        """
        target_date = target_date or date.today()
        return self.get_sales_summary(target_date, target_date)
