"""
Script de limpieza de falsos positivos en detected_sales.

Elimina items que fueron marcados como vendidos pero que reaparecieron
en el inventario en la misma fecha o fechas posteriores.

Esto ocurre cuando el scraper falla y retorna 0 items, causando que
el sistema marque incorrectamente TODO el inventario como vendido.
"""

import sqlite3
from datetime import date

def cleanup_false_positives():
    """Elimina falsos positivos de detected_sales."""

    conn = sqlite3.connect('data/inventory.db')
    cursor = conn.cursor()

    print('\n' + '='*70)
    print('LIMPIEZA DE FALSOS POSITIVOS')
    print('='*70)

    # Encontrar items en ambas tablas (falsos positivos)
    cursor.execute("""
        SELECT DISTINCT s.platform, s.listing_id, s.detection_date
        FROM detected_sales s
        WHERE EXISTS (
            SELECT 1 FROM daily_inventory d
            WHERE d.platform = s.platform
            AND d.listing_id = s.listing_id
            AND d.snapshot_date >= s.detection_date
        )
        ORDER BY s.detection_date DESC, s.platform, s.listing_id
    """)

    false_positives = cursor.fetchall()

    if not false_positives:
        print('\n[OK] No se encontraron falsos positivos.')
        conn.close()
        return

    print(f'\n[!] Falsos positivos encontrados: {len(false_positives)}')
    print('\nDetalle:')
    print(f"{'Platform':<12} {'Listing ID':<15} {'Detection Date':<15}")
    print('-' * 70)

    for platform, listing_id, detection_date in false_positives[:20]:  # Mostrar máximo 20
        print(f"{platform:<12} {listing_id:<15} {detection_date:<15}")

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
    deleted_count = 0

    for platform, listing_id, detection_date in false_positives:
        cursor.execute("""
            DELETE FROM detected_sales
            WHERE platform = ? AND listing_id = ? AND detection_date = ?
        """, (platform, listing_id, detection_date))
        deleted_count += 1

    conn.commit()
    conn.close()

    print(f'\n[OK] {deleted_count} falsos positivos eliminados correctamente.')
    print('\nEjecute "py check_integrity.py --full" para verificar.')
    print('='*70 + '\n')


if __name__ == '__main__':
    cleanup_false_positives()
