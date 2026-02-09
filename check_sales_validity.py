#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Tests Avanzados de Integridad para Ventas Detectadas
import requests, re, time, random
from datetime import date, timedelta
from database.db_manager import DatabaseManager

def test_scraping_coverage_consistency(db):
    with db.get_connection() as conn:
        c = conn.cursor()
        c.execute("""SELECT snapshot_date, COUNT(*) as count FROM daily_inventory 
                     WHERE platform='chrono24' AND snapshot_date>=date('now','-7 days')
                     GROUP BY snapshot_date ORDER BY snapshot_date DESC""")
        counts = [dict(r) for r in c.fetchall()]
    if len(counts) < 2:
        return True, "Datos insuficientes"
    today, yesterday = counts[0]['count'], counts[1]['count']
    drop = ((yesterday - today) / yesterday) * 100 if yesterday > 0 else 0
    if abs(drop) > 10:
        return False, f"Cobertura cambió {drop:+.1f}% (ayer: {yesterday}, hoy: {today})"
    return True, f"Cobertura estable: {today} items (delta: {drop:+.1f}%)"

def test_sales_detection_rate(db):
    today, yesterday = date.today(), date.today() - timedelta(days=1)
    with db.get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as c FROM daily_inventory WHERE platform='chrono24' AND snapshot_date=?", (yesterday,))
        yesterday_count = dict(c.fetchone())['c']
        c.execute("SELECT COUNT(*) as c FROM detected_sales WHERE platform='chrono24' AND detection_date=?", (today,))
        sales_count = dict(c.fetchone())['c']
    if yesterday_count == 0:
        return True, "Sin baseline"
    rate = (sales_count / yesterday_count) * 100
    if rate > 20:
        return False, f"Tasa {rate:.1f}% excede umbral (20%)"
    return True, f"Tasa aceptable: {rate:.1f}%"

def test_pagination_completeness(db):
    with db.get_connection() as conn:
        c = conn.cursor()
        c.execute("""SELECT notes FROM scrape_logs WHERE platform='chrono24' 
                     AND run_date=date('now') ORDER BY created_at DESC LIMIT 1""")
        row = c.fetchone()
        if not row:
            return False, "Sin logs de scraping hoy"
        notes = dict(row).get('notes', '')
        m = re.search(r'(\d+) páginas detectadas.*scrapeando (\d+) páginas', notes)
        if m:
            total, scraped = int(m.group(1)), int(m.group(2))
            cov = (scraped / total) * 100
            if cov < 5:
                return False, f"Cobertura {cov:.1f}% ({scraped}/{total} págs) CRÍTICO"
            return True, f"Cobertura {cov:.1f}% ({scraped}/{total} págs)"
        return True, "Datos paginación no disponibles"

def test_url_accessibility_sample(db):
    with db.get_connection() as conn:
        c = conn.cursor()
        c.execute("""SELECT url FROM detected_sales WHERE platform='chrono24' 
                     AND detection_date>=date('now','-7 days') ORDER BY RANDOM() LIMIT 10""")
        urls = [dict(r)['url'] for r in c.fetchall()]
    if not urls:
        return True, "Sin ventas recientes"
    active = 0
    for url in urls:
        try:
            if requests.head(url, timeout=5, allow_redirects=True).status_code == 200:
                active += 1
        except:
            pass
        time.sleep(0.5)
    pct = (active / len(urls)) * 100
    if pct > 30:
        return False, f"{active}/{len(urls)} URLs activas ({pct:.0f}%) - posibles falsos positivos"
    return True, f"{active}/{len(urls)} URLs activas ({pct:.0f}%)"

def main():
    print("="*70)
    print("TESTS AVANZADOS DE INTEGRIDAD")
    print("="*70)
    print()
    db = DatabaseManager()
    tests = [
        ("Consistencia cobertura scraping", test_scraping_coverage_consistency),
        ("Tasa de ventas detectadas", test_sales_detection_rate),
        ("Completitud de paginación", test_pagination_completeness),
        ("Muestra accesibilidad URLs", test_url_accessibility_sample),
    ]
    passed, warnings, errors = 0, 0, 0
    for name, test_fn in tests:
        print(f"[*] {name}...", end=" ")
        try:
            ok, msg = test_fn(db)
            if ok:
                print(f"[OK] {msg}")
                passed += 1
            else:
                print(f"[X] {msg}")
                errors += 1
        except Exception as e:
            print(f"[!] Error: {e}")
            warnings += 1
    print()
    print("="*70)
    print("RESUMEN")
    print("="*70)
    print(f"[OK] Tests pasados: {passed}")
    print(f"[!] Advertencias: {warnings}")
    print(f"[X] Errores críticos: {errors}")
    print("="*70)
    print()
    if errors > 0:
        print("ACCIÓN REQUERIDA:")
        print("  Revisa los errores críticos detectados.")
        print("  Ejecuta check_integrity.py --full para más detalles.")
        print()

if __name__ == "__main__":
    main()
