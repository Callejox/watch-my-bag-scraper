"""
Clase base para los scrapers con Playwright y stealth.
Proporciona funcionalidad común para manejar navegación, anti-detección y reintentos.
"""

import asyncio
import random
import aiohttp
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
from datetime import date

from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from playwright_stealth import Stealth
from tenacity import retry, stop_after_attempt, wait_exponential
from loguru import logger

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    REQUEST_DELAY_MIN,
    REQUEST_DELAY_MAX,
    MAX_RETRIES,
    PAGE_TIMEOUT,
    USER_AGENTS,
    IMAGES_DIR,
    DOWNLOAD_IMAGES,
)


class BaseScraper(ABC):
    """
    Clase base abstracta para scrapers.

    Proporciona:
    - Gestión de Playwright con stealth
    - Rate limiting automático
    - Reintentos con backoff exponencial
    - Simulación de comportamiento humano
    - Logging integrado
    """

    PLATFORM_NAME: str = "base"

    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self.logger = logger.bind(scraper=self.PLATFORM_NAME)

    async def start(self) -> None:
        """Inicializa Playwright y el navegador."""
        self.logger.info(f"Iniciando scraper {self.PLATFORM_NAME}")
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=False,  # Desactivado para evitar detección de Cloudflare
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--window-position=0,0",
                "--ignore-certificate-errors",
                "--ignore-certificate-errors-spki-list",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
            ]
        )
        self.logger.info("Navegador iniciado correctamente")

    async def stop(self) -> None:
        """Cierra el navegador y limpia recursos."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self.logger.info(f"Scraper {self.PLATFORM_NAME} detenido")

    async def __aenter__(self):
        """Permite usar el scraper como context manager."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cierra el scraper al salir del context manager."""
        await self.stop()

    def _get_random_user_agent(self) -> str:
        """Retorna un User-Agent aleatorio."""
        return random.choice(USER_AGENTS)

    @asynccontextmanager
    async def get_page(self) -> Page:
        """
        Context manager que proporciona una página configurada con stealth.

        Usage:
            async with scraper.get_page() as page:
                await page.goto("https://example.com")
        """
        context = await self._browser.new_context(
            viewport={"width": random.randint(1200, 1920), "height": random.randint(800, 1080)},
            user_agent=self._get_random_user_agent(),
            locale="es-ES",
            timezone_id="Europe/Madrid",
            java_script_enabled=True,
        )

        page = await context.new_page()

        # Aplicar configuración stealth
        await Stealth().apply_stealth_async(page)

        # Configurar headers adicionales
        await page.set_extra_http_headers({
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        })

        # Configurar timeout
        page.set_default_timeout(PAGE_TIMEOUT)

        try:
            yield page
        finally:
            await context.close()

    async def random_delay(self) -> None:
        """Espera un tiempo aleatorio entre requests."""
        delay = random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
        self.logger.debug(f"Esperando {delay:.2f} segundos")
        await asyncio.sleep(delay)

    async def simulate_human_behavior(self, page: Page) -> None:
        """
        Simula comportamiento humano en la página.
        Realiza scroll y movimientos de ratón aleatorios.
        """
        # Scroll aleatorio
        scroll_amount = random.randint(100, 500)
        await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
        await asyncio.sleep(random.uniform(0.3, 1.0))

        # Movimiento de ratón aleatorio
        await page.mouse.move(
            random.randint(100, 800),
            random.randint(100, 600)
        )
        await asyncio.sleep(random.uniform(0.2, 0.5))

    async def handle_cloudflare(self, page: Page) -> bool:
        """
        Detecta y maneja la página de verificación de Cloudflare.

        Returns:
            True si se detectó y manejó Cloudflare, False en caso contrario
        """
        cloudflare_selectors = [
            "#challenge-running",
            ".cf-browser-verification",
            "#cf-challenge-running",
            "#challenge-stage",
            "div.cf-turnstile",
        ]

        for selector in cloudflare_selectors:
            element = await page.query_selector(selector)
            if element:
                self.logger.warning("Detectada verificación de Cloudflare, esperando...")
                # Esperar hasta 30 segundos para que se resuelva
                try:
                    await page.wait_for_selector(selector, state="hidden", timeout=30000)
                    self.logger.info("Verificación de Cloudflare completada")
                    await asyncio.sleep(2)  # Espera adicional
                    return True
                except Exception:
                    self.logger.error("Timeout esperando Cloudflare")
                    return True

        return False

    async def safe_goto(
        self,
        page: Page,
        url: str,
        wait_until: str = "domcontentloaded"
    ) -> bool:
        """
        Navega a una URL de forma segura con manejo de errores.

        Args:
            page: Página de Playwright
            url: URL a visitar
            wait_until: Condición de espera ('load', 'domcontentloaded', 'networkidle')

        Returns:
            True si la navegación fue exitosa, False en caso contrario
        """
        try:
            self.logger.debug(f"Navegando a: {url}")
            response = await page.goto(url, wait_until=wait_until, timeout=60000)

            # Esperar un poco para que cargue el contenido dinámico
            await asyncio.sleep(3)

            # Verificar código de respuesta
            if response and response.status >= 400:
                self.logger.warning(f"Respuesta HTTP {response.status} para {url}")
                return False

            # Manejar posible Cloudflare
            await self.handle_cloudflare(page)

            # Simular comportamiento humano
            await self.simulate_human_behavior(page)

            return True

        except Exception as e:
            self.logger.error(f"Error navegando a {url}: {e}")
            return False

    async def extract_text(
        self,
        page: Page,
        selector: str,
        default: str = ""
    ) -> str:
        """
        Extrae texto de un elemento de forma segura.

        Args:
            page: Página de Playwright
            selector: Selector CSS
            default: Valor por defecto si no se encuentra

        Returns:
            Texto del elemento o valor por defecto
        """
        try:
            element = await page.query_selector(selector)
            if element:
                text = await element.text_content()
                return text.strip() if text else default
        except Exception as e:
            self.logger.debug(f"No se pudo extraer texto de '{selector}': {e}")
        return default

    async def extract_attribute(
        self,
        page: Page,
        selector: str,
        attribute: str,
        default: str = ""
    ) -> str:
        """
        Extrae un atributo de un elemento de forma segura.

        Args:
            page: Página de Playwright
            selector: Selector CSS
            attribute: Nombre del atributo (href, src, etc.)
            default: Valor por defecto

        Returns:
            Valor del atributo o valor por defecto
        """
        try:
            element = await page.query_selector(selector)
            if element:
                value = await element.get_attribute(attribute)
                return value if value else default
        except Exception as e:
            self.logger.debug(f"No se pudo extraer atributo '{attribute}' de '{selector}': {e}")
        return default

    async def scroll_to_load_all(
        self,
        page: Page,
        max_scrolls: int = 20,
        scroll_delay: float = 1.0
    ) -> None:
        """
        Hace scroll hasta el final de la página para cargar contenido lazy-loaded.

        Args:
            page: Página de Playwright
            max_scrolls: Número máximo de scrolls
            scroll_delay: Tiempo entre scrolls
        """
        last_height = 0

        for i in range(max_scrolls):
            # Obtener altura actual
            current_height = await page.evaluate("document.body.scrollHeight")

            if current_height == last_height:
                self.logger.debug(f"Scroll completado después de {i} iteraciones")
                break

            # Scroll al final
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(scroll_delay)

            last_height = current_height

    @abstractmethod
    async def scrape(self, **kwargs) -> List[Dict[str, Any]]:
        """
        Método principal de scraping. Debe ser implementado por cada subclase.

        Returns:
            Lista de diccionarios con los datos extraídos
        """
        pass

    @abstractmethod
    async def scrape_item_detail(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Extrae detalles de un item individual.

        Args:
            url: URL del item

        Returns:
            Diccionario con los datos del item o None si falla
        """
        pass

    async def download_image(
        self,
        image_url: str,
        listing_id: str,
        platform: str = None
    ) -> Optional[str]:
        """
        Descarga una imagen y la guarda localmente.

        Args:
            image_url: URL de la imagen
            listing_id: ID del listing (para nombrar el archivo)
            platform: Nombre de la plataforma (chrono24, vestiaire)

        Returns:
            Path local del archivo guardado o None si falla
        """
        if not DOWNLOAD_IMAGES or not image_url:
            return None

        try:
            # Crear directorio de imágenes si no existe
            platform = platform or self.PLATFORM_NAME
            today = date.today().isoformat()
            img_dir = IMAGES_DIR / platform / today
            img_dir.mkdir(parents=True, exist_ok=True)

            # Determinar extensión del archivo
            ext = '.jpg'
            if '.png' in image_url.lower():
                ext = '.png'
            elif '.webp' in image_url.lower():
                ext = '.webp'

            # Nombre del archivo basado en listing_id
            filename = f"{listing_id}{ext}"
            filepath = img_dir / filename

            # Si ya existe, no descargar de nuevo
            if filepath.exists():
                self.logger.debug(f"Imagen ya existe: {filepath}")
                return str(filepath)

            # Descargar imagen
            async with aiohttp.ClientSession() as session:
                headers = {
                    'User-Agent': self._get_random_user_agent(),
                    'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                }
                async with session.get(image_url, headers=headers, timeout=30) as response:
                    if response.status == 200:
                        content = await response.read()
                        filepath.write_bytes(content)
                        self.logger.debug(f"Imagen guardada: {filepath}")
                        return str(filepath)
                    else:
                        self.logger.warning(f"Error descargando imagen: HTTP {response.status}")
                        return None

        except Exception as e:
            self.logger.warning(f"Error descargando imagen {image_url}: {e}")
            return None

    async def download_images_for_listings(
        self,
        listings: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Descarga imágenes para una lista de listings y añade el path local.

        Args:
            listings: Lista de listings con image_url

        Returns:
            Lista de listings actualizada con image_local_path
        """
        if not DOWNLOAD_IMAGES:
            return listings

        for listing in listings:
            image_url = listing.get('image_url')
            listing_id = listing.get('listing_id')

            if image_url and listing_id:
                local_path = await self.download_image(
                    image_url,
                    listing_id,
                    listing.get('platform', self.PLATFORM_NAME)
                )
                listing['image_local_path'] = local_path

        return listings
