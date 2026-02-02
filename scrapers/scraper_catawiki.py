"""
Scraper específico para Catawiki.
Busca relojes por modelo en subastas activas y finalizadas.
"""

import re
import json
import asyncio
import random
import requests  # Para llamadas HTTP a FlareSolverr
from typing import List, Dict, Any, Optional
from datetime import datetime
from contextlib import asynccontextmanager

from playwright.async_api import Page
from playwright_stealth import Stealth
from loguru import logger

from .base_scraper import BaseScraper

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CATAWIKI_BASE_URL


class CatawikiScraper(BaseScraper):
    """
    Scraper para Catawiki - Plataforma de subastas.

    Características:
    - Búsqueda por modelo de reloj
    - Extracción de subastas activas
    - Obtención de precios de venta finales
    """

    PLATFORM_NAME = "catawiki"

    def __init__(self):
        super().__init__()
        self.base_url = CATAWIKI_BASE_URL
        self._session_initialized = False
        self._context = None

    @asynccontextmanager
    async def get_page(self) -> Page:
        """
        Override del método base con configuración específica para Catawiki.
        Usa configuraciones más agresivas de anti-detección.
        """
        # Configuración de contexto más realista
        context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="es-ES",
            timezone_id="Europe/Madrid",
            java_script_enabled=True,
            # Añadir permisos que un navegador real tendría
            permissions=["geolocation"],
            # Simular un dispositivo real
            device_scale_factor=1,
            is_mobile=False,
            has_touch=False,
            # Color scheme
            color_scheme="light",
        )

        # Añadir cookies iniciales para parecer un usuario que ya visitó el sitio
        await context.add_cookies([
            {
                "name": "catawiki_consent",
                "value": "true",
                "domain": ".catawiki.com",
                "path": "/",
            }
        ])

        page = await context.new_page()

        # Aplicar stealth
        await Stealth().apply_stealth_async(page)

        # Headers más completos
        await page.set_extra_http_headers({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        })

        # Inyectar scripts para ocultar la automatización
        await page.add_init_script("""
            // Ocultar webdriver
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            // Ocultar plugins vacíos
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });

            // Ocultar languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['es-ES', 'es', 'en-US', 'en']
            });

            // Chrome específico
            window.chrome = {
                runtime: {}
            };

            // Permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        """)

        page.set_default_timeout(60000)

        try:
            yield page
        finally:
            await context.close()

    async def _initialize_session(self, page: Page) -> bool:
        """
        Inicializa la sesión navegando primero a la página principal.
        Esto establece cookies y hace que las solicitudes posteriores parezcan legítimas.

        Args:
            page: Página de Playwright

        Returns:
            True si la sesión se inicializó correctamente
        """
        if self._session_initialized:
            return True

        try:
            self.logger.info("Inicializando sesión en Catawiki...")

            # Ir primero a la página principal
            response = await page.goto(
                f"{self.base_url}/es/",
                wait_until="domcontentloaded",
                timeout=60000
            )

            if not response or response.status >= 400:
                self.logger.warning(f"Error accediendo a página principal: {response.status if response else 'No response'}")
                return False

            # Esperar a que cargue la página
            await asyncio.sleep(3)

            # Manejar posible Cloudflare o captcha
            await self.handle_cloudflare(page)

            # Simular comportamiento humano
            await self.simulate_human_behavior(page)

            # Aceptar cookies si aparece el banner
            try:
                cookie_selectors = [
                    "button[data-testid='accept-cookies']",
                    "[id*='cookie'] button[class*='accept']",
                    "button:has-text('Aceptar')",
                    "button:has-text('Accept')",
                    "[class*='cookie'] button:first-of-type",
                ]
                for selector in cookie_selectors:
                    try:
                        cookie_btn = await page.query_selector(selector)
                        if cookie_btn:
                            await cookie_btn.click()
                            self.logger.info("Cookies aceptadas")
                            await asyncio.sleep(1)
                            break
                    except Exception:
                        continue
            except Exception:
                pass

            # Navegar a la sección de relojes para establecer contexto
            watches_url = f"{self.base_url}/es/c/401-relojes-de-pulsera"
            await page.goto(watches_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            await self.simulate_human_behavior(page)

            self._session_initialized = True
            self.logger.info("Sesión inicializada correctamente")
            return True

        except Exception as e:
            self.logger.error(f"Error inicializando sesión: {e}")
            return False

    async def _solve_with_flaresolverr(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Usa FlareSolverr para resolver Cloudflare y obtener el HTML.

        Args:
            url: URL a resolver

        Returns:
            Diccionario con HTML resuelto o None si falla
        """
        from config import USE_FLARESOLVERR, FLARESOLVERR_URL, FLARESOLVERR_TIMEOUT

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

            # Selectores adaptados a Catawiki
            overlay_selectors = [
                # Genéricos (igual que Chrono24)
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
                "button[data-testid='accept-cookies']",
                "[id*='cookie'] button[class*='accept']",
                ".cookie-banner button",

                # Catawiki-specific
                "[data-testid='modal-close']",
                "[class*='Modal'] button",
                "[class*='overlay'] button",
                "[role='dialog'] button",

                # Login/signup prompts
                "button:has-text('Más tarde')",
                "button:has-text('Later')",
                "button:has-text('No, gracias')",
                "button:has-text('No thanks')",
            ]

            for selector in overlay_selectors:
                try:
                    button = await page.query_selector(selector)
                    if button:
                        is_visible = await button.is_visible()
                        if is_visible:
                            self.logger.info(f"Cerrando overlay con selector: {selector}")
                            await button.click()
                            await asyncio.sleep(1)
                            closed_any = True
                except Exception:
                    continue

            if not closed_any:
                self.logger.debug("No se encontraron overlays visibles")

            return closed_any

        except Exception as e:
            self.logger.warning(f"Error cerrando overlays: {e}")
            return False

    async def _navigate_with_flaresolverr(self, page: Page, url: str) -> bool:
        """
        Navega a una URL usando FlareSolverr para resolver Cloudflare.
        Usa estrategia dual: goto() con cookies + set_content() fallback.

        Args:
            page: Página de Playwright
            url: URL completa a la que navegar

        Returns:
            True si se navegó exitosamente con artículos visibles, False si falló
        """
        from config import USE_FLARESOLVERR

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

            # Diagnóstico: ¿El HTML de FlareSolverr contiene artículos de Catawiki?
            import re
            article_patterns = [
                r'data-testid="lot-card"',  # Catawiki-specific
                r'class="lot-card"',
                r'class="[^"]*LotCard[^"]*"',
            ]

            total_matches = 0
            for pattern in article_patterns:
                matches = re.findall(pattern, html)
                if matches:
                    total_matches = max(total_matches, len(matches))
                    self.logger.debug(f"Patrón '{pattern}': {len(matches)} coincidencias")

            self.logger.info(f"HTML FlareSolverr: {len(html)} chars, {total_matches} artículos estimados")

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

                    # Catawiki-specific selectors
                    articles = await page.query_selector_all(
                        "[data-testid='lot-card'], .lot-card, article[class*='lot']"
                    )

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
            if html and total_matches > 0:
                self.logger.info(f"Inyectando HTML de FlareSolverr con {total_matches} artículos...")
                await page.set_content(html, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)
                await self._close_overlays(page)

                # Catawiki-specific alternative selectors (sin prefijo article)
                alternative_selectors = [
                    "[data-testid='lot-card']",
                    ".lot-card",
                    "[class*='LotCard']",
                    "a[href*='/l/']",
                ]

                articles = None
                for selector in alternative_selectors:
                    articles = await page.query_selector_all(selector)
                    if articles:
                        self.logger.info(f"set_content() encontró {len(articles)} artículos con selector: {selector}")
                        return True

                if not articles:
                    self.logger.error("set_content() no encontró artículos con ningún selector")
                    return False
            else:
                self.logger.warning(f"HTML de FlareSolverr no contiene artículos ({total_matches})")

            return False

        except Exception as e:
            self.logger.error(f"Error navegando con FlareSolverr: {e}")
            return False

    def _build_search_url(self, model: str, page: int = 1) -> str:
        """
        Construye la URL de búsqueda para un modelo.

        Args:
            model: Nombre del modelo a buscar
            page: Número de página

        Returns:
            URL de búsqueda
        """
        # Catawiki usa parámetros de búsqueda en la URL
        query = model.replace(' ', '+')
        # Categoría 401 = Relojes de pulsera
        base = f"{self.base_url}/es/l/401-relojes-de-pulsera?q={query}"
        if page > 1:
            base += f"&page={page}"
        return base

    def _build_sold_search_url(self, model: str, page: int = 1) -> str:
        """
        Construye la URL de búsqueda de artículos vendidos.

        Args:
            model: Nombre del modelo a buscar
            page: Número de página

        Returns:
            URL de búsqueda de vendidos
        """
        query = model.replace(' ', '+')
        # Añadir filtro de subastas finalizadas
        base = f"{self.base_url}/es/l/401-relojes-de-pulsera?q={query}&filter_sold=true"
        if page > 1:
            base += f"&page={page}"
        return base

    async def _extract_apollo_state(self, page: Page) -> Optional[Dict]:
        """
        Extrae los datos de Apollo State de la página.
        Catawiki usa Apollo GraphQL y guarda datos en window.__APOLLO_STATE__.

        Args:
            page: Página de Playwright

        Returns:
            Diccionario con los datos o None
        """
        try:
            apollo_data = await page.evaluate("""
                () => {
                    if (window.__APOLLO_STATE__) {
                        return window.__APOLLO_STATE__;
                    }
                    // Buscar en scripts
                    const scripts = document.querySelectorAll('script');
                    for (const script of scripts) {
                        const text = script.textContent || '';
                        if (text.includes('__APOLLO_STATE__')) {
                            const match = text.match(/__APOLLO_STATE__\\s*=\\s*({.+?});/s);
                            if (match) {
                                try {
                                    return JSON.parse(match[1]);
                                } catch(e) {}
                            }
                        }
                    }
                    return null;
                }
            """)

            return apollo_data

        except Exception as e:
            self.logger.debug(f"No se pudo extraer Apollo State: {e}")
            return None

    async def _extract_next_data(self, page: Page) -> Optional[Dict]:
        """
        Extrae los datos de __NEXT_DATA__ si existe.

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

    async def _extract_listings_from_page(self, page: Page, generic_model: str) -> List[Dict[str, Any]]:
        """
        Extrae los listings de la página actual.

        Args:
            page: Página de Playwright
            generic_model: Modelo buscado

        Returns:
            Lista de listings extraídos
        """
        listings = []

        # Intentar extraer de Apollo State primero
        apollo_data = await self._extract_apollo_state(page)
        if apollo_data:
            listings = self._parse_apollo_listings(apollo_data, generic_model)
            if listings:
                self.logger.info(f"Extraídos {len(listings)} listings de Apollo State")
                return listings

        # Intentar extraer de __NEXT_DATA__
        next_data = await self._extract_next_data(page)
        if next_data:
            listings = self._parse_next_data_listings(next_data, generic_model)
            if listings:
                self.logger.info(f"Extraídos {len(listings)} listings de NEXT_DATA")
                return listings

        # Fallback: extraer del DOM
        listings = await self._extract_listings_from_dom(page, generic_model)
        self.logger.info(f"Extraídos {len(listings)} listings del DOM")

        return listings

    def _parse_apollo_listings(self, apollo_data: Dict, generic_model: str) -> List[Dict[str, Any]]:
        """
        Parsea los listings desde Apollo State.

        Args:
            apollo_data: Datos de Apollo
            generic_model: Modelo buscado

        Returns:
            Lista de listings
        """
        listings = []

        try:
            # Apollo guarda los objetos con claves como "Lot:12345"
            for key, value in apollo_data.items():
                if not isinstance(value, dict):
                    continue

                # Buscar objetos que parezcan lotes/productos
                if key.startswith('Lot:') or value.get('__typename') == 'Lot':
                    listing = self._parse_apollo_lot(value, generic_model)
                    if listing:
                        listings.append(listing)

        except Exception as e:
            self.logger.debug(f"Error parseando Apollo listings: {e}")

        return listings

    def _parse_apollo_lot(self, lot: Dict, generic_model: str) -> Optional[Dict[str, Any]]:
        """
        Parsea un lote individual de Apollo.

        Args:
            lot: Datos del lote
            generic_model: Modelo buscado

        Returns:
            Diccionario con datos del listing
        """
        try:
            listing_id = str(lot.get('id', ''))
            if not listing_id:
                return None

            # Extraer título/modelo
            title = lot.get('title', '') or lot.get('name', '')

            # Extraer precio
            current_bid = lot.get('currentBidAmount', {})
            if isinstance(current_bid, dict):
                price = current_bid.get('cents', 0) / 100 if current_bid.get('cents') else None
                currency = current_bid.get('currency', 'EUR')
            else:
                price = lot.get('hammerPrice', {}).get('cents', 0) / 100 if lot.get('hammerPrice') else None
                currency = 'EUR'

            # Extraer URL
            url = lot.get('url', '') or lot.get('path', '')
            if url and not url.startswith('http'):
                url = f"{self.base_url}{url}"

            # Extraer imagen
            image_url = ''
            images = lot.get('images', []) or lot.get('photos', [])
            if images and isinstance(images, list):
                first_img = images[0]
                if isinstance(first_img, dict):
                    image_url = first_img.get('url', '') or first_img.get('src', '')
                elif isinstance(first_img, str):
                    image_url = first_img

            # Estado de la subasta
            auction_state = lot.get('auctionState', '') or lot.get('state', '')
            is_sold = auction_state.lower() in ['closed', 'sold', 'ended']

            # Fecha de cierre
            closes_at = lot.get('closesAt', '') or lot.get('endDate', '')

            return {
                'listing_id': listing_id,
                'generic_model': generic_model,
                'specific_model': title,
                'listing_price': price,
                'currency': currency,
                'url': url,
                'image_url': image_url,
                'auction_state': auction_state,
                'is_sold': is_sold,
                'closes_at': closes_at,
                'platform': self.PLATFORM_NAME,
            }

        except Exception as e:
            self.logger.debug(f"Error parseando lote Apollo: {e}")
            return None

    def _parse_next_data_listings(self, next_data: Dict, generic_model: str) -> List[Dict[str, Any]]:
        """
        Parsea los listings desde __NEXT_DATA__.

        Args:
            next_data: Datos de Next.js
            generic_model: Modelo buscado

        Returns:
            Lista de listings
        """
        listings = []

        try:
            # Navegar por la estructura de Next.js
            props = next_data.get('props', {})
            page_props = props.get('pageProps', {})

            # Buscar lotes en diferentes ubicaciones posibles
            lots = (
                page_props.get('lots', []) or
                page_props.get('searchResults', {}).get('lots', []) or
                page_props.get('initialData', {}).get('lots', []) or
                []
            )

            for lot in lots:
                listing = self._parse_next_data_lot(lot, generic_model)
                if listing:
                    listings.append(listing)

        except Exception as e:
            self.logger.debug(f"Error parseando NEXT_DATA listings: {e}")

        return listings

    def _parse_next_data_lot(self, lot: Dict, generic_model: str) -> Optional[Dict[str, Any]]:
        """
        Parsea un lote individual de NEXT_DATA.

        Args:
            lot: Datos del lote
            generic_model: Modelo buscado

        Returns:
            Diccionario con datos del listing
        """
        try:
            listing_id = str(lot.get('id', '') or lot.get('lotId', ''))
            if not listing_id:
                return None

            title = lot.get('title', '') or lot.get('name', '')

            # Precio
            price_data = lot.get('currentBid', {}) or lot.get('price', {})
            if isinstance(price_data, dict):
                price = price_data.get('amount') or price_data.get('cents', 0) / 100
                currency = price_data.get('currency', 'EUR')
            else:
                price = float(price_data) if price_data else None
                currency = 'EUR'

            # URL
            url = lot.get('url', '') or lot.get('path', '')
            if url and not url.startswith('http'):
                url = f"{self.base_url}{url}"

            # Imagen
            image_url = ''
            images = lot.get('images', []) or lot.get('photos', [])
            if images:
                first_img = images[0] if isinstance(images, list) else images
                if isinstance(first_img, dict):
                    image_url = first_img.get('url', '') or first_img.get('large', '') or first_img.get('medium', '')
                elif isinstance(first_img, str):
                    image_url = first_img

            # Estado
            auction_state = lot.get('state', '') or lot.get('auctionState', '')
            is_sold = lot.get('isSold', False) or auction_state.lower() in ['closed', 'sold']

            return {
                'listing_id': listing_id,
                'generic_model': generic_model,
                'specific_model': title,
                'listing_price': price,
                'currency': currency,
                'url': url,
                'image_url': image_url,
                'auction_state': auction_state,
                'is_sold': is_sold,
                'platform': self.PLATFORM_NAME,
            }

        except Exception as e:
            self.logger.debug(f"Error parseando lote NEXT_DATA: {e}")
            return None

    async def _extract_listings_from_dom(self, page: Page, generic_model: str) -> List[Dict[str, Any]]:
        """
        Extrae los listings directamente del DOM.

        Args:
            page: Página de Playwright
            generic_model: Modelo buscado

        Returns:
            Lista de listings
        """
        listings = []

        # Selectores comunes para tarjetas de producto en Catawiki
        card_selectors = [
            "[data-testid='lot-card']",
            ".lot-card",
            "article[class*='lot']",
            "[class*='LotCard']",
            "a[href*='/l/'][class*='card']",
        ]

        articles = []
        for selector in card_selectors:
            articles = await page.query_selector_all(selector)
            if articles:
                self.logger.debug(f"Encontrados {len(articles)} artículos con selector: {selector}")
                break

        for article in articles:
            try:
                listing = await self._parse_dom_article(article, page, generic_model)
                if listing:
                    listings.append(listing)
            except Exception as e:
                self.logger.warning(f"Error parseando artículo DOM: {e}")
                continue

        return listings

    async def _parse_dom_article(self, article, page: Page, generic_model: str) -> Optional[Dict[str, Any]]:
        """
        Parsea un artículo del DOM.

        Args:
            article: Elemento del artículo
            page: Página de Playwright
            generic_model: Modelo buscado

        Returns:
            Diccionario con datos del listing
        """
        try:
            # Extraer URL y ID
            link_element = await article.query_selector("a[href*='/l/']")
            if not link_element:
                link_element = await article.query_selector("a")

            url = ""
            listing_id = ""
            if link_element:
                url = await link_element.get_attribute("href")
                if url and not url.startswith("http"):
                    url = f"{self.base_url}{url}"

                # Extraer ID del URL (formato: /l/12345678-nombre)
                id_match = re.search(r'/l/(\d+)', url)
                if id_match:
                    listing_id = id_match.group(1)

            if not listing_id:
                return None

            # Extraer título
            title = ""
            title_selectors = [
                "[data-testid='lot-title']",
                ".lot-title",
                "h3", "h4",
                "[class*='title']",
            ]
            for selector in title_selectors:
                title_el = await article.query_selector(selector)
                if title_el:
                    title = await title_el.text_content()
                    if title:
                        title = title.strip()
                        break

            # Extraer precio
            price = None
            price_selectors = [
                "[data-testid='current-bid']",
                "[data-testid='lot-price']",
                ".current-bid",
                "[class*='price']",
                "[class*='bid']",
            ]
            for selector in price_selectors:
                price_el = await article.query_selector(selector)
                if price_el:
                    price_text = await price_el.text_content()
                    price = self._parse_price(price_text)
                    if price:
                        break

            # Extraer imagen
            image_url = ""
            img_element = await article.query_selector("img")
            if img_element:
                for attr in ['data-src', 'data-lazy', 'srcset', 'src']:
                    img_val = await img_element.get_attribute(attr)
                    if img_val:
                        if attr == 'srcset':
                            img_val = img_val.split(',')[0].strip().split(' ')[0]
                        if img_val.startswith('http') or img_val.startswith('//'):
                            if img_val.startswith('//'):
                                img_val = 'https:' + img_val
                            image_url = img_val
                            break

            return {
                'listing_id': listing_id,
                'generic_model': generic_model,
                'specific_model': title,
                'listing_price': price,
                'currency': 'EUR',
                'url': url,
                'image_url': image_url,
                'platform': self.PLATFORM_NAME,
            }

        except Exception as e:
            self.logger.error(f"Error extrayendo datos del artículo DOM: {e}")
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

            cleaned = re.sub(r'[^\d.]', '', cleaned)
            return float(cleaned) if cleaned else None

        except (ValueError, AttributeError):
            return None

    def _parse_date(self, date_str: str) -> str:
        """
        Parsea una fecha a formato estándar.

        Args:
            date_str: String de fecha

        Returns:
            Fecha en formato YYYY-MM-DD o string vacío
        """
        if not date_str:
            return ""

        try:
            # Intentar varios formatos
            for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y']:
                try:
                    dt = datetime.strptime(date_str[:19], fmt)
                    return dt.strftime('%Y-%m-%d')
                except ValueError:
                    continue
        except Exception:
            pass

        return ""

    async def _search_using_searchbox(self, page: Page, query: str) -> bool:
        """
        Realiza una búsqueda usando el cuadro de búsqueda de la página.
        Esto simula el comportamiento de un usuario real.

        Args:
            page: Página de Playwright
            query: Término de búsqueda

        Returns:
            True si la búsqueda fue exitosa
        """
        try:
            self.logger.info(f"Buscando '{query}' usando el buscador...")

            # PASO 1: Primero intentar hacer clic en el icono/botón de búsqueda
            # Muchos sitios ocultan el input y solo muestran un icono
            search_trigger_selectors = [
                # Iconos y botones de búsqueda comunes
                "button[aria-label*='earch']",
                "button[aria-label*='uscar']",
                "[data-testid='search-button']",
                "[data-testid='search-trigger']",
                "[data-testid='search-icon']",
                "a[href*='search']",
                "[class*='search-trigger']",
                "[class*='search-icon']",
                "[class*='SearchTrigger']",
                "[class*='SearchIcon']",
                "button[class*='search']",
                "header button svg",  # Iconos SVG en header
                "nav button svg",
                # Selectores específicos de Catawiki
                "[class*='Header'] button",
                "[class*='header'] [class*='search']",
                "button[type='button'][class*='Search']",
            ]

            search_input = None

            # Primero intentar encontrar el input directamente (puede estar visible)
            direct_input_selectors = [
                "input[type='search']",
                "input[name='q']",
                "input[placeholder*='Buscar']",
                "input[placeholder*='Search']",
                "input[placeholder*='buscar']",
                "input[placeholder*='search']",
                "[data-testid='search-input']",
                "input[class*='search']",
                "input[class*='Search']",
                "#search-input",
                "header input[type='text']",
                "header input",
                "[role='search'] input",
                "[class*='SearchInput']",
                "[class*='search-input']",
            ]

            # Intentar encontrar input directamente
            for selector in direct_input_selectors:
                try:
                    search_input = await page.query_selector(selector)
                    if search_input:
                        is_visible = await search_input.is_visible()
                        if is_visible:
                            self.logger.info(f"Input de búsqueda encontrado directamente: {selector}")
                            break
                        else:
                            search_input = None
                except Exception:
                    continue

            # Si no encontramos input visible, intentar activar el buscador con un clic
            if not search_input:
                self.logger.debug("Input no visible, buscando botón/icono de búsqueda...")

                for trigger_selector in search_trigger_selectors:
                    try:
                        trigger = await page.query_selector(trigger_selector)
                        if trigger:
                            is_visible = await trigger.is_visible()
                            if is_visible:
                                self.logger.info(f"Clic en trigger de búsqueda: {trigger_selector}")
                                await trigger.click()
                                await asyncio.sleep(1)

                                # Ahora buscar el input que debería aparecer
                                for input_selector in direct_input_selectors:
                                    try:
                                        search_input = await page.query_selector(input_selector)
                                        if search_input:
                                            is_input_visible = await search_input.is_visible()
                                            if is_input_visible:
                                                self.logger.info(f"Input encontrado después del clic: {input_selector}")
                                                break
                                            else:
                                                search_input = None
                                    except Exception:
                                        continue

                                if search_input:
                                    break
                    except Exception:
                        continue

            # PASO 2: Si aún no encontramos, intentar usar el teclado (Ctrl+K o /)
            if not search_input:
                self.logger.debug("Intentando atajos de teclado para búsqueda...")
                for shortcut in ["/", "Control+k", "Meta+k"]:
                    try:
                        await page.keyboard.press(shortcut)
                        await asyncio.sleep(0.8)

                        for input_selector in direct_input_selectors:
                            try:
                                search_input = await page.query_selector(input_selector)
                                if search_input and await search_input.is_visible():
                                    self.logger.info(f"Input encontrado con atajo {shortcut}: {input_selector}")
                                    break
                            except Exception:
                                continue

                        if search_input:
                            break
                    except Exception:
                        continue

            if not search_input:
                # Último intento: hacer screenshot y buscar en el HTML
                self.logger.warning("No se encontró el cuadro de búsqueda con selectores conocidos")

                # Imprimir el HTML del header para debug
                try:
                    header_html = await page.evaluate("""
                        () => {
                            const header = document.querySelector('header') || document.querySelector('nav');
                            return header ? header.outerHTML.substring(0, 2000) : 'No header found';
                        }
                    """)
                    self.logger.debug(f"HTML del header (primeros 500 chars): {header_html[:500]}...")
                except Exception:
                    pass

                return False

            # PASO 3: Interactuar con el input encontrado
            # Limpiar el campo primero
            await search_input.click()
            await asyncio.sleep(0.3)

            # Seleccionar todo y borrar (por si hay texto previo)
            await page.keyboard.press("Control+a")
            await asyncio.sleep(0.1)

            # Escribir el término de búsqueda letra por letra (más humano)
            for char in query:
                await search_input.type(char, delay=random.randint(50, 150))
                await asyncio.sleep(random.uniform(0.03, 0.08))

            self.logger.info(f"Texto escrito en buscador: '{query}'")
            await asyncio.sleep(1.5)

            # Esperar sugerencias de autocompletado si aparecen
            try:
                suggestions = await page.query_selector("[class*='suggestion'], [class*='autocomplete'], [role='listbox']")
                if suggestions:
                    self.logger.debug("Detectadas sugerencias de autocompletado")
                    await asyncio.sleep(0.5)
            except Exception:
                pass

            # Presionar Enter
            await page.keyboard.press("Enter")
            self.logger.info("Enter presionado, esperando resultados...")

            # Esperar a que cargue la página de resultados
            await asyncio.sleep(5)

            # Verificar que estamos en una página de resultados
            current_url = page.url
            self.logger.info(f"URL actual: {current_url}")

            if 'q=' in current_url or 'search' in current_url.lower() or 'buscar' in current_url.lower():
                self.logger.info(f"Búsqueda exitosa, URL de resultados detectada")
                return True
            else:
                # Verificar si hay resultados en la página actual
                results_selectors = [
                    "[data-testid='lot-card']",
                    ".lot-card",
                    "article[class*='lot']",
                    "[class*='LotCard']",
                    "[class*='SearchResult']",
                    "[class*='search-result']",
                ]
                for sel in results_selectors:
                    results = await page.query_selector_all(sel)
                    if results:
                        self.logger.info(f"Encontrados {len(results)} resultados con selector {sel}")
                        return True

                self.logger.warning(f"URL no parece de resultados, pero intentaremos extraer: {current_url[:80]}...")
                return True  # Intentar extraer de todas formas

        except Exception as e:
            self.logger.error(f"Error en búsqueda: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
            return False

    async def scrape_model(self, model: str, max_pages: int = 3) -> List[Dict[str, Any]]:
        """
        Scrapea un modelo específico.

        Args:
            model: Nombre del modelo
            max_pages: Máximo de páginas a scrapear

        Returns:
            Lista de listings encontrados
        """
        all_listings = []

        async with self.get_page() as page:
            # Inicializar sesión primero (solo una vez)
            if not await self._initialize_session(page):
                self.logger.error("No se pudo inicializar la sesión en Catawiki")
                return []

            # Para la primera página, usar el buscador
            self.logger.info(f"Scrapeando Catawiki: {model} - Página 1")

            # Intentar primero usando el buscador (simula usuario real)
            search_success = await self._search_using_searchbox(page, f"{model} reloj")

            if not search_success:
                self.logger.warning("Búsqueda por buscador falló, intentando navegación directa...")
                url = self._build_search_url(model, 1)
                self.logger.info(f"URL construida: {url}")
                try:
                    response = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    await asyncio.sleep(4)

                    # CRITICAL: Verificar si Catawiki redirigió a otra categoría
                    current_url = page.url
                    self.logger.info(f"URL actual después de navegación: {current_url}")

                    # Catawiki redirige automáticamente si no hay resultados en la categoría
                    # URL esperada: /es/l/401-relojes-de-pulsera
                    # Si redirige a otra categoría (ej: /es/c/153-comics), abortar
                    if "/l/401-relojes-de-pulsera" not in current_url and "/c/401-" not in current_url:
                        self.logger.warning(f"Catawiki redirigió a otra categoría: {current_url}")
                        self.logger.warning(f"Probablemente no hay resultados para '{model}' en categoría de relojes")

                        # Intentar con términos más específicos
                        self.logger.info(f"Reintentando con términos más específicos: '{model} watch reloj'")
                        specific_query = f"{model.replace(' ', '+')}+watch+reloj"
                        url_retry = f"{self.base_url}/es/l/401-relojes-de-pulsera?q={specific_query}"
                        response = await page.goto(url_retry, wait_until="domcontentloaded", timeout=60000)
                        await asyncio.sleep(4)

                        # Verificar nuevamente si redirigió
                        if "/l/401-relojes-de-pulsera" not in page.url and "/c/401-" not in page.url:
                            self.logger.error(f"Catawiki sigue redirigiendo a otra categoría: {page.url}")
                            self.logger.error(f"No hay resultados en categoría de relojes para '{model}', abortando")
                            return []
                        else:
                            self.logger.info(f"Búsqueda específica exitosa: {page.url}")

                    if response and response.status >= 400:
                        self.logger.error(f"Navegación directa falló: HTTP {response.status}")

                        # RESCATE CON FLARESOLVERR
                        from config import USE_FLARESOLVERR
                        if USE_FLARESOLVERR:
                            self.logger.info("Intentando rescate con FlareSolverr en página 1...")
                            rescued = await self._navigate_with_flaresolverr(page, url)
                            if not rescued:
                                self.logger.error("FlareSolverr también falló, terminando")
                                return []
                        else:
                            return []

                except Exception as e:
                    self.logger.error(f"Error en navegación directa: {e}")

                    # RESCATE CON FLARESOLVERR
                    from config import USE_FLARESOLVERR
                    if USE_FLARESOLVERR:
                        self.logger.info("Intentando rescate con FlareSolverr después de excepción...")
                        rescued = await self._navigate_with_flaresolverr(page, url)
                        if not rescued:
                            return []
                    else:
                        return []

            # Simular comportamiento humano
            await self.simulate_human_behavior(page)
            await self.random_delay()

            # Intentar esperar por elementos de producto
            try:
                await page.wait_for_selector(
                    "[data-testid='lot-card'], .lot-card, article[class*='lot'], [class*='LotCard'], a[href*='/l/']",
                    timeout=15000
                )
            except Exception:
                self.logger.debug("No se encontraron elementos de lote, probando scroll...")
                for _ in range(3):
                    await page.evaluate("window.scrollBy(0, 500)")
                    await asyncio.sleep(1)
                await page.evaluate("window.scrollTo(0, 0)")
                await asyncio.sleep(2)

            # Extraer listings de la primera página
            listings = await self._extract_listings_from_page(page, model)
            if listings:
                all_listings.extend(listings)
                self.logger.info(f"Página 1: {len(listings)} listings")
            else:
                self.logger.info("No se encontraron listings en página 1")

            # Páginas adicionales (si hay más de 1) - Loop híbrido de 3 niveles
            consecutive_failures = 0  # Contador de fallos consecutivos

            for page_num in range(2, max_pages + 1):
                # Delay aleatorio entre páginas
                delay = random.uniform(5, 8)
                self.logger.debug(f"Esperando {delay:.1f}s antes de página {page_num}")
                await asyncio.sleep(delay)

                navigated = False

                # Construir URL para página N (Catawiki usa parámetro simple ?page=N)
                if '?q=' in page.url:
                    # Ya tiene query string
                    if 'page=' in page.url:
                        target_url = re.sub(r'page=\d+', f'page={page_num}', page.url)
                    else:
                        target_url = f"{page.url}&page={page_num}"
                else:
                    # Reconstruir URL desde cero (búsqueda por modelo)
                    target_url = self._build_search_url(model, page_num)

                self.logger.debug(f"URL paginación página {page_num}: {target_url[:100]}...")

                # === NIVEL 1: goto() directo con cookies existentes (rápido, 0 overhead) ===
                if not navigated:
                    try:
                        self.logger.info(f"Página {page_num}: Intentando goto() directo...")
                        response = await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                        if response and response.ok:
                            await asyncio.sleep(random.uniform(2, 4))
                            await self._close_overlays(page)
                            articles = await page.query_selector_all("[data-testid='lot-card'], .lot-card")
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

                    # Cerrar overlays antes de buscar botón
                    await self._close_overlays(page)

                    next_selectors = [
                        f"a[href*='page={page_num}']",
                        "button[aria-label*='siguiente']",
                        "button[aria-label*='next']",
                        "[data-testid='pagination-next']",
                        "a.pagination-next",
                    ]

                    for selector in next_selectors:
                        try:
                            next_btn = await page.query_selector(selector)
                            if next_btn and await next_btn.is_visible():
                                await next_btn.scroll_into_view_if_needed()
                                await asyncio.sleep(random.uniform(0.5, 1.0))
                                await next_btn.click()
                                await asyncio.sleep(random.uniform(2, 4))

                                # Verificar que navegó correctamente
                                articles = await page.query_selector_all("[data-testid='lot-card'], .lot-card")
                                if articles:
                                    navigated = True
                                    self.logger.info(f"Página {page_num}: click 'Siguiente' exitoso ({len(articles)} artículos)")
                                    break
                        except Exception:
                            continue

                # === NIVEL 3: FlareSolverr + estrategia dual (lento pero robusto) ===
                from config import USE_FLARESOLVERR
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

                # Cerrar cualquier overlay antes de scrapear
                await self._close_overlays(page)

                # Simular comportamiento humano
                await self.simulate_human_behavior(page)

                # Extraer listings
                self.logger.info(f"Scrapeando Catawiki: {model} - Página {page_num}")
                listings = await self._extract_listings_from_page(page, model)

                if listings:
                    all_listings.extend(listings)
                    self.logger.info(f"Página {page_num}: {len(listings)} listings")
                else:
                    self.logger.info(f"No se encontraron más listings en página {page_num}")
                    consecutive_failures += 1
                    if consecutive_failures >= 2:
                        break

        # Eliminar duplicados por listing_id
        seen = set()
        unique_listings = []
        for listing in all_listings:
            if listing['listing_id'] not in seen:
                seen.add(listing['listing_id'])
                unique_listings.append(listing)

        return unique_listings

    async def scrape(self, models: List[str], max_pages: int = 3) -> List[Dict[str, Any]]:
        """
        Scrapea múltiples modelos.

        Args:
            models: Lista de modelos a buscar
            max_pages: Máximo de páginas por modelo

        Returns:
            Lista de todos los listings encontrados
        """
        all_listings = []

        for model in models:
            self.logger.info(f"=== Buscando modelo: {model} ===")
            listings = await self.scrape_model(model, max_pages)
            all_listings.extend(listings)
            self.logger.info(f"Total para {model}: {len(listings)} listings")

        self.logger.info(f"Total general Catawiki: {len(all_listings)} listings")
        return all_listings

    async def scrape_item_detail(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Extrae detalles de un item individual.
        Implementación del método abstracto de BaseScraper.

        Args:
            url: URL del artículo

        Returns:
            Diccionario con los detalles o None
        """
        return await self.get_item_details(url)

    async def get_item_details(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene los detalles completos de un artículo.

        Args:
            url: URL del artículo

        Returns:
            Diccionario con los detalles o None
        """
        async with self.get_page() as page:
            try:
                success = await self.safe_goto(page, url)
                if not success:
                    return None

                await self.random_delay()

                # Extraer ID del URL
                id_match = re.search(r'/l/(\d+)', url)
                listing_id = id_match.group(1) if id_match else ""

                # Intentar obtener datos estructurados
                apollo_data = await self._extract_apollo_state(page)
                if apollo_data and listing_id:
                    lot_key = f"Lot:{listing_id}"
                    if lot_key in apollo_data:
                        return self._parse_apollo_lot(apollo_data[lot_key], "")

                # Extraer del DOM
                title = ""
                title_el = await page.query_selector("h1, [data-testid='lot-title']")
                if title_el:
                    title = await title_el.text_content()

                # Precio actual/final
                price = None
                price_selectors = [
                    "[data-testid='current-bid']",
                    "[data-testid='winning-bid']",
                    "[class*='hammer-price']",
                    "[class*='current-bid']",
                ]
                for selector in price_selectors:
                    price_el = await page.query_selector(selector)
                    if price_el:
                        price_text = await price_el.text_content()
                        price = self._parse_price(price_text)
                        if price:
                            break

                # Imagen principal
                image_url = ""
                img_el = await page.query_selector("[data-testid='lot-image'] img, .lot-image img, img[class*='main']")
                if img_el:
                    image_url = await img_el.get_attribute("src") or ""

                # Descripción
                description = ""
                desc_el = await page.query_selector("[data-testid='lot-description'], .lot-description")
                if desc_el:
                    description = await desc_el.text_content()

                return {
                    'listing_id': listing_id,
                    'specific_model': title.strip() if title else "",
                    'listing_price': price,
                    'currency': 'EUR',
                    'image_url': image_url,
                    'description': description.strip() if description else "",
                    'url': url,
                    'platform': self.PLATFORM_NAME,
                }

            except Exception as e:
                self.logger.error(f"Error extrayendo detalles de {url}: {e}")
                return None
