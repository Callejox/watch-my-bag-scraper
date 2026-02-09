#!/usr/bin/env python3
"""
Validación de URLs de Ventas Detectadas

Verifica si productos marcados como "vendidos" siguen activos en la web.
Genera reporte CSV con clasificación de cada venta:
- FALSE_POSITIVE: Producto sigue a la venta (link activo)
- TRUE_POSITIVE: Producto realmente vendido (404 o página muestra vendido)
- INCONCLUSIVE: No se pudo determinar (Cloudflare, timeout, etc.)

Uso:
    python validate_sales_urls.py
    # Output: validation_results.csv

Autor: Generado con Claude
"""

import requests
import time
import random
import csv
from datetime import date, timedelta
from database.db_manager import DatabaseManager
from config import USER_AGENTS


def validate_sale_url(url: str) -> tuple[str, str]:
    """
    Verifica si una URL de venta sigue activa.

    Args:
        url: URL del producto a verificar

    Returns:
        tuple[str, str]: (status, classification)
        - ('200_ACTIVE', 'FALSE_POSITIVE'): Producto sigue a la venta
        - ('200_SOLD', 'TRUE_POSITIVE'): Página muestra vendido
        - ('404', 'TRUE_POSITIVE'): Página no encontrada
        - ('403', 'INCONCLUSIVE'): Cloudflare bloqueado
        - ('TIMEOUT', 'INCONCLUSIVE'): Request timeout
        - ('ERROR_*', 'INCONCLUSIVE'): Otro error
    """
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Cache-Control': 'no-cache',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
    }

    try:
        # HEAD request para status rápido
        response = requests.head(url, headers=headers, timeout=10, allow_redirects=True)
        status_code = response.status_code

        # Status codes definitivos
        if status_code in [404, 410]:
            return (str(status_code), 'TRUE_POSITIVE')

        if status_code == 403:
            return ('403', 'INCONCLUSIVE')

        if status_code == 200:
            # GET request para verificar contenido HTML
            response = requests.get(url, headers=headers, timeout=15)
            html = response.text.lower()

            # Indicadores de producto activo
            active_indicators = [
                'añadir a la cesta',
                'add to cart',
                'ver detalles',
                'view details',
                'precio:',
                'price:',
                'comprar ahora',
                'buy now',
                'añadir a favoritos',
                'add to wishlist',
            ]

            # Indicadores de producto vendido
            sold_indicators = [
                'vendido',
                'sold',
                'no disponible',
                'not available',
                'agotado',
                'out of stock',
                'no longer available',
                'ya no está disponible',
                'este artículo ya no está a la venta',
                'this item is no longer for sale',
            ]

            active_found = any(indicator in html for indicator in active_indicators)
            sold_found = any(indicator in html for indicator in sold_indicators)

            if active_found and not sold_found:
                return ('200_ACTIVE', 'FALSE_POSITIVE')
            elif sold_found:
                return ('200_SOLD', 'TRUE_POSITIVE')
            else:
                return ('200_UNKNOWN', 'INCONCLUSIVE')

        return (str(status_code), 'INCONCLUSIVE')

    except requests.exceptions.Timeout:
        return ('TIMEOUT', 'INCONCLUSIVE')
    except requests.exceptions.ConnectionError:
        return ('ERROR_ConnectionError', 'INCONCLUSIVE')
    except requests.exceptions.RequestException as e:
        return (f'ERROR_{type(e).__name__}', 'INCONCLUSIVE')
    except Exception as e:
        return (f'ERROR_{type(e).__name__}', 'INCONCLUSIVE')


def main():
    print("=" * 70)
    print("VALIDACIÓN DE URLs DE VENTAS DETECTADAS")
    print("=" * 70)
    print()

    db = DatabaseManager()

    # Query últimas ventas (30 días)
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT platform, listing_id, url, detection_date, sale_price
            FROM detected_sales
            WHERE platform = 'chrono24'
              AND detection_date >= date('now', '-30 days')
            ORDER BY detection_date DESC
        """)
        sales = [dict(row) for row in cursor.fetchall()]

    if not sales:
        print("[!] No se encontraron ventas de Chrono24 en los últimos 30 días.")
        return

    print(f"[*] Ventas a validar: {len(sales)}")
    print(f"[*] Tiempo estimado: ~{len(sales)} segundos (~{len(sales)/60:.1f} minutos)")
    print()

    results = []
    false_positive_count = 0
    true_positive_count = 0
    inconclusive_count = 0

    start_time = time.time()

    for i, sale in enumerate(sales, 1):
        url = sale['url']
        listing_id = sale['listing_id']

        # Validar URL
        status, classification = validate_sale_url(url)

        results.append({
            'listing_id': listing_id,
            'url': url,
            'status': status,
            'classification': classification,
            'detection_date': sale['detection_date'],
            'sale_price': sale['sale_price'],
        })

        # Actualizar contadores
        if classification == 'FALSE_POSITIVE':
            false_positive_count += 1
            marker = '[!]'
        elif classification == 'TRUE_POSITIVE':
            true_positive_count += 1
            marker = '[OK]'
        else:
            inconclusive_count += 1
            marker = '[?]'

        # Progreso
        print(f"{marker} [{i}/{len(sales)}] {listing_id}: {classification} ({status})")

        # Rate limiting: 0.5-1s entre requests
        if i < len(sales):  # No esperar después del último
            time.sleep(random.uniform(0.5, 1.0))

    elapsed_time = time.time() - start_time

    # Guardar resultados a CSV
    output_file = 'validation_results.csv'
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        if results:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)

    # Resumen
    print()
    print("=" * 70)
    print("RESUMEN DE VALIDACIÓN")
    print("=" * 70)
    print(f"Total validadas: {len(results)}")
    print()
    print(f"[!] Falsos positivos (activos): {false_positive_count} ({false_positive_count/len(results)*100:.1f}%)")
    print(f"[OK] Verdaderos positivos: {true_positive_count} ({true_positive_count/len(results)*100:.1f}%)")
    print(f"[?] Inconclusos (Cloudflare/timeout): {inconclusive_count} ({inconclusive_count/len(results)*100:.1f}%)")
    print()
    print(f"Tiempo total: {elapsed_time:.1f}s ({elapsed_time/60:.1f} minutos)")
    print(f"\nResultados guardados en: {output_file}")
    print("=" * 70)
    print()

    # Recomendaciones
    if false_positive_count > 0:
        print("RECOMENDACIÓN:")
        print(f"  Se detectaron {false_positive_count} falsos positivos.")
        print(f"  Ejecuta cleanup_false_positives.py para eliminarlos de la BD.")
        print()
        print("  Comando:")
        print(f"    py cleanup_false_positives.py --input {output_file}")
        print(f"    py cleanup_false_positives.py --input {output_file} --execute")
        print()

    if inconclusive_count > len(results) * 0.3:  # Más de 30% inconclusos
        print("ADVERTENCIA:")
        print(f"  {inconclusive_count/len(results)*100:.1f}% de validaciones fueron inconclusas.")
        print("  Esto puede deberse a:")
        print("    - Bloqueo de Cloudflare (status 403)")
        print("    - Timeouts de red")
        print("    - Páginas dinámicas que requieren JavaScript")
        print()
        print("  Revisa manualmente casos INCONCLUSIVE en validation_results.csv")
        print()


if __name__ == "__main__":
    main()
