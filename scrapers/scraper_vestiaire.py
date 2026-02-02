"""
Scraper específico para Vestiaire Collective.
Monitorea vendedores específicos y extrae precios reales de venta.
"""

import re
import json
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from urllib.parse import urljoin

from playwright.async_api import Page
from loguru import logger

from .base_scraper import BaseScraper

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    VESTIAIRE_BASE_URL,
    VESTIAIRE_SELLER_IDS,
    VESTIAIRE_MAX_PAGES_DEFAULT,
    VESTIAIRE_PAGINATION_TOLERANCE,
    PAGINATION_RETRY_COUNT,
    PAGINATION_STOP_ON_CONSECUTIVE_FAILURES,
)


class VestiaireScraper(BaseScraper):
    """
    Scraper para Vestiaire Collective - Marketplace de moda de lujo.

    Características:
    - Seguimiento de vendedores específicos por ID
    - Extracción de inventario activo de cada vendedor
    - Obtención del precio real de venta (no estimado)
    - Cálculo de tiempo de permanencia en venta
    """

    PLATFORM_NAME = "vestiaire"

    def __init__(self):
        super().__init__()
        self.base_url = VESTIAIRE_BASE_URL
        self.seller_ids = VESTIAIRE_SELLER_IDS

    def _build_seller_url(self, seller_id: str) -> str:
        """
        Construye la URL del perfil de un vendedor.

        Args:
            seller_id: ID del vendedor

        Returns:
            URL del perfil del vendedor
        """
        return f"{self.base_url}/profile/{seller_id}/?tab=items-for-sale"

    def _build_seller_listings_url(self, seller_id: str, page: int = 1) -> str:
        """
        Construye la URL de los listings de un vendedor.

        Args:
            seller_id: ID del vendedor
            page: Número de página

        Returns:
            URL de listings del vendedor
        """
        base = f"{self.base_url}/profile/{seller_id}/"
        if page > 1:
            return f"{base}?tab=items-for-sale&page={page}"
        return f"{base}?tab=items-for-sale"

    async def _detect_total_pages_vestiaire(self, page: Page, seller_id: str) -> tuple:
        """
        Detecta el número total de páginas e items para un vendedor dinámicamente.

        Args:
            page: Playwright page (debe estar en el perfil del vendedor)
            seller_id: ID del vendedor

        Returns:
            Tuple de (total_items, total_pages)
            - total_items: Número total de items (None si no se puede detectar)
            - total_pages: Número total de páginas
        """
        total_items = None
        total_pages = 1

        try:
            # Method 1: Extract from __NEXT_DATA__ (JSON en la página)
            next_data = await self._extract_next_data(page)
            if next_data:
                page_props = next_data.get('props', {}).get('pageProps', {})
                pagination = (
                    page_props.get('pagination') or
                    page_props.get('userProducts', {}).get('pagination') or
                    {}
                )

                total_items = pagination.get('total') or pagination.get('totalItems')
                total_pages = pagination.get('totalPages') or pagination.get('pageCount') or 1

                # Si tenemos items pero no pages, calcular (60 items por página)
                if total_items and total_pages == 1:
                    total_pages = (total_items + 59) // 60

                if total_items:
                    self.logger.info(
                        f"Vendedor {seller_id}: {total_items} items en {total_pages} páginas "
                        f"(detectado desde __NEXT_DATA__)"
                    )
                    return total_items, total_pages

            # Method 2: Extract from DOM pagination
            pagination_el = await page.query_selector("[class*='pagination']")
            if pagination_el:
                page_links = await pagination_el.query_selector_all("a, button, span")
                page_numbers = []
                for link in page_links:
                    text = await link.text_content()
                    if text and text.strip().isdigit():
                        page_numbers.append(int(text.strip()))

                if page_numbers:
                    total_pages = max(page_numbers)
                    self.logger.info(f"Vendedor {seller_id}: {total_pages} páginas (detectado desde DOM)")
                    return None, total_pages

            self.logger.warning(
                f"No se pudo detectar paginación para vendedor {seller_id}, "
                f"usando límite configurado: {VESTIAIRE_MAX_PAGES_DEFAULT}"
            )
            return None, VESTIAIRE_MAX_PAGES_DEFAULT

        except Exception as e:
            self.logger.warning(f"Error detectando paginación: {e}, usando límite por defecto")
            return None, VESTIAIRE_MAX_PAGES_DEFAULT

    async def _extract_next_data(self, page: Page) -> Optional[Dict]:
        """
        Extrae los datos de __NEXT_DATA__ de la página.
        Vestiaire Collective usa Next.js y guarda datos en este script.

        Args:
            page: Página de Playwright

        Returns:
            Diccionario con los datos o None
        """
        try:
            script_content = await page.evaluate("""
                () => {
                    const script = document.getElementById('__NEXT_DATA__');
                    return script ? script.textContent : null;
                }
            """)

            if script_content:
                return json.loads(script_content)

        except Exception as e:
            self.logger.debug(f"No se pudo extraer __NEXT_DATA__: {e}")

        return None

    async def _extract_listings_from_page(self, page: Page, seller_id: str) -> List[Dict[str, Any]]:
        """
        Extrae los listings de la página actual del vendedor.

        Args:
            page: Página de Playwright
            seller_id: ID del vendedor

        Returns:
            Lista de diccionarios con datos de cada listing
        """
        listings = []

        # Esperar a que carguen los productos
        try:
            await page.wait_for_selector('[class*="productCard"], [class*="product-card"]', timeout=15000)
            await asyncio.sleep(3)  # Esperar contenido dinámico

            # Scroll para cargar imágenes lazy
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            await asyncio.sleep(1)
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)

        except Exception:
            self.logger.warning("Timeout esperando productos en la página")

        # MÉTODO PRINCIPAL: Extraer de __NEXT_DATA__ (Next.js)
        next_data = await self._extract_next_data(page)
        if next_data:
            listings = self._parse_next_data_listings(next_data, seller_id)
            if listings:
                self.logger.info(f"Extraídos {len(listings)} productos de __NEXT_DATA__")
                # Intentar enriquecer con imágenes del DOM si faltan
                listings = await self._enrich_listings_with_images(page, listings)
                return listings

        # Método 2: Extraer de JSON-LD schemas
        json_ld_scripts = await page.query_selector_all('script[type="application/ld+json"]')
        for script in json_ld_scripts:
            try:
                content = await script.text_content()
                if content:
                    data = json.loads(content)
                    if data.get('@type') == 'Product' and data.get('sku'):
                        listing = self._parse_json_ld_product(data, seller_id)
                        if listing and listing.get('listing_id'):
                            listings.append(listing)
            except Exception as e:
                self.logger.debug(f"Error parseando JSON-LD: {e}")
                continue

        if listings:
            self.logger.debug(f"Extraídos {len(listings)} productos de JSON-LD")
            listings = await self._enrich_listings_with_images(page, listings)
            return listings

        # Método 3: Fallback - extracción del DOM
        card_selectors = [
            '[class*="product-card_productCard"]',
            '[class*="productCard"]',
            "[data-testid='product-card']",
            'article[class*="product"]',
            'a[href*="/product/"]',
        ]

        articles = None
        for selector in card_selectors:
            articles = await page.query_selector_all(selector)
            if articles:
                self.logger.debug(f"Encontrados {len(articles)} artículos con selector: {selector}")
                break

        if not articles:
            self.logger.warning("No se encontraron artículos en la página")
            return listings

        for article in articles:
            try:
                listing = await self._parse_article(article, page, seller_id)
                if listing and listing.get('listing_id'):
                    listings.append(listing)
            except Exception as e:
                self.logger.warning(f"Error parseando artículo: {e}")
                continue

        return listings

    async def _enrich_listings_with_images(self, page: Page, listings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enriquece los listings con imágenes extraídas del DOM si faltan.

        Args:
            page: Página de Playwright
            listings: Lista de listings

        Returns:
            Lista de listings con imágenes actualizadas
        """
        # Crear un mapa de listing_id -> imagen del DOM
        image_map = {}

        try:
            # Extraer todas las imágenes de productos del DOM
            all_product_links = await page.query_selector_all('a[href*="/product/"]')

            for link in all_product_links:
                try:
                    href = await link.get_attribute('href')
                    if not href:
                        continue

                    # Extraer ID del producto
                    id_match = re.search(r'/product/[^/]+-(\d+)\.shtml', href) or re.search(r'/product/(\d+)', href)
                    if not id_match:
                        continue
                    listing_id = id_match.group(1)

                    # Buscar imagen dentro del link
                    img = await link.query_selector('img')
                    if img:
                        # Probar varios atributos
                        for attr in ['src', 'data-src', 'srcset']:
                            img_url = await img.get_attribute(attr)
                            if img_url:
                                if attr == 'srcset':
                                    img_url = img_url.split(',')[0].strip().split(' ')[0]
                                if img_url.startswith('//'):
                                    img_url = 'https:' + img_url
                                if 'vestiaire' in img_url.lower() or img_url.startswith('http'):
                                    image_map[listing_id] = img_url
                                    break
                except Exception:
                    continue

            # Buscar también en el HTML completo con regex
            if len(image_map) < len(listings):
                html = await page.content()

                # Patrón para encontrar imágenes de Vestiaire
                img_patterns = [
                    r'https://images\.vestiairecollective\.com/[^"\'>\s]+',
                    r'//images\.vestiairecollective\.com/[^"\'>\s]+',
                ]

                for pattern in img_patterns:
                    matches = re.findall(pattern, html)
                    for match in matches:
                        if match.startswith('//'):
                            match = 'https:' + match
                        # Intentar extraer el ID de producto de la URL de imagen
                        id_match = re.search(r'/(\d{6,})[/_-]', match)
                        if id_match:
                            pid = id_match.group(1)
                            if pid not in image_map:
                                image_map[pid] = match

        except Exception as e:
            self.logger.debug(f"Error enriqueciendo imágenes: {e}")

        # Actualizar listings con imágenes
        for listing in listings:
            if not listing.get('image_url') or not listing['image_url'].startswith('http'):
                lid = listing.get('listing_id', '')
                if lid in image_map:
                    listing['image_url'] = image_map[lid]
                    self.logger.debug(f"Imagen enriquecida para {lid}: {image_map[lid][:50]}...")

        return listings

    def _parse_json_ld_product(self, data: Dict, seller_id: str) -> Optional[Dict[str, Any]]:
        """
        Parsea un producto desde JSON-LD schema.

        Args:
            data: Datos JSON-LD del producto
            seller_id: ID del vendedor

        Returns:
            Diccionario con datos del producto
        """
        try:
            listing_id = str(data.get('sku', ''))
            if not listing_id:
                return None

            # Extraer precio del offers
            offers = data.get('offers', {})
            price = offers.get('price')
            listing_price = float(price) if price else None
            currency = offers.get('priceCurrency', 'EUR')

            # Extraer marca
            brand_data = data.get('brand', {})
            brand = brand_data.get('name', '') if isinstance(brand_data, dict) else str(brand_data)

            # Extraer URL
            url = offers.get('url', '')
            if url and not url.startswith('http'):
                url = f"{self.base_url}{url}"

            # Extraer imagen - probar múltiples campos de JSON-LD
            image_url = ''
            for img_field in ['image', 'images', 'photo', 'thumbnail']:
                image_data = data.get(img_field)
                if image_data:
                    if isinstance(image_data, list) and image_data:
                        first_img = image_data[0]
                        if isinstance(first_img, str):
                            image_url = first_img
                        elif isinstance(first_img, dict):
                            image_url = first_img.get('url', '') or first_img.get('contentUrl', '') or first_img.get('src', '')
                    elif isinstance(image_data, str):
                        image_url = image_data
                    elif isinstance(image_data, dict):
                        image_url = image_data.get('url', '') or image_data.get('contentUrl', '') or image_data.get('src', '')
                    if image_url:
                        break
            # Normalizar URL
            if image_url and image_url.startswith('//'):
                image_url = 'https:' + image_url

            # Extraer descripción
            description = data.get('description', '')

            # Extraer condición
            item_condition = offers.get('itemCondition', '')
            condition = ''
            if 'UsedCondition' in str(item_condition):
                condition = 'used'
            elif 'NewCondition' in str(item_condition):
                condition = 'new'

            product_name = data.get('name', '')
            return {
                'listing_id': listing_id,
                'seller_id': seller_id,
                'product_name': product_name,
                'specific_model': product_name,  # Mapear a specific_model para la BD
                'brand': brand,
                'listing_price': listing_price,
                'currency': currency,
                'condition': condition,
                'url': url,
                'image_url': image_url,
                'description': description,
                'platform': self.PLATFORM_NAME,
            }

        except Exception as e:
            self.logger.debug(f"Error parseando JSON-LD product: {e}")
            return None

    def _parse_next_data_listings(self, next_data: Dict, seller_id: str) -> List[Dict[str, Any]]:
        """
        Parsea los listings desde __NEXT_DATA__.

        Args:
            next_data: Datos de Next.js
            seller_id: ID del vendedor

        Returns:
            Lista de listings
        """
        listings = []

        try:
            # Navegar a la estructura de productos
            page_props = next_data.get('props', {}).get('pageProps', {})

            # Buscar productos en varias ubicaciones posibles
            products = []

            # Ubicaciones comunes para productos en Vestiaire
            product_paths = [
                page_props.get('products', []),
                page_props.get('initialProducts', {}).get('items', []),
                page_props.get('catalog', {}).get('products', []),
                page_props.get('user', {}).get('products', []),
                page_props.get('seller', {}).get('products', []),
                page_props.get('userProducts', {}).get('items', []),
                page_props.get('productList', []),
                page_props.get('items', []),
            ]

            for path in product_paths:
                if path and isinstance(path, list):
                    products = path
                    break

            # Búsqueda recursiva en pageProps si no encontramos productos
            if not products:
                products = self._find_products_recursive(page_props)

            self.logger.debug(f"Encontrados {len(products)} productos en __NEXT_DATA__")

            for product in products:
                try:
                    listing = self._parse_next_data_product(product, seller_id)
                    if listing:
                        listings.append(listing)
                except Exception as e:
                    self.logger.debug(f"Error parseando producto de NEXT_DATA: {e}")
                    continue

        except Exception as e:
            self.logger.warning(f"Error extrayendo productos de NEXT_DATA: {e}")

        return listings

    def _find_products_recursive(self, data: Any, depth: int = 0) -> List[Dict]:
        """
        Busca productos recursivamente en la estructura de datos.

        Args:
            data: Datos a buscar
            depth: Profundidad actual de recursión

        Returns:
            Lista de productos encontrados
        """
        if depth > 5:  # Limitar profundidad
            return []

        products = []

        if isinstance(data, dict):
            # Buscar claves que puedan contener productos
            product_keys = ['products', 'items', 'listings', 'productList', 'catalog']
            for key in product_keys:
                if key in data:
                    value = data[key]
                    if isinstance(value, list) and value:
                        # Verificar que parecen ser productos
                        first = value[0]
                        if isinstance(first, dict) and ('id' in first or 'sku' in first or 'price' in first):
                            return value

            # Recursión en valores
            for value in data.values():
                result = self._find_products_recursive(value, depth + 1)
                if result:
                    return result

        elif isinstance(data, list) and data:
            # Verificar si la lista contiene productos
            first = data[0]
            if isinstance(first, dict) and ('id' in first or 'sku' in first or 'price' in first):
                return data

        return products

    def _parse_next_data_product(self, product: Dict, seller_id: str) -> Optional[Dict[str, Any]]:
        """
        Parsea un producto individual desde __NEXT_DATA__.

        Args:
            product: Datos del producto
            seller_id: ID del vendedor

        Returns:
            Diccionario con datos del producto
        """
        try:
            listing_id = str(product.get('id', ''))
            if not listing_id:
                return None

            # Extraer precio
            price_data = product.get('price', {})
            if isinstance(price_data, dict):
                listing_price = float(price_data.get('amount', 0) or price_data.get('value', 0))
                currency = price_data.get('currency', 'EUR')
            else:
                listing_price = float(price_data) if price_data else None
                currency = 'EUR'

            # Extraer marca
            brand_data = product.get('brand', {})
            brand = brand_data.get('name', '') if isinstance(brand_data, dict) else str(brand_data)

            # Extraer URL
            path = product.get('path', '') or product.get('url', '')
            if path and not path.startswith('http'):
                url = f"{self.base_url}{path}"
            else:
                url = path or f"{self.base_url}/product/{listing_id}/"

            # Fecha de creación/subida
            created_at = product.get('createdAt', '') or product.get('publishedAt', '')
            upload_date = self._parse_date(created_at)

            # Extraer imagen - probar múltiples campos
            image_url = ''
            # Campos donde puede estar la imagen en __NEXT_DATA__
            image_fields = ['pictures', 'images', 'medias', 'picture', 'image', 'thumbnail']
            for field in image_fields:
                images = product.get(field)
                if images:
                    if isinstance(images, list) and images:
                        first_img = images[0]
                        if isinstance(first_img, dict):
                            # Probar múltiples claves para la URL
                            for key in ['url', 'src', 'path', 'original', 'large', 'medium']:
                                if first_img.get(key):
                                    image_url = first_img[key]
                                    break
                        elif isinstance(first_img, str):
                            image_url = first_img
                    elif isinstance(images, dict):
                        for key in ['url', 'src', 'path', 'original', 'large', 'medium']:
                            if images.get(key):
                                image_url = images[key]
                                break
                    elif isinstance(images, str):
                        image_url = images
                    if image_url:
                        break
            # Normalizar URL
            if image_url and image_url.startswith('//'):
                image_url = 'https:' + image_url

            # Extraer descripción
            description = product.get('description', '') or product.get('sellerComment', '')

            # Extraer condición
            condition_data = product.get('condition', {})
            condition = condition_data.get('label', '') if isinstance(condition_data, dict) else str(condition_data)

            product_name = product.get('name', '') or product.get('title', '')
            return {
                'listing_id': listing_id,
                'seller_id': seller_id,
                'product_name': product_name,
                'specific_model': product_name,  # Mapear a specific_model para la BD
                'brand': brand,
                'listing_price': listing_price,
                'currency': currency,
                'condition': condition,
                'upload_date': upload_date,
                'url': url,
                'image_url': image_url,
                'description': description,
                'platform': self.PLATFORM_NAME,
                'raw_data': {
                    'size': product.get('size', {}).get('label', ''),
                    'color': product.get('color', {}).get('name', ''),
                    'category': product.get('category', {}).get('name', ''),
                }
            }

        except Exception as e:
            self.logger.debug(f"Error parseando producto: {e}")
            return None

    async def _parse_article(self, article, page: Page, seller_id: str) -> Optional[Dict[str, Any]]:
        """
        Parsea un artículo individual del DOM.

        Args:
            article: Elemento del artículo
            page: Página de Playwright
            seller_id: ID del vendedor

        Returns:
            Diccionario con datos del artículo
        """
        try:
            # Extraer URL y ID
            link_element = await article.query_selector("a[href*='/product/']")
            if not link_element:
                link_element = await article.query_selector("a")

            url = ""
            listing_id = ""
            if link_element:
                url = await link_element.get_attribute("href")
                if url and not url.startswith("http"):
                    url = f"{self.base_url}{url}"

                # Extraer ID del URL
                id_match = re.search(r'/product/([^/]+)/', url) or re.search(r'-(\d+)\.shtml', url)
                if id_match:
                    listing_id = id_match.group(1)

            if not listing_id:
                return None

            # Extraer nombre del producto
            name_selectors = [
                "[data-testid='product-name']",
                ".product-name",
                ".productCard__name",
                "h3",
                "span.name",
            ]
            product_name = ""
            for selector in name_selectors:
                name_el = await article.query_selector(selector)
                if name_el:
                    product_name = await name_el.text_content()
                    product_name = product_name.strip() if product_name else ""
                    break

            # Extraer marca
            brand_selectors = [
                "[data-testid='product-brand']",
                ".product-brand",
                ".productCard__brand",
                "span.brand",
            ]
            brand = ""
            for selector in brand_selectors:
                brand_el = await article.query_selector(selector)
                if brand_el:
                    brand = await brand_el.text_content()
                    brand = brand.strip() if brand else ""
                    break

            # Extraer precio
            price_selectors = [
                "[data-testid='product-price']",
                ".product-price",
                ".productCard__price",
                "span.price",
            ]
            price_text = ""
            for selector in price_selectors:
                price_el = await article.query_selector(selector)
                if price_el:
                    price_text = await price_el.text_content()
                    break

            listing_price = self._parse_price(price_text)

            # Extraer imagen - probar múltiples selectores y atributos
            image_url = ""
            img_selectors = [
                "img[data-testid='product-image']",
                "img.product-image",
                "img[src*='vestiaire']",
                "img[src*='images.vestiairecollective']",
                "picture img",
                "img"
            ]
            # Atributos donde puede estar la URL de imagen (en orden de prioridad)
            img_attrs = ['data-src', 'data-lazy-src', 'data-original', 'srcset', 'src']

            for img_selector in img_selectors:
                img_element = await article.query_selector(img_selector)
                if img_element:
                    for attr in img_attrs:
                        img_val = await img_element.get_attribute(attr)
                        if img_val:
                            # Si es srcset, tomar la primera URL
                            if attr == 'srcset':
                                img_val = img_val.split(',')[0].strip().split(' ')[0]
                            # Validar que es una URL de imagen válida
                            if img_val and (
                                'vestiaire' in img_val.lower() or
                                img_val.startswith('http') or
                                img_val.startswith('//')
                            ):
                                # Normalizar URLs que empiezan con //
                                if img_val.startswith('//'):
                                    img_val = 'https:' + img_val
                                image_url = img_val
                                break
                    if image_url:
                        break

            # Si aún no tenemos imagen, buscar en el HTML del artículo
            if not image_url:
                try:
                    outer_html = await article.evaluate("el => el.outerHTML")
                    # Buscar URLs de imagen de Vestiaire en el HTML
                    img_patterns = [
                        r'(https://images\.vestiairecollective\.com[^"\'>\s]+\.(?:jpg|jpeg|png|webp))',
                        r'(https://[^"\'>\s]*vestiaire[^"\'>\s]+\.(?:jpg|jpeg|png|webp))',
                    ]
                    for pattern in img_patterns:
                        matches = re.findall(pattern, outer_html, re.IGNORECASE)
                        if matches:
                            image_url = matches[0]
                            break
                except Exception:
                    pass

            return {
                'listing_id': listing_id,
                'seller_id': seller_id,
                'product_name': product_name,
                'specific_model': product_name,  # Mapear a specific_model para la BD
                'brand': brand,
                'listing_price': listing_price,
                'currency': 'EUR',
                'url': url,
                'image_url': image_url,
                'platform': self.PLATFORM_NAME,
            }

        except Exception as e:
            self.logger.error(f"Error extrayendo datos del artículo: {e}")
            return None

    def _parse_price(self, price_text: str) -> Optional[float]:
        """
        Parsea el texto del precio a un valor numérico.

        Args:
            price_text: Texto del precio

        Returns:
            Precio como float o None
        """
        if not price_text:
            return None

        try:
            # Eliminar símbolos de moneda y espacios
            cleaned = re.sub(r'[€$£\s]', '', price_text)
            # Normalizar separadores
            if '.' in cleaned and ',' in cleaned:
                cleaned = cleaned.replace('.', '').replace(',', '.')
            elif ',' in cleaned:
                parts = cleaned.split(',')
                if len(parts) == 2 and len(parts[1]) == 2:
                    cleaned = cleaned.replace(',', '.')
                else:
                    cleaned = cleaned.replace(',', '')
            else:
                cleaned = cleaned.replace('.', '')

            cleaned = re.sub(r'[^\d.]', '', cleaned)
            return float(cleaned) if cleaned else None

        except (ValueError, AttributeError):
            return None

    def _parse_date(self, date_text: str) -> Optional[str]:
        """
        Parsea texto de fecha a formato ISO.

        Args:
            date_text: Texto de fecha (puede ser ISO o timestamp)

        Returns:
            Fecha en formato YYYY-MM-DD o None
        """
        if not date_text:
            return None

        try:
            # Si es un timestamp ISO
            if 'T' in date_text:
                dt = datetime.fromisoformat(date_text.replace('Z', '+00:00'))
                return dt.strftime('%Y-%m-%d')

            # Si es timestamp unix (milisegundos)
            if date_text.isdigit():
                ts = int(date_text) / 1000 if len(date_text) > 10 else int(date_text)
                return datetime.fromtimestamp(ts).strftime('%Y-%m-%d')

            # Formato DD/MM/YYYY o DD.MM.YYYY
            date_match = re.search(r'(\d{1,2})[./](\d{1,2})[./](\d{4})', date_text)
            if date_match:
                day, month, year = date_match.groups()
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

        except Exception:
            pass

        return None

    async def get_seller_inventory(
        self,
        seller_id: str,
        max_pages: int = 0  # 0 = usar config, N = override
    ) -> List[Dict[str, Any]]:
        """
        Obtiene el inventario activo de un vendedor con validación completa.

        Args:
            seller_id: ID del vendedor
            max_pages: Número máximo de páginas a scrapear (0 = usar config.VESTIAIRE_MAX_PAGES_DEFAULT)

        Returns:
            Lista de listings activos del vendedor
        """
        all_listings = []
        seen_ids = set()  # NUEVO: Deduplicación como Chrono24

        async with self.get_page() as page:
            # Navegar a perfil del vendedor
            url = self._build_seller_listings_url(seller_id, page=1)
            self.logger.info(f"Scrapeando vendedor {seller_id}")

            if not await self.safe_goto(page, url):
                self.logger.error(f"Error cargando perfil del vendedor {seller_id}")
                return all_listings

            await asyncio.sleep(2)

            # === PRE-SCRAPING VALIDATION ===
            total_items, total_pages = await self._detect_total_pages_vestiaire(page, seller_id)

            # Determinar cuántas páginas scrapear
            if max_pages > 0:
                pages_to_scrape = min(total_pages, max_pages)
            else:
                pages_to_scrape = total_pages  # Usar las detectadas dinámicamente

            expected_items = total_items if total_items else (total_pages * 60)

            self.logger.info(
                f"PRE-SCRAPING vendedor {seller_id}: {total_pages} páginas detectadas "
                f"(~{expected_items} items esperados, scrapeando {pages_to_scrape} páginas)"
            )

            # === SCRAPING CON ERROR HANDLING MEJORADO ===
            consecutive_failures = 0

            for page_num in range(1, pages_to_scrape + 1):
                if page_num > 1:
                    await self.random_delay()

                    page_url = self._build_seller_listings_url(seller_id, page_num)

                    # REINTENTOS
                    success = False
                    for attempt in range(1, PAGINATION_RETRY_COUNT + 1):
                        if await self.safe_goto(page, page_url):
                            success = True
                            break
                        else:
                            self.logger.warning(
                                f"Error cargando página {page_num} (intento {attempt}/{PAGINATION_RETRY_COUNT})"
                            )
                            if attempt < PAGINATION_RETRY_COUNT:
                                await asyncio.sleep(random.uniform(3, 5))

                    if not success:
                        self.logger.error(
                            f"No se pudo cargar página {page_num} después de "
                            f"{PAGINATION_RETRY_COUNT} reintentos"
                        )
                        consecutive_failures += 1

                        # Si 2 páginas consecutivas fallan, detener
                        if consecutive_failures >= 2:
                            self.logger.error(
                                f"2 páginas consecutivas fallaron ({page_num-1}, {page_num}), "
                                f"deteniendo scraping de vendedor {seller_id}"
                            )
                            break

                        self.logger.warning(f"Saltando página {page_num}, intentando siguiente...")
                        continue
                    else:
                        consecutive_failures = 0

                await asyncio.sleep(2)

                # Extraer listings
                listings = await self._extract_listings_from_page(page, seller_id)

                # Si no hay listings y ya pasamos el total detectado, terminar
                if not listings:
                    if page_num <= total_pages:
                        self.logger.warning(f"Página {page_num} vacía (posible error temporal)")
                        consecutive_failures += 1
                        if consecutive_failures >= 2:
                            break
                    else:
                        self.logger.info(f"Fin de inventario en página {page_num}")
                        break
                    continue

                # PROCESAR CON DEDUPLICACIÓN
                new_count = 0
                new_listings_this_page = []
                for listing in listings:
                    lid = listing.get('listing_id')
                    if lid:
                        if lid not in seen_ids:
                            all_listings.append(listing)
                            new_listings_this_page.append(listing)
                            seen_ids.add(lid)
                            new_count += 1

                self.logger.info(
                    f"Página {page_num}/{pages_to_scrape}: "
                    f"{len(listings)} extraídos, {new_count} nuevos | "
                    f"Total acumulado: {len(all_listings)}"
                )

                # Descargar imágenes de los listings nuevos de esta página
                if new_listings_this_page:
                    self.logger.info(f"Descargando {len(new_listings_this_page)} imágenes de página {page_num}...")
                    await self.download_images_for_listings(new_listings_this_page)
                    self.logger.info(f"✓ Descarga de imágenes completada para página {page_num}")

            # === POST-SCRAPING VALIDATION ===
            actual_items = len(all_listings)
            variance = actual_items - expected_items
            variance_pct = (variance / expected_items * 100) if expected_items > 0 else 0
            is_valid = abs(variance) <= VESTIAIRE_PAGINATION_TOLERANCE

            if is_valid:
                self.logger.info(
                    f"✓ VALIDACIÓN OK vendedor {seller_id}: {actual_items} items "
                    f"vs {expected_items} esperados (varianza: {variance:+d}, {variance_pct:+.1f}%)"
                )
            else:
                self.logger.warning(
                    f"⚠ VALIDACIÓN FALLIDA vendedor {seller_id}: {actual_items} items "
                    f"vs {expected_items} esperados (varianza: {variance:+d}, {variance_pct:+.1f}%) "
                    f"- EXCEDE tolerancia de ±{VESTIAIRE_PAGINATION_TOLERANCE}"
                )

        self.logger.info(f"Vendedor {seller_id} completado: {len(all_listings)} listings únicos")
        return all_listings

    async def get_sold_item_details(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene los detalles de un item vendido, incluyendo el precio real de venta.

        Args:
            url: URL del producto

        Returns:
            Diccionario con detalles del producto vendido
        """
        async with self.get_page() as page:
            if not await self.safe_goto(page, url):
                return None

            try:
                # Intentar extraer de __NEXT_DATA__
                next_data = await self._extract_next_data(page)
                if next_data:
                    product = next_data.get('props', {}).get('pageProps', {}).get('product', {})
                    if product:
                        # El precio de venta real suele estar en 'soldPrice' o similar
                        sale_price = (
                            product.get('soldPrice', {}).get('amount') or
                            product.get('finalPrice', {}).get('amount') or
                            product.get('price', {}).get('amount')
                        )

                        return {
                            'listing_id': str(product.get('id', '')),
                            'sale_price': float(sale_price) if sale_price else None,
                            'currency': product.get('price', {}).get('currency', 'EUR'),
                            'sold': product.get('sold', False),
                            'sold_at': product.get('soldAt', ''),
                        }

                # Fallback: buscar en el DOM
                sold_price_selectors = [
                    "[data-testid='sold-price']",
                    ".sold-price",
                    ".final-price",
                    ".product-price--sold",
                ]

                for selector in sold_price_selectors:
                    price_el = await page.query_selector(selector)
                    if price_el:
                        price_text = await price_el.text_content()
                        sale_price = self._parse_price(price_text)
                        if sale_price:
                            return {
                                'sale_price': sale_price,
                                'currency': 'EUR',
                                'sold': True,
                            }

            except Exception as e:
                self.logger.error(f"Error obteniendo detalles de venta: {e}")

            return None

    async def scrape(self, seller_ids: Optional[List[str]] = None, max_pages: int = 0) -> List[Dict[str, Any]]:
        """
        Ejecuta el scraping completo para todos los vendedores configurados.

        Args:
            seller_ids: Lista de IDs de vendedores (usa config si es None)
            max_pages: Máximo de páginas por vendedor (0 = usar config.VESTIAIRE_MAX_PAGES_DEFAULT)

        Returns:
            Lista de todos los listings encontrados
        """
        seller_ids = seller_ids or self.seller_ids
        all_listings = []

        # Filtrar IDs placeholder
        valid_seller_ids = [
            sid for sid in seller_ids
            if sid and not sid.startswith('seller_id_')
        ]

        if not valid_seller_ids:
            self.logger.warning(
                "No hay IDs de vendedores válidos configurados. "
                "Edita config.py y reemplaza los placeholders."
            )
            return all_listings

        self.logger.info(f"Iniciando scraping de {len(valid_seller_ids)} vendedores")

        for seller_id in valid_seller_ids:
            try:
                listings = await self.get_seller_inventory(seller_id, max_pages)
                all_listings.extend(listings)
                self.logger.info(f"Vendedor '{seller_id}': {len(listings)} listings")

                await self.random_delay()

            except Exception as e:
                self.logger.error(f"Error scrapeando vendedor '{seller_id}': {e}")
                continue

        self.logger.info(f"Scraping completado: {len(all_listings)} listings totales")
        return all_listings

    async def scrape_item_detail(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Extrae detalles completos de un listing individual.

        Args:
            url: URL del listing

        Returns:
            Diccionario con detalles del listing
        """
        async with self.get_page() as page:
            if not await self.safe_goto(page, url):
                return None

            try:
                next_data = await self._extract_next_data(page)
                if next_data:
                    product = next_data.get('props', {}).get('pageProps', {}).get('product', {})
                    if product:
                        return self._parse_next_data_product(product, product.get('seller', {}).get('id', ''))

                # Fallback DOM
                title = await self.extract_text(page, "h1, [data-testid='product-title']")
                brand = await self.extract_text(page, "[data-testid='product-brand'], .brand")
                price_text = await self.extract_text(page, "[data-testid='product-price'], .price")
                description = await self.extract_text(page, "[data-testid='product-description'], .description")

                id_match = re.search(r'/product/([^/]+)/', url)
                listing_id = id_match.group(1) if id_match else ""

                return {
                    'listing_id': listing_id,
                    'product_name': title,
                    'brand': brand,
                    'listing_price': self._parse_price(price_text),
                    'currency': 'EUR',
                    'description': description,
                    'url': url,
                    'platform': self.PLATFORM_NAME,
                }

            except Exception as e:
                self.logger.error(f"Error extrayendo detalles de {url}: {e}")
                return None
