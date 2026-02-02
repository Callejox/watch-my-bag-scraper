"""
Migración: Añadir columna bracelet_material a daily_inventory y detected_sales
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "inventory.db"

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 1. Añadir columna a daily_inventory
        cursor.execute("""
            ALTER TABLE daily_inventory
            ADD COLUMN bracelet_material TEXT
        """)
        print("[OK] Columna bracelet_material anadida a daily_inventory")

        # 2. Añadir columna a detected_sales
        cursor.execute("""
            ALTER TABLE detected_sales
            ADD COLUMN bracelet_material TEXT
        """)
        print("[OK] Columna bracelet_material anadida a detected_sales")

        conn.commit()
        print("\n[OK] Migracion completada exitosamente")

    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("[WARN] La columna bracelet_material ya existe")
        else:
            print(f"✗ Error: {e}")
            raise

    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
