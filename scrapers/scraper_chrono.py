"""
Scraper específico para Chrono24.es
Busca relojes de lujo por modelo con filtros geográficos.
"""

import re
import asyncio
import random
import json
from typing import List, Dict, Any, Optional
from urllib.parse import urlencode
from datetime import datetime

from playwright.async_api import Page
from loguru import logger
import requests

from .base_scraper import BaseScraper

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    CHRONO24_BASE_URL,
    CHRONO24_MODELS,
    CHRONO24_EXCLUDE_COUNTRIES,
    CHRONO24_PAGE_SIZE,
    CHRONO24_MAX_PAGES,
    USE_FLARESOLVERR,
    FLARESOLVERR_URL,
    FLARESOLVERR_TIMEOUT,
    CHRONO24_PAGINATION_TOLERANCE,
    PAGINATION_RETRY_COUNT,
    PAGINATION_STOP_ON_CONSECUTIVE_FAILURES,
)


class Chrono24Scraper(BaseScraper):
    """
    Scraper para Chrono24.es - Marketplace de relojes de lujo.

    Características:
    - Búsqueda por modelo genérico
    - Exclusión de artículos de Japón
    - Extracción de modelo específico, referencia, precio, fecha subida
    - Paginación automática
    """

    PLATFORM_NAME = "chrono24"

    def __init__(self):
        super().__init__()
        self.base_url = CHRONO24_BASE_URL
        self.models_to_search = CHRONO24_MODELS

    async def _solve_with_flaresolverr(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Usa FlareSolverr para resolver Cloudflare y obtener el HTML.

        Args:
            url: URL a resolver

        Returns:
            Diccionario con HTML resuelto o None si falla
        """
        if not USE_FLARESOLVERR:
            return None

        try:
            self.logger.info(f"Usando FlareSolverr para resolver: {url}")

            payload = {
                "cmd": "request.get",
                "url": url,
                "maxTimeout": FLARESOLVERR_TIMEOUT * 1000,  # ms
            }

            response = requests.post(
                FLARESOLVERR_URL,
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
                timeout=FLARESOLVERR_TIMEOUT + 10
            )

            if response.status_code == 200:
                result = response.json()
                if result.get("status") == "ok":
                    solution = result.get("solution", {})
                    self.logger.info(f"FlareSolverr resolvió correctamente (status: {solution.get('status')})")
                    return solution
                else:
                    self.logger.error(f"FlareSolverr error: {result.get('message')}")
                    return None
            else:
                self.logger.error(f"FlareSolverr HTTP {response.status_code}")
                return None

        except requests.exceptions.ConnectionError:
            self.logger.error("No se puede conectar a FlareSolverr. ¿Está corriendo Docker?")
            return None
        except Exception as e:
            self.logger.error(f"Error con FlareSolverr: {e}")
            return None

    def _build_search_url(self, model: str, page: int = 1) -> str:
        """
        Construye la URL de búsqueda para Chrono24.

        Args:
            model: Nombre del modelo a buscar
            page: Número de página

        Returns:
            URL de búsqueda completa
        """
        # Parámetros base - usar pageSize de config (default 120)
        params = {
            "query": model,
            "dosearch": "true",
            "searchexplain": "1",
            "sortorder": "5",  # Ordenar por fecha (más recientes primero)
            "pageSize": str(CHRONO24_PAGE_SIZE),  # Items por página desde config
        }

        # Añadir número de página si no es la primera
        if page > 1:
            params["showpage"] = str(page)

        base_search_url = f"{self.base_url}/search/index.htm"
        return f"{base_search_url}?{urlencode(params)}"

    async def _extract_listings_from_page(self, page: Page) -> List[Dict[str, Any]]:
        """
        Extrae los listings de la página actual de resultados.

        Args:
            page: Página de Playwright

        Returns:
            Lista de diccionarios con datos de cada listing
        """
        listings = []

        # Selectores para los artículos en la página de resultados
        # Chrono24 cambia frecuentemente su estructura HTML
        article_selectors = [
            "article.article-item-container",
            "div.article-item-container",
            "[data-testid='article-item']",
            ".rcard",
            # Nuevos selectores (2024-2026)
            "[class*='WatchCard']",
            "[class*='watch-card']",
            ".article-card",
            "article[class*='article']",
            "[class*='SearchResult']",
            ".search-results-article",
            "div[class*='article-item']",
            # Selectores más genéricos
            "a[href*='--id'][class*='article']",
            "[data-article-id]",
            ".js-article-item",
        ]

        articles = None
        for selector in article_selectors:
            articles = await page.query_selector_all(selector)
            if articles:
                self.logger.debug(f"Encontrados {len(articles)} artículos con selector: {selector}")
                break

        if not articles:
            self.logger.warning("No se encontraron artículos en la página")
            # Debug: guardar screenshot y HTML para análisis
            try:
                from config import DATA_DIR
                debug_dir = DATA_DIR / "debug"
                debug_dir.mkdir(exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                # Guardar screenshot
                screenshot_path = debug_dir / f"chrono24_debug_{timestamp}.png"
                await page.screenshot(path=str(screenshot_path), full_page=True)
                self.logger.info(f"Screenshot guardado: {screenshot_path}")

                # Guardar HTML
                html_path = debug_dir / f"chrono24_debug_{timestamp}.html"
                html_content = await page.content()
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                self.logger.info(f"HTML guardado: {html_path}")

                # Log de elementos encontrados en la página
                body = await page.query_selector("body")
                if body:
                    body_html = await body.inner_html()
                    # Buscar patrones comunes
                    if "captcha" in body_html.lower() or "cloudflare" in body_html.lower():
                        self.logger.error("DETECTADO: Posible CAPTCHA o protección Cloudflare")
                    if "no results" in body_html.lower() or "sin resultados" in body_html.lower():
                        self.logger.warning("La página indica que no hay resultados")
            except Exception as debug_error:
                self.logger.debug(f"Error guardando debug: {debug_error}")

            return listings

        # Scroll para cargar imágenes lazy-loaded
        self.logger.info("Haciendo scroll para cargar imágenes...")
        for i in range(5):
            await page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {(i+1)/5})")
            await asyncio.sleep(0.5)
        # Volver arriba
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(0.5)

        for article in articles:
            try:
                listing = await self._parse_article(article, page)
                if listing and listing.get('listing_id'):
                    # Verificar que no es de un país excluido
                    seller_location = listing.get('seller_location', '')
                    if not self._is_excluded_country(seller_location):
                        listings.append(listing)
                    else:
                        self.logger.debug(f"Excluido artículo de {seller_location}")

            except Exception as e:
                self.logger.warning(f"Error parseando artículo: {e}")
                continue

        return listings

    def _clean_image_url(self, image_url: str) -> str:
        """
        Limpia y normaliza la URL de imagen de Chrono24.

        Chrono24 usa URLs con placeholders como 'Square_SIZE_' que deben ser
        reemplazados por tamaños reales como 'Square100' o eliminados.

        Args:
            image_url: URL de imagen original

        Returns:
            URL de imagen limpia y funcional
        """
        if not image_url:
            return ""

        # Reemplazar placeholders de tamaño con valores reales
        # Chrono24 usa formatos como: Square_SIZE_, ExtraLarge_SIZE_, etc.
        # Large ofrece mejor resolución
        size_replacements = [
            ('Square_SIZE_', 'Large'),
            ('ExtraLarge_SIZE_', 'ExtraLarge'),
            ('Large_SIZE_', 'Large'),
            ('Medium_SIZE_', 'Large'),
            ('Small_SIZE_', 'Large'),
            ('_SIZE_', ''),
        ]

        for placeholder, replacement in size_replacements:
            if placeholder in image_url:
                image_url = image_url.replace(placeholder, replacement)

        # Asegurar que la URL usa https
        if image_url.startswith('http://'):
            image_url = image_url.replace('http://', 'https://')

        return image_url

    def _is_valid_product_image(self, img_url: str) -> bool:
        """
        Verifica si una URL corresponde a una imagen de producto válida.

        Args:
            img_url: URL de la imagen

        Returns:
            True si es una imagen de producto válida
        """
        if not img_url:
            return False

        img_lower = img_url.lower()

        # Rechazar si es un icono, logo, placeholder o SVG
        invalid_patterns = [
            'icon', 'logo', 'placeholder', 'certified', 'default',
            'badge', 'flag', 'avatar', 'sprite', 'blank', 'empty',
            '.svg', 'data:image', 'base64'
        ]

        for pattern in invalid_patterns:
            if pattern in img_lower:
                return False

        # Debe contener chrono24 y ser una imagen
        if 'chrono24' not in img_lower:
            return False

        # Debe tener extensión de imagen o ser de uhren (relojes)
        valid_extensions = ['.jpg', '.jpeg', '.png', '.webp']
        has_valid_ext = any(ext in img_lower for ext in valid_extensions)
        is_uhren_image = '/uhren/' in img_lower or '/images/uhren/' in img_lower

        return has_valid_ext or is_uhren_image

    async def _parse_article(self, article, page: Page) -> Optional[Dict[str, Any]]:
        """
        Parsea un artículo individual de los resultados.

        Args:
            article: Elemento del artículo
            page: Página de Playwright

        Returns:
            Diccionario con los datos del artículo
        """
        try:
            # Extraer URL y listing_id desde el primer link con href a un reloj
            link_element = await article.query_selector("a[href*='--id']")
            if not link_element:
                link_element = await article.query_selector("a[href*='/omega/'], a[href*='/rolex/'], a[href*='/patek-philippe/']")

            url = ""
            listing_id = ""
            if link_element:
                url = await link_element.get_attribute("href")
                if url and not url.startswith("http"):
                    url = f"{self.base_url}{url}"

                # Extraer ID del URL (formato: --id12345678.htm)
                id_match = re.search(r'--id(\d+)\.htm', url)
                if id_match:
                    listing_id = id_match.group(1)

            if not listing_id:
                return None

            # Extraer imagen del artículo - ESTRATEGIA MEJORADA
            image_url = ""

            # MÉTODO 1: Buscar en atributos de elementos img directamente
            # Este es el método más confiable
            all_images = await article.query_selector_all("img")
            for img_element in all_images:
                # Probar múltiples atributos en orden de prioridad
                for attr in ['data-original', 'data-lazy', 'data-src', 'srcset', 'src']:
                    img_src = await img_element.get_attribute(attr)
                    if img_src:
                        # Si es srcset, extraer la URL con mejor resolución
                        if attr == 'srcset':
                            # srcset puede tener formato: "url1 1x, url2 2x" o "url1 100w, url2 200w"
                            parts = img_src.split(',')
                            for part in reversed(parts):  # Empezar por la de mayor resolución
                                part_url = part.strip().split(' ')[0].strip()
                                if self._is_valid_product_image(part_url):
                                    image_url = self._clean_image_url(part_url)
                                    break
                        elif self._is_valid_product_image(img_src):
                            image_url = self._clean_image_url(img_src)

                        if image_url:
                            self.logger.debug(f"Imagen encontrada ({attr}): {image_url[:80]}...")
                            break
                if image_url:
                    break

            # MÉTODO 2: Si no encontramos en elementos img, buscar en el HTML con regex
            if not image_url:
                outer_html = await article.evaluate("el => el.outerHTML")

                # Patrones para encontrar URLs de imagen en el HTML
                img_patterns = [
                    # URLs de CDN de Chrono24 con imágenes de relojes
                    r'(https://cdn[0-9]*\.chrono24\.com/images/uhren/[^"\'>\s]+\.(?:jpg|jpeg|png|webp))',
                    r'(https://img\.chrono24\.com/images/uhren/[^"\'>\s]+\.(?:jpg|jpeg|png|webp))',
                    # URLs generales de Chrono24 con imágenes
                    r'(https://[^"\'>\s]*chrono24\.com[^"\'>\s]*/uhren/[^"\'>\s]+\.(?:jpg|jpeg|png|webp))',
                ]

                for pattern in img_patterns:
                    matches = re.findall(pattern, outer_html, re.IGNORECASE)
                    if matches:
                        for match in matches:
                            if self._is_valid_product_image(match):
                                image_url = self._clean_image_url(match)
                                self.logger.debug(f"Imagen encontrada (regex HTML): {image_url[:80]}...")
                                break
                    if image_url:
                        break

            # MÉTODO 3: Construir URL basada en el listing_id (último recurso)
            if not image_url and listing_id:
                # Chrono24 tiene un patrón predecible para las imágenes
                constructed_url = f"https://cdn2.chrono24.com/images/uhren/{listing_id}-1_v1.jpg"
                image_url = constructed_url
                self.logger.debug(f"Imagen construida desde ID: {image_url}")

            # Log de depuración
            if image_url:
                self.logger.info(f"Listing {listing_id}: imagen = {image_url[:70]}...")
            else:
                self.logger.warning(f"Listing {listing_id}: NO se encontró imagen")

            # Extraer todo el texto del artículo para parsearlo
            inner_text = await article.inner_text()
            lines = [l.strip() for l in inner_text.split('\n') if l.strip()]

            # El título suele estar en las primeras líneas con el nombre de la marca
            specific_model = ""
            reference_number = ""
            price_text = ""
            seller_location = ""
            upload_date_text = ""

            for i, line in enumerate(lines):
                # Buscar el modelo (línea que contiene marca conocida)
                known_brands = [
                    'Omega', 'Rolex', 'Patek', 'Audemars', 'Cartier', 'IWC',
                    'Breitling', 'Tudor', 'TAG', 'Hermès', 'Hermes', 'Longines',
                    'Zenith', 'Jaeger', 'Vacheron', 'Panerai', 'Hublot', 'Chopard',
                    'Blancpain', 'Girard', 'Seiko', 'Grand Seiko', 'A. Lange'
                ]
                if any(brand in line for brand in known_brands):
                    if not specific_model:
                        specific_model = line

                # Buscar referencia (patrón numérico como 2518.80, 126610LN, etc.)
                if re.match(r'^[\d]{3,}[\.\-]?[\d\w]*$', line) and not reference_number:
                    reference_number = line

                # Buscar precio (contiene € o EUR)
                if '€' in line and not price_text:
                    price_text = line

                # Buscar ubicación (código de país de 2 letras solo)
                if re.match(r'^[A-Z]{2}$', line):
                    seller_location = line

                # Buscar fecha de publicación (formato: "hace X días", "12.01.2024", etc.)
                if not upload_date_text:
                    if 'hace' in line.lower() or re.search(r'\d{1,2}[./]\d{1,2}[./]\d{2,4}', line):
                        upload_date_text = line

            # Buscar condición (Nuevo, Muy bueno, Bueno, etc.)
            condition = ""
            condition_keywords = {
                'nuevo': 'Nuevo',
                'new': 'Nuevo',
                'sin usar': 'Nuevo',
                'unworn': 'Nuevo',
                'muy bueno': 'Muy Bueno',
                'very good': 'Muy Bueno',
                'bueno': 'Bueno',
                'good': 'Bueno',
                'aceptable': 'Aceptable',
                'fair': 'Aceptable',
            }

            for keyword, normalized in condition_keywords.items():
                if keyword in inner_text.lower():
                    condition = normalized
                    break

            # Buscar año de producción (2020, 2021, etc.)
            year_of_production = ""
            year_match = re.search(r'\b(19[5-9]\d|20[0-2]\d)\b', inner_text)
            if year_match:
                year_of_production = year_match.group(1)

            # Buscar material de caja
            case_material = ""
            case_keywords = {
                'acero': 'Acero',
                'steel': 'Acero',
                'stainless steel': 'Acero',
                'oro amarillo': 'Oro Amarillo',
                'yellow gold': 'Oro Amarillo',
                'oro rosa': 'Oro Rosa',
                'rose gold': 'Oro Rosa',
                'oro blanco': 'Oro Blanco',
                'white gold': 'Oro Blanco',
                'oro': 'Oro',
                'gold': 'Oro',
                'platino': 'Platino',
                'platinum': 'Platino',
                'titanio': 'Titanio',
                'titanium': 'Titanio',
                'cerámica': 'Cerámica',
                'ceramic': 'Cerámica',
                'bronce': 'Bronce',
                'bronze': 'Bronce',
                'aluminio': 'Aluminio',
                'aluminum': 'Aluminio',
            }

            text_lower = inner_text.lower()
            for keyword, normalized in case_keywords.items():
                if keyword in text_lower:
                    case_material = normalized
                    break

            # Buscar material de pulsera
            bracelet_material = ""
            bracelet_keywords = {
                'pulsera de acero': 'Acero',
                'steel bracelet': 'Acero',
                'pulsera de oro': 'Oro',
                'gold bracelet': 'Oro',
                'pulsera de cuero': 'Cuero',
                'leather strap': 'Cuero',
                'correa de cuero': 'Cuero',
                'leather': 'Cuero',
                'cuero': 'Cuero',
                'pulsera de caucho': 'Caucho',
                'rubber strap': 'Caucho',
                'caucho': 'Caucho',
                'rubber': 'Caucho',
                'pulsera de titanio': 'Titanio',
                'titanium bracelet': 'Titanio',
                'textil': 'Textil',
                'textile': 'Textil',
                'nylon': 'Nylon',
            }

            for keyword, normalized in bracelet_keywords.items():
                if keyword in text_lower:
                    bracelet_material = normalized
                    break

            # Si no se encontró material de pulsera, asumir mismo que caja si es metal
            if not bracelet_material and case_material in ['Acero', 'Oro', 'Oro Amarillo', 'Oro Rosa', 'Oro Blanco', 'Titanio']:
                bracelet_material = case_material

            # Buscar color de esfera
            dial_color = ""
            dial_keywords = {
                'negro': 'Negro',
                'black': 'Negro',
                'blanco': 'Blanco',
                'white': 'Blanco',
                'azul': 'Azul',
                'blue': 'Azul',
                'verde': 'Verde',
                'green': 'Verde',
                'gris': 'Gris',
                'grey': 'Gris',
                'gray': 'Gris',
                'plateado': 'Plateado',
                'silver': 'Plateado',
                'champagne': 'Champagne',
                'marrón': 'Marrón',
                'brown': 'Marrón',
                'beige': 'Beige',
            }

            for keyword, normalized in dial_keywords.items():
                if keyword in text_lower:
                    dial_color = normalized
                    break

            listing_price = self._parse_price(price_text)
            upload_date = self._parse_date(upload_date_text) if upload_date_text else None

            return {
                'listing_id': listing_id,
                'specific_model': specific_model,
                'reference_number': reference_number,
                'listing_price': listing_price,
                'currency': 'EUR',
                'seller_location': seller_location,
                'upload_date': upload_date,
                'url': url,
                'image_url': image_url,
                'condition': condition,
                'year_of_production': year_of_production,
                'case_material': case_material,
                'bracelet_material': bracelet_material,
                'dial_color': dial_color,
            }

        except Exception as e:
            self.logger.error(f"Error extrayendo datos del artículo: {e}")
            return None

    def _parse_price(self, price_text: str) -> Optional[float]:
        """
        Parsea el texto del precio a un valor numérico.

        Args:
            price_text: Texto del precio (ej: "€ 12.500" o "12,500 EUR")

        Returns:
            Precio como float o None
        """
        if not price_text:
            return None

        try:
            # Eliminar símbolos de moneda y espacios
            cleaned = re.sub(r'[€$£\s]', '', price_text)
            # Normalizar separadores (europeo: 12.500,00 -> 12500.00)
            # Si tiene punto como separador de miles y coma como decimal
            if '.' in cleaned and ',' in cleaned:
                cleaned = cleaned.replace('.', '').replace(',', '.')
            elif ',' in cleaned:
                # Solo coma, podría ser decimal o miles
                parts = cleaned.split(',')
                if len(parts) == 2 and len(parts[1]) == 2:
                    cleaned = cleaned.replace(',', '.')
                else:
                    cleaned = cleaned.replace(',', '')
            else:
                # Solo puntos, eliminar si son separadores de miles
                cleaned = cleaned.replace('.', '')

            # Extraer solo números y punto decimal
            cleaned = re.sub(r'[^\d.]', '', cleaned)

            return float(cleaned) if cleaned else None

        except (ValueError, AttributeError):
            return None

    def _parse_date(self, date_text: str) -> Optional[str]:
        """
        Parsea texto de fecha a formato ISO.

        Args:
            date_text: Texto de fecha

        Returns:
            Fecha en formato YYYY-MM-DD o None
        """
        if not date_text:
            return None

        try:
            from datetime import datetime, timedelta
            date_text = date_text.strip().lower()
            today = datetime.now()

            # 1. Fechas relativas: "hace X días/horas/semanas"
            if 'hace' in date_text or 'ago' in date_text:
                # "hace X días" o "X días"
                if 'día' in date_text or 'day' in date_text:
                    match = re.search(r'(\d+)', date_text)
                    if match:
                        days = int(match.group(1))
                        result = (today - timedelta(days=days)).strftime('%Y-%m-%d')
                        self.logger.debug(f"Fecha parseada (días): '{date_text}' → {result}")
                        return result

                # "hace X horas" → hoy
                elif 'hora' in date_text or 'hour' in date_text:
                    result = today.strftime('%Y-%m-%d')
                    self.logger.debug(f"Fecha parseada (horas): '{date_text}' → {result}")
                    return result

                # "hace X semanas"
                elif 'semana' in date_text or 'week' in date_text:
                    match = re.search(r'(\d+)', date_text)
                    if match:
                        weeks = int(match.group(1))
                        result = (today - timedelta(weeks=weeks)).strftime('%Y-%m-%d')
                        self.logger.debug(f"Fecha parseada (semanas): '{date_text}' → {result}")
                        return result

                # "hace X meses"
                elif 'mes' in date_text or 'month' in date_text:
                    match = re.search(r'(\d+)', date_text)
                    if match:
                        months = int(match.group(1))
                        result = (today - timedelta(days=months*30)).strftime('%Y-%m-%d')
                        self.logger.debug(f"Fecha parseada (meses): '{date_text}' → {result}")
                        return result

            # 2. Formato DD.MM.YYYY o DD/MM/YYYY
            date_match = re.search(r'(\d{1,2})[./](\d{1,2})[./](\d{4})', date_text)
            if date_match:
                day, month, year = date_match.groups()
                day_int, month_int = int(day), int(month)
                # Validar que sea una fecha válida (no una referencia de producto)
                if 1 <= day_int <= 31 and 1 <= month_int <= 12:
                    result = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    self.logger.debug(f"Fecha parseada (DD.MM.YYYY): '{date_text}' → {result}")
                    return result

            # 3. Formato DD.MM.YY (año corto)
            date_match = re.search(r'(\d{1,2})[./](\d{1,2})[./](\d{2})(?!\d)', date_text)
            if date_match:
                day, month, year = date_match.groups()
                day_int, month_int = int(day), int(month)
                # Validar que sea una fecha válida (no una referencia de producto)
                if 1 <= day_int <= 31 and 1 <= month_int <= 12:
                    year = f"20{year}"  # Asumir siglo XXI
                    result = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    self.logger.debug(f"Fecha parseada (DD.MM.YY): '{date_text}' → {result}")
                    return result

            # 4. Formato YYYY-MM-DD (ya normalizado)
            date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', date_text)
            if date_match:
                result = date_match.group(0)
                self.logger.debug(f"Fecha parseada (ISO): '{date_text}' → {result}")
                return result

            # 5. Fechas con meses escritos: "25 ene 2024", "jan 25, 2024"
            month_names = {
                'ene': '01', 'jan': '01', 'enero': '01', 'january': '01',
                'feb': '02', 'febrero': '02', 'february': '02',
                'mar': '03', 'marzo': '03', 'march': '03',
                'abr': '04', 'apr': '04', 'abril': '04', 'april': '04',
                'may': '05', 'mayo': '05',
                'jun': '06', 'junio': '06', 'june': '06',
                'jul': '07', 'julio': '07', 'july': '07',
                'ago': '08', 'aug': '08', 'agosto': '08', 'august': '08',
                'sep': '09', 'sept': '09', 'septiembre': '09', 'september': '09',
                'oct': '10', 'octubre': '10', 'october': '10',
                'nov': '11', 'noviembre': '11', 'november': '11',
                'dic': '12', 'dec': '12', 'diciembre': '12', 'december': '12',
            }

            for month_name, month_num in month_names.items():
                if month_name in date_text:
                    # Buscar día y año cerca del mes
                    parts = date_text.split()
                    day = None
                    year = None
                    for part in parts:
                        if part.isdigit():
                            num = int(part)
                            if 1 <= num <= 31:
                                day = f"{num:02d}"
                            elif 2020 <= num <= 2030:
                                year = str(num)

                    if day and year:
                        result = f"{year}-{month_num}-{day}"
                        self.logger.debug(f"Fecha parseada (mes texto): '{date_text}' → {result}")
                        return result

            # Si llegamos aquí, no pudimos parsear
            self.logger.warning(f"No se pudo parsear fecha: '{date_text}'")
            return None

        except Exception as e:
            self.logger.warning(f"Error parseando fecha '{date_text}': {e}")
            return None

    def _is_excluded_country(self, location: str) -> bool:
        """
        Verifica si la ubicación corresponde a un país excluido.

        Args:
            location: Texto de ubicación

        Returns:
            True si debe ser excluido
        """
        if not location:
            return False

        location_lower = location.lower()
        for country in CHRONO24_EXCLUDE_COUNTRIES:
            if country.lower() in location_lower:
                return True

        return False

    async def _wait_for_cloudflare(self, page: Page, max_wait: int = 30) -> bool:
        """
        Detecta y espera a que termine la verificación de Cloudflare.

        Args:
            page: Página de Playwright
            max_wait: Tiempo máximo de espera en segundos

        Returns:
            True si la página cargó correctamente, False si detectó bloqueo
        """
        try:
            self.logger.info("Verificando protección Cloudflare...")

            # Esperar unos segundos iniciales para que cargue
            await asyncio.sleep(3)

            # Obtener el contenido HTML
            html_content = await page.content()
            html_lower = html_content.lower()

            # Detectar si es página de Cloudflare challenge
            cloudflare_indicators = [
                'cloudflare',
                'checking your browser',
                'un momento',
                'just a moment',
                'please wait',
                'challenge-platform',
                'cf-chl-opt'
            ]

            is_cloudflare = any(indicator in html_lower for indicator in cloudflare_indicators)

            if is_cloudflare:
                self.logger.warning("Detectada verificación Cloudflare, esperando...")

                # Esperar en intervalos, verificando si la página cargó
                for i in range(max_wait):
                    await asyncio.sleep(1)

                    # Verificar si ya no estamos en la página de Cloudflare
                    current_html = await page.content()
                    current_html_lower = current_html.lower()

                    # Si detectamos elementos típicos de la página de resultados
                    has_results = any(term in current_html_lower for term in [
                        'article-item',
                        'watch-card',
                        'search-results',
                        'wristwatch',
                        'seamaster',
                        'listing'
                    ])

                    # Y ya no hay indicadores de Cloudflare
                    still_cloudflare = any(indicator in current_html_lower for indicator in cloudflare_indicators)

                    if has_results and not still_cloudflare:
                        self.logger.info(f"Cloudflare superado después de {i+1}s")
                        return True

                self.logger.error(f"Timeout esperando Cloudflare después de {max_wait}s")
                return False
            else:
                self.logger.debug("Sin protección Cloudflare detectada")
                return True

        except Exception as e:
            self.logger.error(f"Error verificando Cloudflare: {e}")
            return False

    async def _select_page_size_120(self, page: Page) -> bool:
        """
        Selecciona 120 items por página haciendo click en el selector.

        Args:
            page: Página de Playwright

        Returns:
            True si se seleccionó correctamente
        """
        try:
            # Buscar el selector de cantidad de items por página
            # Chrono24 muestra "30 60 120" como opciones
            size_selectors = [
                "a:has-text('120')",
                "button:has-text('120')",
                "[data-page-size='120']",
                ".page-size-selector a:has-text('120')",
                ".pagination a:has-text('120')",
            ]

            for selector in size_selectors:
                size_btn = await page.query_selector(selector)
                if size_btn:
                    is_visible = await size_btn.is_visible()
                    if is_visible:
                        # Verificar que no está ya seleccionado
                        classes = await size_btn.get_attribute("class") or ""
                        if "active" not in classes and "selected" not in classes:
                            self.logger.info("Seleccionando 120 items por página...")
                            await size_btn.scroll_into_view_if_needed()
                            await asyncio.sleep(random.uniform(0.5, 1.0))
                            await size_btn.click()
                            await asyncio.sleep(random.uniform(2, 4))
                            try:
                                await page.wait_for_load_state("networkidle", timeout=10000)
                            except Exception:
                                await asyncio.sleep(2)
                            return True
                        else:
                            self.logger.debug("120 items ya está seleccionado")
                            return True

            self.logger.debug("No se encontró selector de 120 items por página")
            return False

        except Exception as e:
            self.logger.warning(f"Error seleccionando page size: {e}")
            return False

    async def _get_total_pages(self, page: Page) -> int:
        """
        Obtiene el número total de páginas de resultados.

        Args:
            page: Página de Playwright

        Returns:
            Número total de páginas
        """
        try:
            # Buscar paginación - múltiples selectores
            pagination_selectors = [
                ".pagination",
                "[data-testid='pagination']",
                ".pager",
                "nav[aria-label*='pagination']",
                ".page-navigation",
            ]

            max_page = 1

            for selector in pagination_selectors:
                pagination = await page.query_selector(selector)
                if pagination:
                    # Buscar todos los enlaces de paginación
                    page_links = await pagination.query_selector_all("a, button, span")

                    for link in page_links:
                        text = await link.text_content()
                        if text:
                            text = text.strip()
                            # Solo considerar números (ignorar "<", ">", "...", etc.)
                            if text.isdigit():
                                page_num = int(text)
                                max_page = max(max_page, page_num)

                    if max_page > 1:
                        self.logger.info(f"Paginación detectada: {max_page} páginas")
                        return max_page

            # Método alternativo: buscar en todo el HTML de la paginación
            pagination_html = await page.evaluate("""
                () => {
                    const pag = document.querySelector('.pagination, .pager, [class*="pagination"]');
                    return pag ? pag.innerHTML : '';
                }
            """)

            if pagination_html:
                # Buscar el número más alto en el HTML
                numbers = re.findall(r'>(\d+)<', pagination_html)
                if numbers:
                    max_page = max(int(n) for n in numbers)
                    self.logger.info(f"Paginación (HTML): {max_page} páginas")
                    return max_page

            # Método 3: Buscar texto que indica total de resultados
            total_text = await page.evaluate("""
                () => {
                    const el = document.querySelector('[class*="result"], [class*="total"], [class*="count"]');
                    return el ? el.innerText : '';
                }
            """)

            if total_text:
                # Buscar patrones como "1.234 resultados" o "Showing 1-120 of 5678"
                total_match = re.search(r'(\d[\d.,]*)\s*(resultado|result|anuncio|watch)', total_text.lower())
                if total_match:
                    total_items = int(total_match.group(1).replace('.', '').replace(',', ''))
                    max_page = (total_items // 120) + (1 if total_items % 120 else 0)
                    self.logger.info(f"Total items: {total_items}, páginas estimadas: {max_page}")
                    return max_page

            # Si no hay paginación, asumir 1 página
            self.logger.warning("No se pudo detectar paginación, asumiendo 1 página")
            return 1

        except Exception as e:
            self.logger.warning(f"Error obteniendo paginación: {e}")
            return 1

    async def _detect_total_items(self, page: Page) -> tuple:
        """
        Detecta el total de items y páginas ANTES de empezar a scrapear.

        Returns:
            Tuple de (total_items, total_pages)
            - total_items: Número total de items (None si no se puede detectar)
            - total_pages: Número total de páginas
        """
        total_items = None
        total_pages = await self._get_total_pages(page)

        try:
            # Selectores específicos para Chrono24 (evitar selectores genéricos
            # como [class*='count'] que capturan refs de producto como 220.10.38.20.01.002)
            selectors = [
                "[class*='result-count']",
                "[class*='total-count']",
                "[data-testid='result-count']",
                ".pagination-info",
                "[class*='showing']",
            ]

            for selector in selectors:
                element = await page.query_selector(selector)
                if element:
                    text = await element.text_content()
                    if text:
                        # Patrones: "1,234 resultados" o "Showing 1-120 of 5,678"
                        match = re.search(r'(?:of|de)\s+([\d.,\s]+)', text, re.IGNORECASE)
                        if not match:
                            match = re.search(r'([\d.,\s]+)\s*(?:resultado|result|watch|anuncio)', text, re.IGNORECASE)

                        if match:
                            total_str = match.group(1).replace(',', '').replace('.', '').replace(' ', '')
                            try:
                                candidate = int(total_str)
                                # Sanity check: no más de 100,000 items (Chrono24 rara vez tiene más)
                                if 0 < candidate <= 100_000:
                                    total_items = candidate
                                    self.logger.debug(f"Total items detectados: {total_items} (selector: {selector})")
                                    break
                                else:
                                    self.logger.debug(f"Candidato descartado ({candidate}) - fuera de rango razonable")
                            except ValueError:
                                continue

        except Exception as e:
            self.logger.warning(f"Error detectando total de items: {e}")

        # Si no se pudo detectar total_items, estimar desde páginas
        if total_items is None and total_pages > 0:
            from config import CHRONO24_PAGE_SIZE
            total_items = total_pages * CHRONO24_PAGE_SIZE
            self.logger.info(f"Total items estimado desde páginas: {total_pages} × {CHRONO24_PAGE_SIZE} = {total_items}")

        return total_items, total_pages

    async def _click_next_page(self, page: Page) -> bool:
        """
        Intenta navegar a la siguiente página usando click en lugar de URL directa.

        Args:
            page: Página de Playwright

        Returns:
            True si se navegó exitosamente, False si no hay más páginas
        """
        try:
            # Primero cerrar cualquier overlay que pueda estar bloqueando
            await self._close_overlays(page)

            # Selectores para el botón "siguiente"
            next_selectors = [
                "a[aria-label='Siguiente']",
                "a[aria-label='Next']",
                ".pagination a.next",
                ".pagination [rel='next']",
                "a[title='Siguiente página']",
                "a[title='Next page']",
                ".pager-next a",
                "a.js-page-link[data-page]",
            ]

            for selector in next_selectors:
                next_btn = await page.query_selector(selector)
                if next_btn:
                    # Verificar que el botón es visible y clickeable
                    is_visible = await next_btn.is_visible()
                    if is_visible:
                        # Scroll al botón primero
                        await next_btn.scroll_into_view_if_needed()
                        await asyncio.sleep(random.uniform(0.5, 1.0))

                        # Click con comportamiento humano
                        await next_btn.click()
                        await asyncio.sleep(random.uniform(2, 4))

                        # Esperar a que cargue el contenido
                        try:
                            await page.wait_for_load_state("networkidle", timeout=10000)
                        except Exception:
                            await asyncio.sleep(2)

                        # Cerrar overlays después de navegar
                        await self._close_overlays(page)

                        return True

            # Alternativa: buscar enlaces de paginación numerados
            pagination = await page.query_selector(".pagination, .pager")
            if pagination:
                # Obtener página actual
                current = await pagination.query_selector(".active, [aria-current='page']")
                if current:
                    current_text = await current.text_content()
                    if current_text and current_text.strip().isdigit():
                        current_num = int(current_text.strip())
                        # Buscar el enlace a la página siguiente
                        next_page_link = await pagination.query_selector(f"a:has-text('{current_num + 1}')")
                        if next_page_link:
                            await next_page_link.scroll_into_view_if_needed()
                            await asyncio.sleep(random.uniform(0.5, 1.0))
                            await next_page_link.click()
                            await asyncio.sleep(random.uniform(2, 4))

                            # Cerrar overlays después de navegar
                            await self._close_overlays(page)

                            return True

            return False

        except Exception as e:
            self.logger.debug(f"Error navegando a siguiente página: {e}")
            return False

    async def _navigate_to_page(self, page: Page, target_page: int, max_retries: int = 3) -> bool:
        """
        Navega a una página específica usando URL directa con reintentos.

        Args:
            page: Página de Playwright
            target_page: Número de página destino
            max_retries: Número máximo de reintentos (default: 3)

        Returns:
            True si se navegó exitosamente y la página contiene artículos
        """
        for attempt in range(1, max_retries + 1):
            try:
                current_url = page.url

                # Modificar la URL para ir a la página específica
                if 'showpage=' in current_url:
                    new_url = re.sub(r'showpage=\d+', f'showpage={target_page}', current_url)
                else:
                    separator = '&' if '?' in current_url else '?'
                    new_url = f"{current_url}{separator}showpage={target_page}"

                self.logger.debug(f"Navegando a página {target_page} (intento {attempt}/{max_retries}): {new_url[:100]}...")

                response = await page.goto(new_url, wait_until="domcontentloaded", timeout=30000)

                if response and response.ok:
                    await asyncio.sleep(random.uniform(2, 4))
                    try:
                        await page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        await asyncio.sleep(2)

                    # IMPORTANTE: Cerrar cualquier overlay que pueda estar bloqueando
                    await self._close_overlays(page)

                    # VALIDAR: Verificar que hay artículos visibles
                    articles = await page.query_selector_all("article.article-item-container")
                    if articles:
                        self.logger.debug(f"Página {target_page} cargada correctamente ({len(articles)} artículos visibles)")
                        return True
                    else:
                        self.logger.warning(f"Página {target_page} cargó pero sin artículos (intento {attempt}/{max_retries})")
                else:
                    self.logger.warning(f"Respuesta no OK en página {target_page} (intento {attempt}/{max_retries})")

            except Exception as e:
                self.logger.warning(f"Error navegando a página {target_page} (intento {attempt}/{max_retries}): {e}")

            # Esperar antes de reintentar
            if attempt < max_retries:
                await asyncio.sleep(random.uniform(3, 5))

        return False

    async def _navigate_with_flaresolverr(self, page: Page, url: str) -> bool:
        """
        Navega a una URL usando FlareSolverr para resolver Cloudflare.
        Usa page.goto() (no set_content) para que JavaScript se ejecute
        y los artículos se carguen dinámicamente.

        Args:
            page: Página de Playwright
            url: URL completa a la que navegar

        Returns:
            True si se navegó exitosamente con artículos visibles, False si falló
        """
        if not USE_FLARESOLVERR:
            self.logger.warning("FlareSolverr no está habilitado")
            return False

        try:
            self.logger.info(f"Usando FlareSolverr para navegar a: {url[:80]}...")

            # Llamar FlareSolverr para obtener cookies frescas Y el HTML resuelto
            solution = await self._solve_with_flaresolverr(url)

            if not solution or not solution.get("response"):
                self.logger.warning("FlareSolverr no pudo resolver la URL")
                return False

            cookies = solution.get("cookies", [])
            html = solution.get("response", "")

            # Inyectar cookies de FlareSolverr
            if cookies:
                await page.context.add_cookies(cookies)
                self.logger.debug(f"Cookies FlareSolverr inyectadas: {len(cookies)}")

            # Diagnóstico: ¿El HTML de FlareSolverr contiene artículos?
            html_article_count = html.count('article-item-container') if html else 0
            self.logger.info(f"HTML FlareSolverr: {len(html)} chars, {html_article_count} 'article-item-container' encontrados")

            # ESTRATEGIA 1: goto() con cookies frescas (ejecuta JS, mejor opción)
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                if response and response.ok:
                    await asyncio.sleep(random.uniform(2, 4))
                    try:
                        await page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        await asyncio.sleep(2)
                    await self._close_overlays(page)
                    articles = await page.query_selector_all("article.article-item-container")
                    if articles:
                        self.logger.info(f"FlareSolverr + goto() exitoso ({len(articles)} artículos)")
                        return True
                    else:
                        self.logger.warning("FlareSolverr + goto() sin artículos, probando set_content()...")
                else:
                    status = response.status if response else 'no response'
                    self.logger.warning(f"FlareSolverr + goto() falló ({status}), probando set_content()...")
            except Exception as e:
                self.logger.warning(f"FlareSolverr + goto() error: {e}, probando set_content()...")

            # ESTRATEGIA 2: set_content() con HTML de FlareSolverr (no ejecuta JS pero inyecta HTML completo)
            if html and html_article_count > 0:
                self.logger.info(f"Inyectando HTML de FlareSolverr con {html_article_count} artículos...")
                await page.set_content(html, wait_until="domcontentloaded")
                await asyncio.sleep(1)
                await self._close_overlays(page)

                articles = await page.query_selector_all("article.article-item-container")
                if articles:
                    self.logger.info(f"FlareSolverr + set_content() exitoso ({len(articles)} artículos)")
                    return True
                else:
                    self.logger.warning(f"set_content() inyectó HTML pero selector no encontró artículos")
                    # Último intento: buscar con selectores alternativos
                    for alt_selector in ["article[class*='article']", ".article-item-container", "[class*='article-item']"]:
                        alt_articles = await page.query_selector_all(alt_selector)
                        if alt_articles:
                            self.logger.info(f"set_content() encontró {len(alt_articles)} artículos con selector: {alt_selector}")
                            return True
                    self.logger.warning("set_content() no encontró artículos con ningún selector")
            else:
                self.logger.warning(f"HTML de FlareSolverr no contiene artículos ({html_article_count})")

            return False

        except Exception as e:
            self.logger.error(f"Error en navegación con FlareSolverr: {e}")
            return False

    async def _close_overlays(self, page: Page) -> bool:
        """
        Cierra modales, banners y overlays que puedan estar bloqueando la navegación.

        Args:
            page: Página de Playwright

        Returns:
            True si se cerró algún overlay, False si no había ninguno
        """
        closed_any = False

        try:
            self.logger.debug("Buscando overlays/modales...")

            # Selectores para botones de cerrar/continuar/aceptar
            overlay_selectors = [
                # Botones de cerrar genéricos
                "button:has-text('Cerrar')",
                "button:has-text('Close')",
                "button:has-text('X')",
                "[aria-label='Cerrar']",
                "[aria-label='Close']",
                ".close-button",
                ".modal-close",

                # Botones de continuar
                "button:has-text('Continuar')",
                "button:has-text('Continue')",
                "a:has-text('Continuar')",

                # Cookies y privacidad
                "button:has-text('Aceptar')",
                "button:has-text('Accept')",
                "button:has-text('Aceptar todas')",
                "button:has-text('Accept all')",
                "#onetrust-accept-btn-handler",
                ".cookie-banner button",
                "[data-testid='cookie-accept']",
                ".js-cookie-accept",

                # Otros overlays comunes
                "[class*='overlay'] button",
                "[class*='modal'] button",
                "[role='dialog'] button",
            ]

            for selector in overlay_selectors:
                try:
                    # Buscar el elemento con timeout corto
                    button = await page.query_selector(selector)
                    if button:
                        # Verificar que es visible
                        is_visible = await button.is_visible()
                        if is_visible:
                            self.logger.info(f"Cerrando overlay con selector: {selector}")
                            await button.click()
                            await asyncio.sleep(1)
                            closed_any = True
                            # Continuar buscando más overlays
                except Exception as e:
                    # Ignorar errores individuales y continuar
                    self.logger.debug(f"Error con selector {selector}: {e}")
                    continue

            if not closed_any:
                self.logger.debug("No se encontraron overlays visibles")

            return closed_any

        except Exception as e:
            self.logger.warning(f"Error cerrando overlays: {e}")
            return False

    async def _accept_cookies(self, page: Page) -> bool:
        """
        DEPRECATED: Use _close_overlays() instead.
        Detecta y acepta el banner de cookies de Chrono24.

        Args:
            page: Página de Playwright

        Returns:
            True si se manejaron cookies, False si no había banner
        """
        return await self._close_overlays(page)

    async def search_model(
        self,
        model: str,
        max_pages: int = 0  # 0 = sin límite, scrapear todas
    ) -> List[Dict[str, Any]]:
        """
        Busca un modelo específico y extrae todos los listings con validación completa.

        Args:
            model: Nombre del modelo a buscar
            max_pages: Número máximo de páginas a scrapear (0 = todas)

        Returns:
            Lista de listings encontrados
        """
        all_listings = []
        seen_ids = set()  # Para evitar duplicados entre páginas

        async with self.get_page() as page:
            # PASO 1: Construir URL de búsqueda
            search_url = self._build_search_url(model, page=1)
            self.logger.info(f"Buscando: {model}")
            self.logger.debug(f"URL: {search_url}")

            # PASO 2: Intentar con FlareSolverr si está habilitado
            if USE_FLARESOLVERR:
                solution = await self._solve_with_flaresolverr(search_url)
                if solution and solution.get("response"):
                    # FlareSolverr resolvió exitosamente
                    # Inyectar HTML y cookies en Playwright
                    html = solution.get("response", "")
                    cookies = solution.get("cookies", [])

                    # Navegar a about:blank primero
                    await page.goto("about:blank")

                    # Añadir cookies
                    if cookies:
                        await page.context.add_cookies(cookies)
                        self.logger.info(f"Cookies inyectadas: {len(cookies)}")

                    # Navegar a la URL real ahora con cookies
                    if await self.safe_goto(page, search_url):
                        self.logger.info("Navegación exitosa con FlareSolverr")
                    else:
                        self.logger.error("Falló navegación después de FlareSolverr")
                        return all_listings
                else:
                    self.logger.warning("FlareSolverr no pudo resolver, intentando método tradicional...")
                    # Fallback al método tradicional
                    if not await self.safe_goto(page, search_url):
                        self.logger.error(f"No se pudo cargar la búsqueda para {model}")
                        return all_listings

                    if not await self._wait_for_cloudflare(page, max_wait=60):
                        self.logger.error(f"No se pudo superar la protección Cloudflare para {model}")
                        return all_listings
            else:
                # Método tradicional sin FlareSolverr
                if not await self.safe_goto(page, search_url):
                    self.logger.error(f"No se pudo cargar la búsqueda para {model}")
                    return all_listings

                if not await self._wait_for_cloudflare(page, max_wait=60):
                    self.logger.error(f"No se pudo superar la protección Cloudflare para {model}")
                    return all_listings

            # Esperar adicional para que carguen los resultados
            await asyncio.sleep(random.uniform(2, 4))

            # Guardar URL base ANTES de cualquier operación que pueda corromperla
            # Se usa para construir URLs de paginación (páginas 2+)
            base_url = page.url
            self.logger.debug(f"URL base guardada: {base_url}")

            # Intentar seleccionar 120 items por página (por si la URL no funcionó)
            await self._select_page_size_120(page)

            # Simular comportamiento humano inicial
            await self.simulate_human_behavior(page)

            # === PRE-SCRAPING VALIDATION ===
            total_items, total_pages = await self._detect_total_items(page)

            # Determinar cuántas páginas scrapear
            if max_pages > 0:
                pages_to_scrape = min(total_pages, max_pages)
            else:
                pages_to_scrape = total_pages  # Todas las páginas

            expected_items = total_items if total_items else (total_pages * CHRONO24_PAGE_SIZE)

            self.logger.info(
                f"PRE-SCRAPING '{model}': {total_pages} páginas detectadas "
                f"(~{expected_items} items esperados, scrapeando {pages_to_scrape} páginas)"
            )

            # Scrapear primera página
            listings = await self._extract_listings_from_page(page)
            page_1_listings = []
            for listing in listings:
                if listing.get('listing_id') and listing['listing_id'] not in seen_ids:
                    listing['generic_model'] = model
                    listing['platform'] = self.PLATFORM_NAME
                    all_listings.append(listing)
                    page_1_listings.append(listing)
                    seen_ids.add(listing['listing_id'])

            self.logger.info(
                f"Página 1/{pages_to_scrape}: {len(listings)} extraídos, {len(page_1_listings)} nuevos | "
                f"Total acumulado: {len(all_listings)}"
            )

            # Descargar imágenes de la página 1
            if page_1_listings:
                self.logger.info(f"Descargando {len(page_1_listings)} imágenes de página 1...")
                await self.download_images_for_listings(page_1_listings)
                self.logger.info(f"✓ Descarga de imágenes completada para página 1")

            # === SCRAPING CON ERROR HANDLING MEJORADO ===
            consecutive_failures = 0  # Contador de fallos consecutivos

            for page_num in range(2, pages_to_scrape + 1):
                # Delay aleatorio entre páginas
                delay = random.uniform(5, 8)
                self.logger.debug(f"Esperando {delay:.1f}s antes de página {page_num}")
                await asyncio.sleep(delay)

                navigated = False

                # Construir URL para página N usando base_url (NO page.url que puede corromperse)
                # CORRECCIÓN CRÍTICA: Chrono24 usa formato --modXX-N.htm, NO showpage=N
                if re.search(r'--mod\d+(?:-\d+)?\.htm', base_url):
                    target_url = re.sub(r'(--mod\d+)(?:-\d+)?(\.htm)', rf'\1-{page_num}\2', base_url)
                elif 'showpage=' in base_url:
                    target_url = re.sub(r'showpage=\d+', f'showpage={page_num}', base_url)
                else:
                    separator = '&' if '?' in base_url else '?'
                    target_url = f"{base_url}{separator}showpage={page_num}"

                self.logger.debug(f"URL paginación página {page_num}: {target_url[:100]}...")

                # === NIVEL 1: goto() directo con cookies existentes (rápido, 0 overhead) ===
                if not navigated:
                    try:
                        self.logger.info(f"Página {page_num}: Intentando goto() directo...")
                        response = await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                        if response and response.ok:
                            await asyncio.sleep(random.uniform(2, 4))
                            await self._close_overlays(page)
                            articles = await page.query_selector_all("article.article-item-container")
                            if articles:
                                navigated = True
                                self.logger.info(f"Página {page_num}: goto() directo exitoso ({len(articles)} artículos)")
                            else:
                                self.logger.warning(f"Página {page_num}: goto() OK pero sin artículos")
                        else:
                            status = response.status if response else 'no response'
                            self.logger.warning(f"Página {page_num}: goto() falló ({status})")
                    except Exception as e:
                        self.logger.warning(f"Página {page_num}: goto() error: {e}")

                # === NIVEL 2: Click en botón "Siguiente" (comportamiento humano) ===
                if not navigated and page.url != "about:blank":
                    self.logger.info(f"Página {page_num}: Intentando click 'Siguiente'...")
                    navigated = await self._click_next_page(page)
                    if navigated:
                        self.logger.info(f"Página {page_num}: click 'Siguiente' exitoso")

                # === NIVEL 3: FlareSolverr + goto() (lento pero robusto) ===
                if not navigated and USE_FLARESOLVERR:
                    self.logger.info(f"Página {page_num}: Escalando a FlareSolverr...")
                    navigated = await self._navigate_with_flaresolverr(page, target_url)
                    if navigated:
                        self.logger.info(f"Página {page_num}: FlareSolverr exitoso")

                # Si ningún método funcionó
                if not navigated:
                    self.logger.error(f"No se pudo navegar a página {page_num} después de todos los intentos")
                    consecutive_failures += 1

                    # Si 2 páginas consecutivas fallan, detener
                    if consecutive_failures >= 2:
                        self.logger.error(
                            f"2 páginas consecutivas fallaron ({page_num-1}, {page_num}), "
                            f"deteniendo scraping de '{model}'"
                        )
                        break

                    # Si solo esta página falló, intentar siguiente
                    self.logger.warning(f"Saltando página {page_num}, intentando siguiente...")
                    continue
                else:
                    consecutive_failures = 0  # Reset contador si navegó bien

                # Verificar Cloudflare en cada página
                if not await self._wait_for_cloudflare(page, max_wait=15):
                    self.logger.warning(f"Cloudflare detectado en página {page_num}")

                    # Intentar rescate con FlareSolverr antes de rendirse
                    if USE_FLARESOLVERR:
                        self.logger.info(f"Página {page_num}: Cloudflare post-navegación, intentando FlareSolverr...")
                        rescued = await self._navigate_with_flaresolverr(page, target_url)
                        if rescued:
                            self.logger.info(f"Página {page_num}: Rescate con FlareSolverr exitoso")
                        else:
                            self.logger.error(f"Página {page_num}: FlareSolverr no pudo resolver Cloudflare, terminando")
                            break
                    else:
                        self.logger.error(f"Cloudflare bloqueó página {page_num}, terminando (FlareSolverr no disponible)")
                        break

                # Cerrar cualquier overlay antes de scrapear
                await self._close_overlays(page)

                # Simular comportamiento humano
                await self.simulate_human_behavior(page)

                # Hacer scroll para cargar contenido lazy
                await self.scroll_to_load_all(page, max_scrolls=3, scroll_delay=0.5)

                # Extraer listings
                listings = await self._extract_listings_from_page(page)
                new_count = 0
                new_listings_this_page = []
                for listing in listings:
                    lid = listing.get('listing_id')
                    if lid and lid not in seen_ids:
                        listing['generic_model'] = model
                        listing['platform'] = self.PLATFORM_NAME
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
            is_valid = abs(variance) <= CHRONO24_PAGINATION_TOLERANCE

            if is_valid:
                self.logger.info(
                    f"✓ VALIDACIÓN OK '{model}': {actual_items} items scrapeados "
                    f"vs {expected_items} esperados (varianza: {variance:+d}, {variance_pct:+.1f}%)"
                )
            else:
                self.logger.warning(
                    f"⚠ VALIDACIÓN FALLIDA '{model}': {actual_items} items scrapeados "
                    f"vs {expected_items} esperados (varianza: {variance:+d}, {variance_pct:+.1f}%) "
                    f"- EXCEDE tolerancia de ±{CHRONO24_PAGINATION_TOLERANCE}"
                )

        self.logger.info(f"Modelo '{model}' completado: {len(all_listings)} listings únicos")
        return all_listings

    async def scrape(self, models: Optional[List[str]] = None, max_pages: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Ejecuta el scraping completo para todos los modelos configurados.

        Args:
            models: Lista de modelos a buscar (usa config si es None)
            max_pages: Máximo de páginas por modelo (None = usar config, 0 = todas)

        Returns:
            Lista de todos los listings encontrados
        """
        models = models or self.models_to_search
        # Usar valor de config si no se especifica
        if max_pages is None:
            max_pages = CHRONO24_MAX_PAGES

        all_listings = []
        all_ids = set()  # Para evitar duplicados globales entre modelos

        self.logger.info(f"Iniciando scraping de {len(models)} modelos en Chrono24")
        self.logger.info(f"Configuración: pageSize={CHRONO24_PAGE_SIZE}, max_pages={'todas' if max_pages == 0 else max_pages}")

        for i, model in enumerate(models, 1):
            try:
                self.logger.info(f"[{i}/{len(models)}] Buscando modelo: {model}")
                listings = await self.search_model(model, max_pages)

                # Filtrar duplicados globales
                new_listings = []
                for listing in listings:
                    lid = listing.get('listing_id')
                    if lid and lid not in all_ids:
                        all_ids.add(lid)
                        new_listings.append(listing)

                all_listings.extend(new_listings)
                self.logger.info(f"Modelo '{model}': {len(listings)} encontrados, {len(new_listings)} nuevos únicos")

                # Delay entre modelos (más largo para evitar detección)
                if i < len(models):
                    delay = random.uniform(5, 10)
                    self.logger.debug(f"Esperando {delay:.1f}s antes del siguiente modelo")
                    await asyncio.sleep(delay)

            except Exception as e:
                self.logger.error(f"Error scrapeando modelo '{model}': {e}")
                continue

        self.logger.info(f"Scraping Chrono24 completado: {len(all_listings)} listings únicos totales")
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
                # Extraer datos detallados
                title = await self.extract_text(page, "h1.detail-title, h1")
                price_text = await self.extract_text(page, ".price-detail, .detail-price")
                reference = await self.extract_text(page, ".detail-reference, [data-testid='reference']")
                seller_name = await self.extract_text(page, ".seller-name, .dealer-name")
                seller_location = await self.extract_text(page, ".seller-location, .dealer-location")
                description = await self.extract_text(page, ".detail-description, .watch-description")

                # Extraer ID del URL
                id_match = re.search(r'--id(\d+)\.htm', url) or re.search(r'/(\d+)\.htm', url)
                listing_id = id_match.group(1) if id_match else ""

                # Extraer imagen principal
                image_url = ""
                img_selectors = [
                    "img.detail-image",
                    ".gallery-image img",
                    "[data-testid='main-image'] img",
                    ".product-image img",
                    "img[src*='chrono24']"
                ]
                for selector in img_selectors:
                    img_element = await page.query_selector(selector)
                    if img_element:
                        image_url = await img_element.get_attribute("src")
                        if image_url and 'chrono24' in image_url:
                            break

                # Extraer especificaciones del reloj desde la tabla de datos
                year_of_production = ""
                case_material = ""
                dial_color = ""
                condition = ""

                # Buscar en tablas de especificaciones
                spec_rows = await page.query_selector_all("table tr, .spec-row, [class*='specification']")
                for row in spec_rows:
                    row_text = await row.inner_text()
                    row_lower = row_text.lower()

                    if 'año' in row_lower or 'year' in row_lower:
                        year_match = re.search(r'(19|20)\d{2}', row_text)
                        if year_match:
                            year_of_production = year_match.group(0)

                    if 'material' in row_lower and 'caja' in row_lower:
                        parts = row_text.split('\n')
                        if len(parts) > 1:
                            case_material = parts[-1].strip()

                    if 'esfera' in row_lower or 'dial' in row_lower:
                        parts = row_text.split('\n')
                        if len(parts) > 1:
                            dial_color = parts[-1].strip()

                    if 'estado' in row_lower or 'condition' in row_lower:
                        parts = row_text.split('\n')
                        if len(parts) > 1:
                            condition = parts[-1].strip()

                # Extraer fecha de publicación
                upload_date_text = await self.extract_text(page, ".listing-date, .upload-date, [class*='date']")
                upload_date = self._parse_date(upload_date_text) if upload_date_text else None

                return {
                    'listing_id': listing_id,
                    'specific_model': title,
                    'reference_number': reference,
                    'listing_price': self._parse_price(price_text),
                    'currency': 'EUR',
                    'seller_name': seller_name,
                    'seller_location': seller_location,
                    'description': description,
                    'url': url,
                    'image_url': image_url,
                    'upload_date': upload_date,
                    'year_of_production': year_of_production,
                    'case_material': case_material,
                    'dial_color': dial_color,
                    'condition': condition,
                    'platform': self.PLATFORM_NAME,
                }

            except Exception as e:
                self.logger.error(f"Error extrayendo detalles de {url}: {e}")
                return None
