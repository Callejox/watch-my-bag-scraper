"""
Script de limpieza de falsos positivos de Catawiki del 2026-01-29.

Elimina items marcados como vendidos cuando el scraper falló (redirección a comics).
"""

import sqlite3
from datetime import date

def cleanup_catawiki_false_positives():
    """Elimina falsos positivos de Catawiki del 2026-01-29."""

    conn = sqlite3.connect('data/inventory.db')
    cursor = conn.cursor()

    print('\n' + '='*70)
    print('LIMPIEZA DE FALSOS POSITIVOS DE CATAWIKI (2026-01-29)')
    print('='*70)

    # Estos son los 24 items marcados como vendidos cuando el scraper falló
    cursor.execute("""
        SELECT platform, listing_id, detection_date, specific_model, sale_price
        FROM detected_sales
        WHERE platform = 'catawiki'
        AND detection_date = '2026-01-29'
        ORDER BY listing_id
    """)

    false_positives = cursor.fetchall()

    if not false_positives:
        print('\n[OK] No se encontraron falsos positivos de Catawiki.')
        conn.close()
        return

    print(f'\n[!] Falsos positivos encontrados: {len(false_positives)}')
    print('\nEstos productos fueron marcados como "vendidos" cuando el scraper')
    print('de Catawiki falló (redirigió a categoría de comics).')
    print('\nDetalle:')
    print(f"{'Listing ID':<15} {'Modelo':<40} {'Precio'}")
    print('-' * 70)

    for platform, listing_id, detection_date, model, price in false_positives[:20]:
        print(f"{listing_id:<15} {(model or 'N/A')[:38]:<40} {price}")

    if len(false_positives) > 20:
        print(f"... y {len(false_positives) - 20} más")

    # Confirmar antes de eliminar
    print(f'\n¿Desea eliminar estos {len(false_positives)} falsos positivos? (s/n): ', end='')
    confirmation = input().strip().lower()

    if confirmation != 's':
        print('\n[X] Operacion cancelada.')
        conn.close()
        return

    # Eliminar de detected_sales
    print('\nEliminando falsos positivos...')
    cursor.execute("""
        DELETE FROM detected_sales
        WHERE platform = 'catawiki'
        AND detection_date = '2026-01-29'
    """)

    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()

    print(f'\n[OK] {deleted_count} falsos positivos eliminados correctamente.')
    print('\nEstos productos siguen disponibles en Catawiki, no han sido vendidos.')
    print('='*70 + '\n')


if __name__ == '__main__':
    cleanup_catawiki_false_positives()
