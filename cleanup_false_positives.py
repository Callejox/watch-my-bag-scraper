#\!/usr/bin/env python3
import argparse, csv, shutil
from datetime import datetime
from pathlib import Path
from database.db_manager import DatabaseManager
from config import DATABASE_PATH

def backup_database(db_path):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = db_path.parent / f"{db_path.stem}_backup_{ts}{db_path.suffix}"
    shutil.copy2(db_path, backup)
    print(f"[OK] BD respaldada: {backup.name}")
    return backup

def load_false_positives(csv_path):
    fps = []
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["classification"] == "FALSE_POSITIVE":
                    fps.append(row["listing_id"])
    except Exception as e:
        print(f"[ERROR] {e}")
    return fps

def preview_deletions(db, ids):
    with db.get_connection() as conn:
        c = conn.cursor()
        ph = ",".join(["?"] * len(ids))
        c.execute(f"SELECT listing_id,detection_date,sale_price,url FROM detected_sales WHERE platform='chrono24' AND listing_id IN ({ph}) ORDER BY detection_date DESC", ids)
        sales = [dict(r) for r in c.fetchall()]
        print("
" + "="*80 + "
PREVIEW: Ventas a eliminar
" + "="*80)
        if not sales:
            print("[\!] No se encontraron ventas")
            return 0
        for s in sales:
            pr = f"€{s['sale_price']}" if s['sale_price'] else "Sin precio"
            print(f"  {s['listing_id']:12} | {s['detection_date']} | {pr:10}")
        print(f"
Total: {len(sales)} ventas
" + "="*80 + "
")
        return len(sales)

def execute_cleanup(db, ids):
    with db.get_connection() as conn:
        c = conn.cursor()
        ph = ",".join(["?"] * len(ids))
        c.execute(f"DELETE FROM detected_sales WHERE platform='chrono24' AND listing_id IN ({ph})", ids)
        cnt = c.rowcount
        c.execute("INSERT INTO scrape_logs(platform,status,items_scraped,items_sold_detected,notes,duration_seconds,run_date) VALUES('cleanup','success',0,?,'Limpieza falsos positivos',0,date('now'))", (cnt,))
        conn.commit()
        print(f"[OK] Eliminadas {cnt} ventas falsas")
        return cnt

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--ids", help="IDs separados por coma")
    args = p.parse_args()
    print("="*80 + "
LIMPIEZA DE FALSOS POSITIVOS
" + "="*80 + "
")
    ids = [i.strip() for i in args.ids.split(",")] if args.ids else load_false_positives(args.input)
    print(f"[*] Cargados {len(ids)} falsos positivos")
    if not ids:
        print("[\!] No hay falsos positivos
")
        return
    db = DatabaseManager()
    cnt = preview_deletions(db, ids)
    if cnt == 0:
        return
    if not args.execute:
        print("[INFO] Modo PREVIEW
Para ejecutar: py cleanup_false_positives.py --input validation_results.csv --execute
")
        return
    print("[\!] ADVERTENCIA: Eliminará ventas de la BD
")
    if input(f"¿Eliminar {cnt} ventas? (y/N): ").lower() \!= "y":
        print("
[INFO] Cancelado
")
        return
    print("
[*] Creando backup...")
    bk = backup_database(DATABASE_PATH)
    print("[*] Ejecutando limpieza...")
    try:
        d = execute_cleanup(db, ids)
        print("
" + "="*80 + "
LIMPIEZA COMPLETADA
" + "="*80)
        print(f"  Eliminadas: {d}
  Backup: {bk.name}
" + "="*80 + "
")
        print("SIGUIENTE PASO:
  py check_integrity.py --full
")
    except Exception as e:
        print("
" + "="*80 + "
ERROR
" + "="*80 + f"
  {e}
  Backup: {bk.name}
" + "="*80 + "
")
        raise

if __name__ == "__main__":
    main()
