"""
Dashboard interactivo para visualizar inventario y ventas de relojes.
Ejecutar con: streamlit run dashboard.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
from pathlib import Path
import sys

# Configurar path del proyecto
sys.path.insert(0, str(Path(__file__).parent))
from database.db_manager import DatabaseManager
from config import EXPORTS_DIR, IMAGES_DIR, CHRONO24_MODELS, VESTIAIRE_SELLER_IDS


def get_best_image_source(item: dict, platform: str = None) -> tuple:
    """
    Determina la mejor fuente de imagen (local o remota) con fallback automático.

    Args:
        item: Diccionario con datos del producto
        platform: Plataforma opcional (si no está en item)

    Returns:
        Tupla (image_source, is_local) donde:
        - image_source: Path local o URL remota
        - is_local: True si es archivo local, False si es URL remota
    """
    platform = platform or item.get('platform', '')
    image_local_path = item.get('image_local_path')
    image_url = item.get('image_url', '')

    # Limpiar URL de imagen para Chrono24 (eliminar placeholders _SIZE_)
    if platform == 'chrono24' and image_url:
        image_url = clean_chrono24_image_url(image_url)

    # Prioridad 1: Imagen local si existe
    if image_local_path:
        local_path = Path(image_local_path)
        if local_path.exists() and local_path.is_file():
            return (str(local_path), True)

    # Prioridad 2: URL remota como fallback
    if image_url and image_url.startswith('http'):
        return (image_url, False)

    # Sin imagen disponible
    return (None, False)


# Configuración de la página
st.set_page_config(
    page_title="Inventario de Relojes",
    page_icon="⌚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizado para tarjetas con imágenes alineadas
st.markdown("""
<style>
    /* ============================================
       GRID DE PRODUCTOS - ALINEACIÓN PERFECTA
       ============================================ */

    /* Contenedor grid principal */
    .products-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
        gap: 20px;
        padding: 10px 0;
    }

    /* Tarjeta de producto individual */
    .product-card {
        background: linear-gradient(135deg, #1e1e2e 0%, #252535 100%);
        border-radius: 12px;
        padding: 12px;
        border: 1px solid #3a3a4a;
        display: flex;
        flex-direction: column;
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .product-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 8px 25px rgba(0,0,0,0.4);
    }

    /* Contenedor de imagen FIJO */
    .product-image-container {
        width: 100%;
        height: 180px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: #f8f8f8;
        border-radius: 8px;
        overflow: hidden;
        margin-bottom: 10px;
    }
    .product-image-container img {
        max-width: 100%;
        max-height: 180px;
        width: auto;
        height: auto;
        object-fit: contain;
    }
    .product-no-image {
        color: #888;
        font-size: 3rem;
    }

    /* Contenido de la tarjeta */
    .product-title {
        font-size: 0.95rem;
        font-weight: 600;
        color: #e0e0e0;
        margin-bottom: 8px;
        line-height: 1.3;
        min-height: 2.6em;
        overflow: hidden;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
    }
    .product-price {
        font-size: 1.3rem;
        font-weight: 700;
        color: #00d9ff;
        margin-bottom: 8px;
    }
    .product-platform {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.7rem;
        font-weight: 600;
        margin-bottom: 8px;
    }
    .platform-chrono24 { background: #ff6b35; color: white; }
    .platform-vestiaire { background: #00a86b; color: white; }
    .platform-catawiki { background: #f5a623; color: white; }

    .product-info {
        font-size: 0.8rem;
        color: #a0a0a0;
        margin: 2px 0;
    }
    .product-link {
        display: block;
        text-align: center;
        padding: 8px;
        background: #3a3a5a;
        color: #00d9ff;
        text-decoration: none;
        border-radius: 6px;
        margin-top: auto;
        font-size: 0.85rem;
    }
    .product-link:hover {
        background: #4a4a6a;
    }
    .sold-badge {
        background: #e94560;
        color: white;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.7rem;
        font-weight: 600;
        margin-bottom: 5px;
        display: inline-block;
    }

    /* ============================================
       ESTILOS ANTIGUOS (para compatibilidad)
       ============================================ */

    /* FORZAR ALINEACIÓN VERTICAL EN COLUMNAS DE STREAMLIT */
    [data-testid="stHorizontalBlock"] {
        align-items: flex-start !important;
    }
    [data-testid="stVerticalBlock"] {
        gap: 0.5rem !important;
    }

    /* Contenedor de imagen con altura FIJA absoluta */
    .image-container {
        width: 100%;
        height: 180px !important;
        min-height: 180px !important;
        max-height: 180px !important;
        display: flex;
        align-items: center;
        justify-content: center;
        background: #f8f8f8;
        border-radius: 8px;
        overflow: hidden;
        margin-bottom: 10px;
        box-sizing: border-box;
    }
    .image-container img {
        max-width: 100%;
        max-height: 180px;
        width: auto;
        height: auto;
        object-fit: contain;
        display: block;
    }

    /* Título con altura FIJA para evitar desalineación */
    .fixed-title {
        height: 2.6em !important;
        min-height: 2.6em !important;
        max-height: 2.6em !important;
        overflow: hidden;
        font-weight: 600;
        font-size: 0.95rem;
        line-height: 1.3;
        color: #e0e0e0;
        margin-bottom: 5px;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
    }

    .no-image, .product-no-image {
        color: #aaa;
        font-size: 3rem;
        display: flex;
        align-items: center;
        justify-content: center;
        width: 100%;
        height: 180px;
        background: #f0f0f0;
        border-radius: 8px;
    }

    .watch-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border-radius: 12px;
        padding: 15px;
        margin: 10px 0;
        border: 1px solid #0f3460;
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .watch-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(0,0,0,0.3);
    }
    .watch-image {
        border-radius: 8px;
        width: 100%;
        height: 200px;
        object-fit: cover;
        background: #2a2a4a;
    }
    .watch-title {
        font-size: 1.1rem;
        font-weight: 600;
        color: #e94560;
        margin: 10px 0 5px 0;
    }
    .watch-price {
        font-size: 1.3rem;
        font-weight: 700;
        color: #00d9ff;
    }
    .watch-detail {
        font-size: 0.85rem;
        color: #a0a0a0;
        margin: 3px 0;
    }
    .stat-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 10px;
        padding: 20px;
        text-align: center;
    }
    .stat-number {
        font-size: 2.5rem;
        font-weight: 700;
        color: white;
    }
    .stat-label {
        font-size: 0.9rem;
        color: rgba(255,255,255,0.8);
    }
    .platform-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 15px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .platform-chrono24 {
        background: #ff6b35;
        color: white;
    }
    .platform-vestiaire {
        background: #00a86b;
        color: white;
    }
    .platform-catawiki {
        background: #f5a623;
        color: white;
    }
    .sold-badge {
        background: #e94560;
        color: white;
        padding: 3px 10px;
        border-radius: 15px;
        font-size: 0.75rem;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_db():
    """Inicializa la conexión a la base de datos."""
    return DatabaseManager()


def format_price(price, currency="EUR"):
    """Formatea un precio con símbolo de moneda."""
    if price is None:
        return "N/A"
    if currency == "EUR":
        return f"€{price:,.0f}"
    return f"{price:,.0f} {currency}"


def clean_chrono24_image_url(image_url: str) -> str:
    """
    Limpia y normaliza la URL de imagen de Chrono24.

    Chrono24 usa URLs con placeholders como 'Square_SIZE_' que deben ser
    reemplazados por tamaños reales.

    Args:
        image_url: URL de imagen original

    Returns:
        URL de imagen limpia y funcional
    """
    if not image_url:
        # Si no hay URL, no podemos hacer nada
        # (Las URLs construidas no funcionan para artículos vendidos)
        return ""

    # Rechazar URLs que son iconos o SVGs
    img_lower = image_url.lower()
    invalid_patterns = ['certified', 'icon', 'logo', 'badge', '.svg', 'default', 'placeholder', 'sprite']
    if any(pattern in img_lower for pattern in invalid_patterns):
        # Para URLs inválidas, no tenemos alternativa confiable
        return ""

    # Reemplazar placeholders de tamaño con valores reales
    # Large ofrece mejor resolución que Square100
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

    # Normalizar el dominio a img.chrono24.com
    if 'cdn2.chrono24.com' in image_url:
        image_url = image_url.replace('cdn2.chrono24.com', 'img.chrono24.com')

    # Asegurar que la URL usa https
    if image_url.startswith('http://'):
        image_url = image_url.replace('http://', 'https://')

    return image_url


def get_platform_badge(platform):
    """Genera badge HTML para la plataforma."""
    if platform == "chrono24":
        return '<span class="platform-badge platform-chrono24">Chrono24</span>'
    elif platform == "vestiaire":
        return '<span class="platform-badge platform-vestiaire">Vestiaire</span>'
    elif platform == "catawiki":
        return '<span class="platform-badge platform-catawiki">Catawiki</span>'
    return f'<span class="platform-badge">{platform}</span>'


def render_product_card_html(item, show_sold=False):
    """
    Genera el HTML de una tarjeta de producto individual.

    Args:
        item: Diccionario con datos del producto
        show_sold: Si es True, muestra badge de vendido

    Returns:
        String HTML de la tarjeta
    """
    import html as html_lib
    import base64

    title = item.get('specific_model') or item.get('product_name') or 'Sin nombre'
    price = item.get('listing_price') or item.get('sale_price')
    platform = item.get('platform', '')
    url = item.get('url', '')
    location = item.get('seller_location', '')
    reference = item.get('reference_number', '')
    brand = item.get('brand', '')

    # Escapar caracteres HTML en el título
    title_escaped = html_lib.escape(title[:60] + '...' if len(title) > 60 else title)

    # Obtener mejor fuente de imagen (local con fallback a remoto)
    image_source, is_local = get_best_image_source(item, platform)

    # Imagen o placeholder
    if image_source:
        if is_local:
            # Convertir imagen local a base64 data URI para HTML
            try:
                img_path = Path(image_source)
                img_data = img_path.read_bytes()
                img_base64 = base64.b64encode(img_data).decode()
                # Detectar tipo MIME
                ext = img_path.suffix.lower()
                mime_type = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                           '.png': 'image/png', '.webp': 'image/webp'}.get(ext, 'image/jpeg')
                image_html = f'<img src="data:{mime_type};base64,{img_base64}" alt="{title_escaped}" loading="lazy">'
            except Exception:
                # Fallback a URL remota si existe
                remote_url = item.get('image_url', '')
                if remote_url and remote_url.startswith('http'):
                    image_html = f'<img src="{remote_url}" alt="{title_escaped}" loading="lazy">'
                else:
                    image_html = '<span class="product-no-image">📷</span>'
        else:
            # URL remota
            image_html = f'<img src="{image_source}" alt="{title_escaped}" loading="lazy">'
    else:
        image_html = '<span class="product-no-image">📷</span>'

    # Badge de plataforma
    platform_class = f"platform-{platform}" if platform else ""
    platform_label = platform.capitalize() if platform else ""

    # Formatear precio
    price_str = f"€{price:,.0f}" if price else "N/A"

    # Badge de vendido
    sold_html = '<span class="sold-badge">VENDIDO</span>' if show_sold else ''

    # Info adicional
    info_html = ""
    if brand:
        info_html += f'<div class="product-info">🏷️ {html_lib.escape(brand)}</div>'
    if reference:
        info_html += f'<div class="product-info">📋 {html_lib.escape(reference)}</div>'
    if location:
        info_html += f'<div class="product-info">📍 {html_lib.escape(location)}</div>'

    # Link
    link_html = f'<a href="{url}" target="_blank" class="product-link">🔗 Ver anuncio</a>' if url else ''

    return f'''
    <div class="product-card">
        <div class="product-image-container">
            {image_html}
        </div>
        {sold_html}
        <div class="product-title">{title_escaped}</div>
        <div class="product-price">{price_str}</div>
        <span class="product-platform {platform_class}">{platform_label}</span>
        {info_html}
        {link_html}
    </div>
    '''


def render_products_grid(items, show_sold=False, num_columns=4):
    """
    Renderiza un grid de productos usando st.columns de Streamlit.
    Usa CSS para forzar alineación vertical.

    Args:
        items: Lista de items a mostrar
        show_sold: Si es True, muestra badge de vendido
        num_columns: Número de columnas
    """
    if not items:
        st.info("No hay elementos para mostrar.")
        return

    # Renderizar usando st.columns nativo de Streamlit
    cols = st.columns(num_columns)
    for idx, item in enumerate(items):
        with cols[idx % num_columns]:
            render_card_simple(item, show_sold)


def render_card_simple(item, show_sold=False):
    """
    Renderiza una tarjeta de producto con el siguiente orden:
    1. Nombre del producto
    2. Precio
    3. País de venta
    4. ID number
    5. Desplegable con más información
    """
    image_url = item.get('image_url', '')
    title = item.get('specific_model') or item.get('product_name') or 'Sin nombre'
    price = item.get('listing_price') or item.get('sale_price')
    platform = item.get('platform', '')
    url = item.get('url', '')
    location = item.get('seller_location', '')
    reference = item.get('reference_number', '')
    brand = item.get('brand', '')
    listing_id = item.get('listing_id', '')
    condition = item.get('condition', '')
    year_of_production = item.get('year_of_production', '')
    case_material = item.get('case_material', '')
    dial_color = item.get('dial_color', '')
    description = item.get('description', '')
    upload_date = item.get('upload_date', '')
    generic_model = item.get('generic_model', '')
    seller_id = item.get('seller_id', '')
    snapshot_date = item.get('snapshot_date', '')
    detection_date = item.get('detection_date', '')
    days_on_sale = item.get('days_on_sale', '')

    # Obtener mejor fuente de imagen (local con fallback a remoto)
    image_source, is_local = get_best_image_source(item, platform)

    # Mostrar imagen con fallback automático - SIEMPRE usar HTML con .image-container para tamaño estandarizado
    if image_source:
        if is_local:
            # Convertir imagen local a base64 data URI para HTML
            try:
                import base64
                from pathlib import Path
                img_path = Path(image_source)
                img_data = img_path.read_bytes()
                img_base64 = base64.b64encode(img_data).decode()
                # Detectar tipo MIME
                ext = img_path.suffix.lower()
                mime_type = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                           '.png': 'image/png', '.webp': 'image/webp'}.get(ext, 'image/jpeg')
                st.markdown(
                    f'<div class="image-container"><img src="data:{mime_type};base64,{img_base64}" alt="producto" loading="lazy"></div>',
                    unsafe_allow_html=True
                )
            except Exception:
                # Fallback a URL remota si existe
                if item.get('image_url', '').startswith('http'):
                    st.markdown(
                        f'<div class="image-container"><img src="{item.get("image_url")}" alt="producto"></div>',
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(
                        '<div class="image-container"><span class="product-no-image">📷</span></div>',
                        unsafe_allow_html=True
                    )
        else:
            # URL remota - usar HTML
            st.markdown(
                f'<div class="image-container"><img src="{image_source}" alt="producto"></div>',
                unsafe_allow_html=True
            )
    else:
        st.markdown(
            '<div class="image-container"><span class="product-no-image">📷</span></div>',
            unsafe_allow_html=True
        )

    # Badge de vendido
    if show_sold:
        st.markdown('<span class="sold-badge">VENDIDO</span>', unsafe_allow_html=True)

    # 1. NOMBRE DEL PRODUCTO
    display_title = title[:50] + '...' if len(title) > 50 else title
    st.markdown(
        f'<div class="fixed-title">{display_title}</div>',
        unsafe_allow_html=True
    )

    # 2. PRECIO
    price_str = f"€{price:,.0f}" if price else "N/A"
    st.markdown(f"### {price_str}")

    # 3. PAÍS DE VENTA
    if location:
        st.caption(f"📍 {location}")
    else:
        st.caption("📍 País no disponible")

    # 4. ID NUMBER
    if listing_id:
        st.caption(f"🆔 {listing_id}")
    else:
        st.caption("🆔 ID no disponible")

    # 5. DESPLEGABLE CON MÁS INFORMACIÓN
    with st.expander("Más información"):
        # Plataforma
        if platform == "chrono24":
            st.markdown(":orange[Chrono24]")
        elif platform == "vestiaire":
            st.markdown(":green[Vestiaire]")
        elif platform == "catawiki":
            st.markdown(":orange[Catawiki]")

        # Info adicional scrapeada
        if brand:
            st.text(f"🏷️ Marca: {brand}")
        if reference:
            st.text(f"📋 Referencia: {reference}")
        if generic_model:
            st.text(f"🔍 Búsqueda: {generic_model}")
        if condition:
            st.text(f"✨ Condición: {condition}")
        if year_of_production:
            st.text(f"📅 Año: {year_of_production}")
        if case_material:
            st.text(f"⚙️ Material: {case_material}")
        if dial_color:
            st.text(f"🎨 Esfera: {dial_color}")
        if upload_date:
            st.text(f"📤 Publicación: {upload_date}")
        if snapshot_date:
            st.text(f"📸 Capturado: {snapshot_date}")
        if seller_id:
            st.text(f"👤 Vendedor ID: {seller_id}")

        # Info específica de ventas
        if show_sold:
            if detection_date:
                st.text(f"🛒 Fecha venta: {detection_date}")
            if days_on_sale:
                st.text(f"⏱️ Días en venta: {days_on_sale}")

        # Descripción
        if description:
            st.text_area("📝 Descripción", description, height=80, disabled=True)

    # 6. BOTÓN LINK AL ANUNCIO (fuera del expander)
    if url:
        st.link_button("🔗 Ver anuncio", url, use_container_width=True)

    st.divider()


def render_watch_card_native(item, show_sold=False, expanded=False):
    """
    Renderiza una tarjeta de reloj con el siguiente orden:
    1. Nombre del producto
    2. Precio
    3. País de venta
    4. ID number
    5. Desplegable con más información
    """
    image_url = item.get('image_url', '')
    title = item.get('specific_model') or item.get('product_name') or 'Sin nombre'
    price = item.get('listing_price') or item.get('sale_price')
    platform = item.get('platform', '')
    url = item.get('url', '')
    condition = item.get('condition', '')
    location = item.get('seller_location', '')
    upload_date = item.get('upload_date', '')
    reference = item.get('reference_number', '')
    brand = item.get('brand', '')
    generic_model = item.get('generic_model', '')
    year_of_production = item.get('year_of_production', '')
    case_material = item.get('case_material', '')
    dial_color = item.get('dial_color', '')
    days_on_sale = item.get('days_on_sale', '')
    listing_id = item.get('listing_id', '')
    description = item.get('description', '')
    snapshot_date = item.get('snapshot_date', '')
    detection_date = item.get('detection_date', '')
    seller_id = item.get('seller_id', '')

    # Obtener mejor fuente de imagen (local con fallback a remoto)
    image_source, is_local = get_best_image_source(item, platform)

    # Mostrar imagen con fallback automático - SIEMPRE usar HTML con .image-container para tamaño estandarizado
    if image_source:
        try:
            if is_local:
                # Convertir imagen local a base64 data URI para HTML
                import base64
                from pathlib import Path
                img_path = Path(image_source)
                img_data = img_path.read_bytes()
                img_base64 = base64.b64encode(img_data).decode()
                # Detectar tipo MIME
                ext = img_path.suffix.lower()
                mime_type = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                           '.png': 'image/png', '.webp': 'image/webp'}.get(ext, 'image/jpeg')
                st.markdown(
                    f'<div class="image-container"><img src="data:{mime_type};base64,{img_base64}" alt="producto" loading="lazy"></div>',
                    unsafe_allow_html=True
                )
                st.caption("📁 Imagen local")
            else:
                # URL remota - usar HTML
                st.markdown(
                    f'<div class="image-container"><img src="{image_source}" alt="producto"></div>',
                    unsafe_allow_html=True
                )
                st.caption("🌐 Imagen remota")
        except Exception as e:
            # Si falla la imagen local, intentar con URL remota como último recurso
            if is_local and item.get('image_url', '').startswith('http'):
                st.markdown(
                    f'<div class="image-container"><img src="{item.get("image_url")}" alt="producto"></div>',
                    unsafe_allow_html=True
                )
                st.caption("🌐 Imagen remota (local falló)")
            else:
                st.markdown(
                    '<div class="image-container"><span class="product-no-image">📷</span></div>',
                    unsafe_allow_html=True
                )
    else:
        st.markdown(
            '<div class="image-container"><span class="product-no-image">📷</span></div>',
            unsafe_allow_html=True
        )

    # Badge de vendido
    if show_sold:
        st.markdown("🔴 **VENDIDO**")

    # 1. NOMBRE DEL PRODUCTO
    display_title = title[:60] + '...' if len(title) > 60 else title
    st.markdown(f"**{display_title}**")

    # 2. PRECIO
    st.markdown(f"### {format_price(price)}")

    # 3. PAÍS DE VENTA
    if location:
        st.caption(f"📍 {location}")
    else:
        st.caption("📍 País no disponible")

    # 4. ID NUMBER
    if listing_id:
        st.caption(f"🆔 {listing_id}")
    else:
        st.caption("🆔 ID no disponible")

    # 5. DESPLEGABLE CON MÁS INFORMACIÓN
    with st.expander("Más información", expanded=expanded):
        # Plataforma
        if platform == "chrono24":
            st.markdown(":orange[Chrono24]")
        elif platform == "vestiaire":
            st.markdown(":green[Vestiaire]")
        elif platform == "catawiki":
            st.markdown(":orange[Catawiki]")

        # Info adicional scrapeada
        if brand:
            st.text(f"🏷️ Marca: {brand}")
        if reference:
            st.text(f"📋 Referencia: {reference}")
        if generic_model:
            st.text(f"🔍 Búsqueda: {generic_model}")
        if condition:
            st.text(f"✨ Condición: {condition}")
        if year_of_production:
            st.text(f"📅 Año: {year_of_production}")
        if case_material:
            st.text(f"⚙️ Material: {case_material}")
        if dial_color:
            st.text(f"🎨 Esfera: {dial_color}")
        if upload_date:
            st.text(f"📤 Publicación: {upload_date}")
        if snapshot_date:
            st.text(f"📸 Capturado: {snapshot_date}")
        if seller_id:
            st.text(f"👤 Vendedor ID: {seller_id}")

        # Info específica de ventas
        if show_sold:
            if detection_date:
                st.text(f"🛒 Fecha venta: {detection_date}")
            if days_on_sale:
                st.text(f"⏱️ Días en venta: {days_on_sale}")

        # Descripción
        if description:
            st.text_area("📝 Descripción", description, height=80, disabled=True)

    # 6. BOTÓN LINK AL ANUNCIO (fuera del expander)
    if url:
        st.link_button("🔗 Ver anuncio", url, use_container_width=True)

    st.divider()


def render_inventory_section(db, platform_filter, price_range, filters):
    """Renderiza la sección de inventario."""
    st.subheader("📦 Inventario Actual")

    # Obtener datos
    chrono_inv = db.get_latest_inventory('chrono24') if platform_filter in ['Todas', 'Chrono24'] else []
    vest_inv = db.get_latest_inventory('vestiaire') if platform_filter in ['Todas', 'Vestiaire'] else []
    catawiki_inv = db.get_latest_inventory('catawiki') if platform_filter in ['Todas', 'Catawiki'] else []

    all_items = chrono_inv + vest_inv + catawiki_inv

    if not all_items:
        st.info("No hay datos de inventario disponibles. Ejecuta el scraper primero.")
        return

    # Filtrar por precio
    filtered_items = [
        item for item in all_items
        if item.get('listing_price') is not None
        and price_range[0] <= item.get('listing_price', 0) <= price_range[1]
    ]

    # Filtrar por ID de producto (Chrono24)
    listing_id_search = filters.get('listing_id', '').strip()
    if listing_id_search:
        filtered_items = [
            item for item in filtered_items
            if listing_id_search in str(item.get('listing_id', ''))
        ]

    # Filtrar por seller ID (Vestiaire)
    seller_ids = filters.get('seller_ids', [])
    if seller_ids:
        filtered_items = [
            item for item in filtered_items
            if item.get('platform') != 'vestiaire' or item.get('seller_id', '') in seller_ids
        ]

    # Filtrar por países (multiselect)
    countries = filters.get('countries', [])
    if countries:
        filtered_items = [
            item for item in filtered_items
            if (item.get('seller_location', '') or '') in countries
        ]

    # Filtrar por condición
    if filters.get('condition') and filters['condition'] != 'Todas':
        filtered_items = [
            item for item in filtered_items
            if filters['condition'].lower() in (item.get('condition', '') or '').lower()
        ]

    # Filtrar por modelo genérico
    if filters.get('generic_model') and filters['generic_model'] != 'Todos':
        filtered_items = [
            item for item in filtered_items
            if item.get('generic_model', '') == filters['generic_model']
        ]

    # Ordenar según criterio seleccionado
    sort_option = filters.get('sort', 'Precio (mayor a menor)')
    if sort_option == 'Precio (mayor a menor)':
        filtered_items.sort(key=lambda x: x.get('listing_price', 0) or 0, reverse=True)
    elif sort_option == 'Precio (menor a mayor)':
        filtered_items.sort(key=lambda x: x.get('listing_price', 0) or 0, reverse=False)
    elif sort_option == 'Fecha publicación (reciente)':
        filtered_items.sort(key=lambda x: x.get('upload_date', '') or '', reverse=True)
    elif sort_option == 'Fecha publicación (antiguo)':
        filtered_items.sort(key=lambda x: x.get('upload_date', '') or '', reverse=False)
    elif sort_option == 'Modelo A-Z':
        filtered_items.sort(key=lambda x: (x.get('specific_model', '') or x.get('product_name', '') or '').lower())
    elif sort_option == 'Modelo Z-A':
        filtered_items.sort(key=lambda x: (x.get('specific_model', '') or x.get('product_name', '') or '').lower(), reverse=True)

    # Opciones de visualización
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.write(f"Mostrando **{len(filtered_items)}** artículos")
    with col2:
        num_columns = st.selectbox("Columnas", [2, 3, 4, 5], index=2, key="inv_cols")
    with col3:
        max_items = st.selectbox("Mostrar", [25, 50, 100, 200], index=2, key="inv_max")

    # Mostrar en grid usando HTML puro (garantiza alineación perfecta)
    render_products_grid(filtered_items[:max_items], show_sold=False, num_columns=num_columns)


def normalize_submodel(specific_model: str) -> str:
    """Normaliza el nombre del sub-modelo para agrupación."""
    if not specific_model:
        return "Sin modelo"
    return ' '.join(specific_model.strip().split())


def calculate_days_on_sale_realtime(sale: dict) -> int:
    """
    Calcula días de venta en tiempo real desde los datos disponibles.

    Prioridad:
    1. Si existe upload_date: detection_date - upload_date
    2. Si no: retornar 0
    """
    from datetime import datetime

    try:
        detection_date_str = sale.get('detection_date')
        upload_date_str = sale.get('upload_date')

        if not detection_date_str:
            return 0

        detection_date = datetime.strptime(detection_date_str, '%Y-%m-%d').date()

        if upload_date_str:
            upload_date = datetime.strptime(upload_date_str, '%Y-%m-%d').date()
            days = (detection_date - upload_date).days
            return max(0, days)  # No permitir días negativos

        # Si no hay upload_date, retornar 0
        return 0

    except Exception:
        return 0


def render_sales_summary_metrics(df, platform_choice):
    """Renderiza métricas resumen de ventas filtradas por plataforma."""
    # Filtrar por plataforma si no es "Todas"
    if platform_choice != "Todas":
        platform_key = platform_choice.lower()  # "chrono24" o "vestiaire"
        df_filtered = df[df['platform'] == platform_key]
    else:
        df_filtered = df

    total_sales = len(df_filtered)
    avg_price = df_filtered['sale_price'].dropna().mean() if 'sale_price' in df_filtered.columns and not df_filtered.empty else 0
    unique_models = df_filtered['submodel'].nunique() if 'submodel' in df_filtered.columns else 0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Ventas", f"{total_sales:,}")
    with col2:
        st.metric("Precio Medio", f"{avg_price:,.0f}" if avg_price else "N/A")
    with col3:
        st.metric("Sub-modelos", f"{unique_models}")


def render_sales_comparison_charts(df, platform_choice):
    """Renderiza gráficos comparativos de sub-modelos del modelo genérico actual."""
    # Filtrar por plataforma si no es "Todas"
    if platform_choice != "Todas":
        platform_key = platform_choice.lower()  # "chrono24" o "vestiaire"
        df_filtered = df[df['platform'] == platform_key]
    else:
        df_filtered = df

    if df_filtered.empty or 'submodel' not in df_filtered.columns:
        st.info("No hay datos para mostrar gráficos con esta plataforma.")
        return

    # Top 10 sub-modelos por cantidad de ventas (limitado para legibilidad)
    top_models = df_filtered['submodel'].value_counts().head(10)
    top_model_names = top_models.index.tolist()
    df_top = df_filtered[df_filtered['submodel'].isin(top_model_names)].copy()

    if df_top.empty:
        return

    col1, col2 = st.columns(2)

    with col1:
        # Barras horizontales: ventas por sub-modelo
        counts = df_top.groupby(['submodel', 'platform']).size().reset_index(name='ventas')
        # Ordenar por total de ventas
        order = counts.groupby('submodel')['ventas'].sum().sort_values(ascending=True).index.tolist()

        fig = px.bar(
            counts,
            y='submodel',
            x='ventas',
            color='platform',
            orientation='h',
            title="Ventas por Sub-modelo",
            labels={'submodel': '', 'ventas': 'Ventas', 'platform': 'Plataforma'},
            color_discrete_map={'chrono24': '#ff6b35', 'vestiaire': '#00a86b', 'catawiki': '#f5a623'},
            category_orders={'submodel': order}
        )
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font_color='white',
            height=max(400, len(top_model_names) * 35),
            yaxis_tickfont_size=11,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # Box plot: distribución de precios por sub-modelo
        df_prices = df_top[df_top['sale_price'].notna() & (df_top['sale_price'] > 0)].copy()
        if not df_prices.empty:
            fig = px.box(
                df_prices,
                y='submodel',
                x='sale_price',
                orientation='h',
                title="Distribución de Precios por Sub-modelo",
                labels={'submodel': '', 'sale_price': 'Precio'},
                category_orders={'submodel': order}
            )
            fig.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font_color='white',
                height=max(400, len(top_model_names) * 35),
                yaxis_tickfont_size=11,
                showlegend=False
            )
            fig.update_traces(marker_color='#00d9ff')
            st.plotly_chart(fig, use_container_width=True)


