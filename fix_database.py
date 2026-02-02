#!/usr/bin/env python3
"""
Script para reparar problemas de integridad en la base de datos.

Soluciona:
1. Ventas duplicadas en detected_sales
2. Añade constraint único para evitar futuros duplicados
3. Opcionalmente elimina falsos positivos

Uso:
    py fix_database.py --preview          # Ver qué se haría (no modifica)
    py fix_database.py --fix-duplicates   # Eliminar duplicados
    py fix_database.py --fix-all          # Reparar todo
"""

import sys
import argparse
import sqlite3
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent))

from config import DATABASE_PATH


class DatabaseFixer:
    """Reparador de problemas de integridad de base de datos."""

    def __init__(self, db_path=None):
        self.db_path = db_path or DATABASE_PATH
        print(f"[*] Usando base de datos: {self.db_path}")

    def preview_duplicates(self):
        """Muestra los duplicados que serían eliminados."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Encontrar duplicados
        cursor.execute("""
            SELECT platform, listing_id, detection_date, COUNT(*) as count
            FROM detected_sales
            GROUP BY platform, listing_id, detection_date
            HAVING count > 1
        """)

        duplicates = cursor.fetchall()
        total_to_remove = 0

        if not duplicates:
            print("\n[OK] No hay duplicados en detected_sales")
            conn.close()
            return 0

        print(f"\n[!] Encontrados {len(duplicates)} grupos de ventas duplicadas:\n")

        for row in duplicates:
            d = dict(row)
            platform = d['platform']
            listing_id = d['listing_id']
            detection_date = d['detection_date']
            count = d['count']

            # Obtener los IDs de los duplicados
            cursor.execute("""
                SELECT id, sale_price
                FROM detected_sales
                WHERE platform = ? AND listing_id = ? AND detection_date = ?
                ORDER BY id
            """, (platform, listing_id, detection_date))

            entries = cursor.fetchall()
            entries_list = [dict(e) for e in entries]

            print(f"  {platform}: {listing_id} (Fecha: {detection_date})")
            print(f"    - {count} copias detectadas")
            print(f"    - Se mantendra ID {entries_list[0]['id']}, precio {entries_list[0]['sale_price']}")
            print(f"    - Se eliminaran {count - 1} copias: {[e['id'] for e in entries_list[1:]]}")

            total_to_remove += (count - 1)

        print(f"\n[RESUMEN]")
        print(f"  - Total de registros duplicados a eliminar: {total_to_remove}")
        print(f"  - Se mantendra 1 copia de cada venta")

        conn.close()
        return total_to_remove

    def fix_duplicates(self, preview=False):
        """
        Elimina ventas duplicadas manteniendo solo la primera entrada.

        Args:
            preview: Si True, solo muestra lo que haría
        """
        if preview:
            return self.preview_duplicates()

        print("\n[*] Eliminando duplicados de detected_sales...")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Encontrar duplicados
        cursor.execute("""
            SELECT platform, listing_id, detection_date
            FROM detected_sales
            GROUP BY platform, listing_id, detection_date
            HAVING COUNT(*) > 1
        """)

        duplicates = cursor.fetchall()

        if not duplicates:
            print("[OK] No hay duplicados para eliminar")
            conn.close()
            return 0

        total_removed = 0

        for row in duplicates:
            platform, listing_id, detection_date = row

            # Obtener todos los IDs de este grupo
            cursor.execute("""
                SELECT id
                FROM detected_sales
                WHERE platform = ? AND listing_id = ? AND detection_date = ?
                ORDER BY id
            """, (platform, listing_id, detection_date))

            ids = [r[0] for r in cursor.fetchall()]

            # Mantener el primero, eliminar el resto
            ids_to_delete = ids[1:]

            if ids_to_delete:
                placeholders = ','.join('?' * len(ids_to_delete))
                cursor.execute(f"""
                    DELETE FROM detected_sales
                    WHERE id IN ({placeholders})
                """, ids_to_delete)

                total_removed += len(ids_to_delete)

        conn.commit()
        print(f"[OK] Eliminados {total_removed} registros duplicados")
        print(f"[OK] Se mantuvieron {len(duplicates)} ventas unicas")

        conn.close()
        return total_removed

    def add_unique_constraint(self):
        """
        Añade constraint único a detected_sales para evitar futuros duplicados.

        Nota: SQLite no permite añadir constraints a tablas existentes,
        así que hay que recrear la tabla.
        """
        print("\n[*] Añadiendo constraint unico a detected_sales...")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Verificar si ya existe la constraint
        cursor.execute("""
            SELECT sql FROM sqlite_master
            WHERE type='table' AND name='detected_sales'
        """)

        current_schema = cursor.fetchone()[0]

        if 'UNIQUE' in current_schema and 'platform' in current_schema:
            print("[OK] La tabla ya tiene constraint unico")
            conn.close()
            return

        print("[*] Creando nueva tabla con constraint...")

        # Crear tabla temporal con constraint
        cursor.execute("""
            CREATE TABLE detected_sales_new (
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(platform, listing_id, detection_date)
            )
        """)

        # Copiar datos (solo registros unicos)
        cursor.execute("""
            INSERT INTO detected_sales_new
            SELECT * FROM detected_sales
            WHERE id IN (
                SELECT MIN(id)
                FROM detected_sales
                GROUP BY platform, listing_id, detection_date
            )
        """)

        copied = cursor.rowcount
        print(f"[OK] Copiados {copied} registros unicos")

        # Eliminar tabla vieja y renombrar
        cursor.execute("DROP TABLE detected_sales")
        cursor.execute("ALTER TABLE detected_sales_new RENAME TO detected_sales")

        # Recrear indices
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sales_platform_date
            ON detected_sales(platform, detection_date)
        """)

        conn.commit()
        print("[OK] Constraint unico añadido exitosamente")

        conn.close()

    def list_false_positives(self):
        """Lista los falsos positivos detectados."""
        print("\n[*] Buscando falsos positivos...")

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT s.platform, s.listing_id, s.detection_date
            FROM detected_sales s
        """)

        sold_items = cursor.fetchall()
        false_positives = []

        for row in sold_items:
            d = dict(row)
            platform = d['platform']
            listing_id = d['listing_id']
            detection_date = d['detection_date']

            # Buscar reapariciones
            cursor.execute("""
                SELECT snapshot_date, listing_price
                FROM daily_inventory
                WHERE platform = ? AND listing_id = ? AND snapshot_date > ?
                ORDER BY snapshot_date
            """, (platform, listing_id, detection_date))

            reappearances = cursor.fetchall()

            if reappearances:
                false_positives.append({
                    'platform': platform,
                    'listing_id': listing_id,
                    'detected_sold': detection_date,
                    'reappearances': [dict(r) for r in reappearances]
                })

        if not false_positives:
            print("[OK] No se encontraron falsos positivos")
            conn.close()
            return []

        print(f"\n[!] Encontrados {len(false_positives)} falsos positivos:\n")

        for fp in false_positives:
            print(f"  {fp['platform']}: {fp['listing_id']}")
            print(f"    - Detectado vendido: {fp['detected_sold']}")
            print(f"    - Reapariciones:")
            for reapp in fp['reappearances']:
                print(f"      - {reapp['snapshot_date']}: {reapp['listing_price']}")

        conn.close()
        return false_positives

    def remove_false_positives(self, preview=False):
        """
        Elimina ventas que son falsos positivos.

        Args:
            preview: Si True, solo muestra lo que haría
        """
        false_positives = self.list_false_positives()

        if not false_positives:
            return 0

        if preview:
            print(f"\n[PREVIEW] Se eliminarian {len(false_positives)} ventas falsas")
            return len(false_positives)

        print(f"\n[*] Eliminando {len(false_positives)} falsos positivos...")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        removed = 0
        for fp in false_positives:
            cursor.execute("""
                DELETE FROM detected_sales
                WHERE platform = ? AND listing_id = ? AND detection_date = ?
            """, (fp['platform'], fp['listing_id'], fp['detected_sold']))

            removed += cursor.rowcount

        conn.commit()
        print(f"[OK] Eliminados {removed} registros de falsos positivos")

        conn.close()
        return removed


def main():
    parser = argparse.ArgumentParser(
        description="Reparar problemas de integridad en la base de datos"
    )
    parser.add_argument(
        '--preview',
        action='store_true',
        help='Mostrar que se haria sin modificar la base de datos'
    )
    parser.add_argument(
        '--fix-duplicates',
        action='store_true',
        help='Eliminar ventas duplicadas'
    )
    parser.add_argument(
        '--fix-false-positives',
        action='store_true',
        help='Eliminar falsos positivos'
    )
    parser.add_argument(
        '--add-constraint',
        action='store_true',
        help='Añadir constraint unico para evitar futuros duplicados'
    )
    parser.add_argument(
        '--fix-all',
        action='store_true',
        help='Reparar todo (duplicados + constraint + falsos positivos)'
    )

    args = parser.parse_args()

    fixer = DatabaseFixer()

    if args.preview:
        print("\n" + "="*70)
        print("PREVIEW - NO SE MODIFICARA LA BASE DE DATOS")
        print("="*70)
        fixer.preview_duplicates()
        fixer.list_false_positives()
        return

    if args.fix_all:
        print("\n" + "="*70)
        print("REPARACION COMPLETA")
        print("="*70)
        fixer.fix_duplicates()
        fixer.add_unique_constraint()
        fixer.remove_false_positives()
        print("\n[OK] Reparacion completa finalizada")
        return

    if args.fix_duplicates:
        fixer.fix_duplicates()

    if args.add_constraint:
        fixer.add_unique_constraint()

    if args.fix_false_positives:
        fixer.remove_false_positives()

    if not any([args.fix_duplicates, args.add_constraint,
                args.fix_false_positives, args.fix_all, args.preview]):
        parser.print_help()


if __name__ == "__main__":
    main()