def render_sales_by_submodel(df, sales_list, platform_choice):
    """Renderiza catálogo de ventas agrupado por sub-modelo con fotos y detalles."""
    # Filtrar por plataforma si no es "Todas"
    if platform_choice != "Todas":
        platform_key = platform_choice.lower()  # "chrono24" o "vestiaire"
        df_filtered = df[df['platform'] == platform_key]
        sales_filtered = [s for s in sales_list if s.get('platform') == platform_key]
    else:
        df_filtered = df
        sales_filtered = sales_list

    if df_filtered.empty or 'submodel' not in df_filtered.columns:
        st.info("No hay sub-modelos para mostrar con esta plataforma.")
        return

    st.divider()
    st.subheader("Detalle por Sub-modelo")

    # Agrupar y ordenar por número de ventas (descendente)
    model_counts = df_filtered['submodel'].value_counts()

    # Crear lookup de sales por submodel
    sales_by_model = {}
    for sale in sales_filtered:
        sm = normalize_submodel(sale.get('specific_model', ''))
        sales_by_model.setdefault(sm, []).append(sale)

    for submodel in model_counts.index:
        group_sales = sales_by_model.get(submodel, [])
        if not group_sales:
            continue

        count = len(group_sales)
        prices = [s.get('sale_price') or 0 for s in group_sales if s.get('sale_price')]
        avg_price = sum(prices) / len(prices) if prices else 0
        min_price = min(prices) if prices else 0
        max_price = max(prices) if prices else 0

        # Calcular días medios en venta
        days_list = [s.get('days_on_sale') for s in group_sales if s.get('days_on_sale') is not None]
        avg_days = sum(days_list) / len(days_list) if days_list else None

        # Título del expander
        title = f"{submodel} ({count} {'venta' if count == 1 else 'ventas'}) - Media: {avg_price:,.0f}"

        with st.expander(title, expanded=False):
            # Métricas del grupo
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.metric("Rango de Precios", f"{min_price:,.0f} - {max_price:,.0f}")
            with m2:
                st.metric("Precio Medio", f"{avg_price:,.0f}")
            with m3:
                st.metric("Total Ventas", f"{count}")
            with m4:
                if avg_days is not None:
                    st.metric("Dias Medio en Venta", f"{avg_days:.0f} dias")
                else:
                    st.metric("Dias Medio en Venta", "N/A")

            # Tabla con fotos integradas
            table_data = []
            for sale in group_sales:
                # Obtener mejor fuente de imagen
                image_source, is_local = get_best_image_source(sale, sale.get('platform', ''))

                # Calcular días de venta en tiempo real
                days_on_sale_calculated = calculate_days_on_sale_realtime(sale)

                url = sale.get('url', '')

                table_data.append({
                    'Foto': image_source or '',  # URL o path local de imagen
                    'Precio': sale.get('sale_price') or 0,
                    'Fecha': sale.get('detection_date', '') or '',
                    'Dias': days_on_sale_calculated,
                    'Pais': sale.get('seller_location', '') or '',
                    'ID': sale.get('listing_id', '') or '',
                    'Material Caja': sale.get('case_material', '') or '',
                    'Material Pulsera': sale.get('bracelet_material', '') or '',
                    'Link': url,
                })

            if table_data:
                df_table = pd.DataFrame(table_data)

                # Ordenar por fecha de venta más reciente
                df_table = df_table.sort_values('Fecha', ascending=False)

                # Configuración de columnas
                st.dataframe(
                    df_table,
                    column_config={
                        "Foto": st.column_config.ImageColumn(
                            "Foto",
                            help="Imagen del reloj",
                            width="small"  # Foto pequeña
                        ),
                        "Precio": st.column_config.NumberColumn(
                            "Precio",
                            format="%,.0f €"
                        ),
                        "Fecha": st.column_config.TextColumn(
                            "Fecha Venta",
                            width="medium"
                        ),
                        "Dias": st.column_config.NumberColumn(
                            "Días",
                            help="Días en venta antes de ser vendido",
                            width="small"
                        ),
                        "Pais": st.column_config.TextColumn(
                            "País",
                            width="small"
                        ),
                        "ID": st.column_config.TextColumn(
                            "ID Producto",
                            width="medium"
                        ),
                        "Material Caja": st.column_config.TextColumn(
                            "Material Caja",
                            width="medium"
                        ),
                        "Material Pulsera": st.column_config.TextColumn(
                            "Material Pulsera",
                            width="medium"
                        ),
                        "Link": st.column_config.LinkColumn(
                            "Link",
                            display_text="Abrir",
                            width="small"
                        ),
                    },
                    hide_index=True,
                    use_container_width=True
                )


def render_generic_model_section(generic_model, df_generic, sales_generic, platform_choice):
    """Renderiza sección completa de un modelo genérico (expander nivel 1)."""
    total_sales = len(df_generic)
    avg_price = df_generic['sale_price'].dropna().mean() if not df_generic.empty else 0

    # Título del expander nivel 1
    title = f"{generic_model.title()} ({total_sales} ventas) - Media: {avg_price:,.0f}"

    with st.expander(title, expanded=True):  # Expanded por defecto
        # GRÁFICOS COMPARATIVOS (solo sub-modelos de este genérico)
        render_sales_comparison_charts(df_generic, platform_choice)

        # SUB-MODELOS (expanders nivel 2)
        render_sales_by_submodel(df_generic, sales_generic, platform_choice)


def render_sales_section(db, platform_filter, date_range, filters):
    """Renderiza la sección de ventas con jerarquía: modelo genérico → sub-modelos."""
    st.subheader("Ventas Detectadas")

    # Determinar plataforma
    platform = None
    if platform_filter == 'Chrono24':
        platform = 'chrono24'
    elif platform_filter == 'Vestiaire':
        platform = 'vestiaire'
    elif platform_filter == 'Catawiki':
        platform = 'catawiki'

    # Obtener ventas
    sales = db.get_sales_by_date_range(date_range[0], date_range[1], platform)

    if not sales:
        st.info("No se han detectado ventas en el periodo seleccionado.")
        return

    # Filtrar por ID de producto (Chrono24)
    listing_id_search = filters.get('listing_id', '').strip()
    if listing_id_search:
        sales = [
            sale for sale in sales
            if listing_id_search in str(sale.get('listing_id', ''))
        ]

    # Filtrar por seller ID (Vestiaire)
    seller_ids = filters.get('seller_ids', [])
    if seller_ids:
        sales = [
            sale for sale in sales
            if sale.get('platform') != 'vestiaire' or sale.get('seller_id', '') in seller_ids
        ]

    # Filtrar por países (multiselect)
    countries = filters.get('countries', [])
    if countries:
        sales = [
            sale for sale in sales
            if (sale.get('seller_location', '') or '') in countries
        ]

    # Filtrar por modelo genérico
    if filters.get('generic_model') and filters['generic_model'] != 'Todos':
        sales = [
            sale for sale in sales
            if sale.get('generic_model', '') == filters['generic_model']
        ]

    if not sales:
        st.info("No se encontraron ventas con los filtros seleccionados.")
        return

    # Crear DataFrame con columna normalizada de sub-modelo
    df = pd.DataFrame(sales)
    df['submodel'] = df['specific_model'].apply(normalize_submodel)

    # SELECTOR DE PLATAFORMA (para filtrar gráficos y catálogos)
    platform_choice = st.selectbox(
        "Filtrar gráficos por plataforma:",
        options=["Todas", "Chrono24", "Vestiaire"],
        index=0,
        key="sales_platform_filter"
    )

    # Métricas resumen (filtradas por plataforma)
    render_sales_summary_metrics(df, platform_choice)

    st.divider()

    # Importar config para obtener CHRONO24_MODELS
    from config import CHRONO24_MODELS

    # ITERAR POR MODELO GENÉRICO (nivel 1)
    for generic_model in CHRONO24_MODELS:
        # Filtrar ventas de este modelo genérico (case-insensitive)
        # Manejar valores None en generic_model
        df_generic = df[df['generic_model'].fillna('').str.lower() == generic_model.lower()]

        if df_generic.empty:
            continue

        # Filtrar sales_list del mismo modelo (manejar None)
        sales_generic = [
            s for s in sales
            if (s.get('generic_model') or '').lower() == generic_model.lower()
        ]

        # RENDERIZAR SECCIÓN DE MODELO GENÉRICO (con expander nivel 1)
        render_generic_model_section(generic_model, df_generic, sales_generic, platform_choice)


def render_statistics(db):
    """Renderiza estadísticas generales."""
    stats = db.get_statistics()

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{stats.get('total_inventory_records', 0):,}</div>
            <div class="stat-label">Registros de Inventario</div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="stat-card" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
            <div class="stat-number">{stats.get('total_sales_detected', 0):,}</div>
            <div class="stat-label">Ventas Detectadas</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        chrono_sales = stats.get('sales_by_platform', {}).get('chrono24', 0)
        st.markdown(f"""
        <div class="stat-card" style="background: linear-gradient(135deg, #ff6b35 0%, #f7931e 100%);">
            <div class="stat-number">{chrono_sales:,}</div>
            <div class="stat-label">Ventas Chrono24</div>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        vest_sales = stats.get('sales_by_platform', {}).get('vestiaire', 0)
        st.markdown(f"""
        <div class="stat-card" style="background: linear-gradient(135deg, #00a86b 0%, #00d9a5 100%);">
            <div class="stat-number">{vest_sales:,}</div>
            <div class="stat-label">Ventas Vestiaire</div>
        </div>
        """, unsafe_allow_html=True)

    with col5:
        catawiki_sales = stats.get('sales_by_platform', {}).get('catawiki', 0)
        st.markdown(f"""
        <div class="stat-card" style="background: linear-gradient(135deg, #f5a623 0%, #f7c948 100%);">
            <div class="stat-number">{catawiki_sales:,}</div>
            <div class="stat-label">Ventas Catawiki</div>
        </div>
        """, unsafe_allow_html=True)


def render_charts(db, date_range):
    """Renderiza gráficos de análisis."""
    st.subheader("📊 Análisis")

    # Obtener ventas para el período
    sales = db.get_sales_by_date_range(date_range[0], date_range[1])

    if not sales:
        st.info("No hay datos suficientes para generar gráficos.")
        return

    df = pd.DataFrame(sales)

    col1, col2 = st.columns(2)

    with col1:
        # Ventas por plataforma
        if 'platform' in df.columns:
            platform_counts = df['platform'].value_counts()
            fig = px.pie(
                values=platform_counts.values,
                names=platform_counts.index,
                title="Ventas por Plataforma",
                color_discrete_map={'chrono24': '#ff6b35', 'vestiaire': '#00a86b', 'catawiki': '#f5a623'}
            )
            fig.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font_color='white'
            )
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        # Distribución de precios
        if 'sale_price' in df.columns:
            df_prices = df[df['sale_price'].notna()]
            if not df_prices.empty:
                fig = px.histogram(
                    df_prices,
                    x='sale_price',
                    nbins=20,
                    title="Distribución de Precios de Venta",
                    labels={'sale_price': 'Precio (€)', 'count': 'Cantidad'}
                )
                fig.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font_color='white'
                )
                fig.update_traces(marker_color='#00d9ff')
                st.plotly_chart(fig, use_container_width=True)

    # Ventas por día
    if 'detection_date' in df.columns:
        df['detection_date'] = pd.to_datetime(df['detection_date'])
        daily_sales = df.groupby('detection_date').size().reset_index(name='ventas')

        fig = px.line(
            daily_sales,
            x='detection_date',
            y='ventas',
            title="Ventas Diarias Detectadas",
            labels={'detection_date': 'Fecha', 'ventas': 'Número de Ventas'}
        )
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font_color='white'
        )
        fig.update_traces(line_color='#e94560', line_width=3)
        st.plotly_chart(fig, use_container_width=True)


def render_data_table(db, platform_filter):
    """Renderiza tabla de datos exportable."""
    st.subheader("📋 Tabla de Datos Completa")

    tab1, tab2 = st.tabs(["📦 Inventario", "💰 Ventas"])

    with tab1:
        chrono_inv = db.get_latest_inventory('chrono24') if platform_filter in ['Todas', 'Chrono24'] else []
        vest_inv = db.get_latest_inventory('vestiaire') if platform_filter in ['Todas', 'Vestiaire'] else []
        catawiki_inv = db.get_latest_inventory('catawiki') if platform_filter in ['Todas', 'Catawiki'] else []
        all_items = chrono_inv + vest_inv + catawiki_inv

        if all_items:
            df = pd.DataFrame(all_items)

            # Todas las columnas disponibles ordenadas
            all_display_cols = [
                'listing_id', 'platform', 'generic_model', 'specific_model', 'brand',
                'reference_number', 'listing_price', 'currency', 'condition',
                'year_of_production', 'case_material', 'dial_color',
                'seller_location', 'upload_date', 'snapshot_date',
                'description', 'image_url', 'url'
            ]
            display_cols = [c for c in all_display_cols if c in df.columns]

            # Selector de columnas a mostrar
            st.write("**Selecciona las columnas a mostrar:**")
            col_selection = st.multiselect(
                "Columnas",
                display_cols,
                default=['platform', 'specific_model', 'reference_number', 'listing_price',
                        'condition', 'seller_location', 'upload_date'],
                key='inv_cols_select',
                label_visibility="collapsed"
            )

            if col_selection:
                # Renombrar columnas para mejor legibilidad
                col_names = {
                    'listing_id': 'ID',
                    'platform': 'Plataforma',
                    'generic_model': 'Búsqueda',
                    'specific_model': 'Modelo',
                    'brand': 'Marca',
                    'reference_number': 'Referencia',
                    'listing_price': 'Precio (€)',
                    'currency': 'Moneda',
                    'condition': 'Condición',
                    'year_of_production': 'Año',
                    'case_material': 'Material Caja',
                    'dial_color': 'Color Esfera',
                    'seller_location': 'País',
                    'upload_date': 'Fecha Publicación',
                    'snapshot_date': 'Fecha Captura',
                    'description': 'Descripción',
                    'image_url': 'URL Imagen',
                    'url': 'URL Anuncio'
                }

                df_display = df[col_selection].copy()
                df_display.columns = [col_names.get(c, c) for c in col_selection]

                st.dataframe(df_display, use_container_width=True, height=500)

                st.write(f"**Total:** {len(df):,} artículos")

            # Botón de descarga (CSV completo)
            csv = df.to_csv(index=False)
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    "📥 Descargar CSV (todas las columnas)",
                    csv,
                    f"inventario_{date.today().isoformat()}.csv",
                    "text/csv",
                    key='download-inventory-full'
                )
            with col2:
                if col_selection:
                    csv_filtered = df[col_selection].to_csv(index=False)
                    st.download_button(
                        "📥 Descargar CSV (columnas seleccionadas)",
                        csv_filtered,
                        f"inventario_filtrado_{date.today().isoformat()}.csv",
                        "text/csv",
                        key='download-inventory-filtered'
                    )
        else:
            st.info("No hay datos de inventario.")

    with tab2:
        today = date.today()
        month_ago = today - timedelta(days=30)

        platform = None
        if platform_filter == 'Chrono24':
            platform = 'chrono24'
        elif platform_filter == 'Vestiaire':
            platform = 'vestiaire'
        elif platform_filter == 'Catawiki':
            platform = 'catawiki'

        sales = db.get_sales_by_date_range(month_ago, today, platform)

        if sales:
            df = pd.DataFrame(sales)

            # Todas las columnas disponibles para ventas
            all_display_cols = [
                'listing_id', 'platform', 'detection_date', 'generic_model', 'specific_model',
                'brand', 'reference_number', 'sale_price', 'currency', 'price_is_estimated',
                'days_on_sale', 'condition', 'year_of_production', 'case_material', 'dial_color',
                'seller_location', 'upload_date', 'description', 'image_url', 'url'
            ]
            display_cols = [c for c in all_display_cols if c in df.columns]

            # Selector de columnas
            st.write("**Selecciona las columnas a mostrar:**")
            col_selection = st.multiselect(
                "Columnas",
                display_cols,
                default=['platform', 'detection_date', 'specific_model', 'sale_price',
                        'days_on_sale', 'seller_location'],
                key='sales_cols_select',
                label_visibility="collapsed"
            )

            if col_selection:
                # Renombrar columnas
                col_names = {
                    'listing_id': 'ID',
                    'platform': 'Plataforma',
                    'detection_date': 'Fecha Venta',
                    'generic_model': 'Búsqueda',
                    'specific_model': 'Modelo',
                    'brand': 'Marca',
                    'reference_number': 'Referencia',
                    'sale_price': 'Precio Venta (€)',
                    'currency': 'Moneda',
                    'price_is_estimated': 'Precio Estimado',
                    'days_on_sale': 'Días en Venta',
                    'condition': 'Condición',
                    'year_of_production': 'Año',
                    'case_material': 'Material Caja',
                    'dial_color': 'Color Esfera',
                    'seller_location': 'País',
                    'upload_date': 'Fecha Publicación',
                    'description': 'Descripción',
                    'image_url': 'URL Imagen',
                    'url': 'URL Anuncio'
                }

                df_display = df[col_selection].copy()
                df_display.columns = [col_names.get(c, c) for c in col_selection]

                st.dataframe(df_display, use_container_width=True, height=500)

                st.write(f"**Total:** {len(df):,} ventas detectadas")

            # Botón de descarga
            csv = df.to_csv(index=False)
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    "📥 Descargar CSV (todas las columnas)",
                    csv,
                    f"ventas_{date.today().isoformat()}.csv",
                    "text/csv",
                    key='download-sales-full'
                )
            with col2:
                if col_selection:
                    csv_filtered = df[col_selection].to_csv(index=False)
                    st.download_button(
                        "📥 Descargar CSV (columnas seleccionadas)",
                        csv_filtered,
                        f"ventas_filtrado_{date.today().isoformat()}.csv",
                        "text/csv",
                        key='download-sales-filtered'
                    )
        else:
            st.info("No hay ventas en el último mes.")


def get_unique_values(db, field, platform_filter):
    """Obtiene valores únicos de un campo para los filtros."""
    chrono_inv = db.get_latest_inventory('chrono24') if platform_filter in ['Todas', 'Chrono24'] else []
    vest_inv = db.get_latest_inventory('vestiaire') if platform_filter in ['Todas', 'Vestiaire'] else []
    catawiki_inv = db.get_latest_inventory('catawiki') if platform_filter in ['Todas', 'Catawiki'] else []
    all_items = chrono_inv + vest_inv + catawiki_inv

    values = set()
    for item in all_items:
        val = item.get(field, '')
        if val:
            values.add(val)
    return sorted(list(values))


def main():
    """Función principal del dashboard."""
    st.title("⌚ Dashboard de Relojes")
    st.markdown("Visualización de inventario y ventas detectadas")

    # Inicializar base de datos
    try:
        db = get_db()
    except Exception as e:
        st.error(f"Error conectando a la base de datos: {e}")
        st.info("Asegúrate de haber inicializado la base de datos con: python main.py --init")
        return

    # Sidebar con filtros
    with st.sidebar:
        st.header("🔍 Filtros")

        # 1. PLATAFORMA
        platform_filter = st.selectbox(
            "📱 Plataforma",
            ["Todas", "Chrono24", "Vestiaire", "Catawiki"]
        )

        st.divider()

        # 2. SELECTOR DE MODELO + FILTROS ESPECÍFICOS POR PLATAFORMA
        st.subheader("🔍 Modelo y Búsqueda")

        # Obtener modelos genéricos disponibles en la base de datos
        generic_models = get_unique_values(db, 'generic_model', platform_filter)

        # Selector de modelo (dropdown)
        model_options = ['Todos'] + generic_models
        generic_model_filter = st.selectbox("Modelo buscado", model_options)

        # Filtros específicos según plataforma seleccionada
        seller_id_filter = []
        listing_id_search = ""

        if platform_filter in ['Todas', 'Vestiaire']:
            # Filtro de Seller ID para Vestiaire
            valid_sellers = [s for s in VESTIAIRE_SELLER_IDS if s and not s.startswith('seller_id_')]
            if valid_sellers:
                seller_id_filter = st.multiselect(
                    "👤 ID Vendedor (Vestiaire)",
                    valid_sellers,
                    placeholder="Selecciona vendedores..."
                )

        if platform_filter in ['Todas', 'Chrono24']:
            # Buscador por ID de producto para Chrono24
            listing_id_search = st.text_input(
                "🆔 Buscar por ID (Chrono24)",
                placeholder="Ej: 12345678"
            )

        st.divider()

        # 3. RANGO DE PRECIO
        st.subheader("💰 Rango de Precio")
        price_min = st.number_input("Mínimo (€)", min_value=0, value=0, step=100)
        price_max = st.number_input("Máximo (€)", min_value=0, value=100000, step=1000)
        price_range = (price_min, price_max)

        st.divider()

        # 4. PAÍSES (MULTISELECT)
        st.subheader("📍 País del Vendedor")
        countries = get_unique_values(db, 'seller_location', platform_filter)
        country_filter = st.multiselect(
            "Países",
            countries,
            placeholder="Todos los países",
            label_visibility="collapsed"
        )

        st.divider()

        # 5. CONDICIÓN
        st.subheader("✨ Condición")
        condition_options = ['Todas', 'Nuevo', 'Muy bueno', 'Bueno', 'Usado']
        condition_filter = st.selectbox("Condición", condition_options, label_visibility="collapsed")

        st.divider()

        # 6. ORDENAR POR
        st.subheader("📊 Ordenar por")
        sort_options = [
            'Precio (mayor a menor)',
            'Precio (menor a mayor)',
            'Fecha publicación (reciente)',
            'Fecha publicación (antiguo)',
            'Modelo A-Z',
            'Modelo Z-A'
        ]
        sort_by = st.selectbox("Criterio", sort_options, label_visibility="collapsed")

        st.divider()

        # 7. PERÍODO DE VENTAS
        st.subheader("📅 Período de Ventas")
        today = date.today()
        date_start = st.date_input("Desde", date(2026, 1, 1))
        date_end = st.date_input("Hasta", today)
        date_range = (date_start, date_end)

        st.divider()

        # Info de última ejecución
        st.subheader("ℹ️ Información")
        stats = db.get_statistics()
        last_run = stats.get('last_run')
        if last_run:
            st.caption(f"Última ejecución: {last_run.get('run_date', 'N/A')}")
            st.caption(f"Estado: {last_run.get('status', 'N/A')}")
        st.caption(f"Total artículos: {stats.get('total_inventory_records', 0):,}")
        st.caption(f"Ventas detectadas: {stats.get('total_sales_detected', 0):,}")

    # Construir diccionario de filtros
    filters = {
        'countries': country_filter,  # Ahora es una lista (multiselect)
        'condition': condition_filter,
        'generic_model': generic_model_filter,
        'sort': sort_by,
        'seller_ids': seller_id_filter,  # Lista de seller IDs para Vestiaire
        'listing_id': listing_id_search,  # ID de producto para Chrono24
    }

    # Estadísticas generales
    render_statistics(db)

    st.divider()

    # Tabs principales
    tab1, tab2, tab3, tab4 = st.tabs(["📦 Inventario", "💰 Ventas", "📊 Análisis", "📋 Datos"])

    with tab1:
        render_inventory_section(db, platform_filter, price_range, filters)

    with tab2:
        render_sales_section(db, platform_filter, date_range, filters)

    with tab3:
        render_charts(db, date_range)

    with tab4:
        render_data_table(db, platform_filter)


if __name__ == "__main__":
    main()
