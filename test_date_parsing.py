"""
Test rápido del parsing de fechas mejorado en scraper_chrono.py
"""
import sys
sys.path.insert(0, '.')

from scrapers.scraper_chrono import Chrono24Scraper

def test_date_parsing():
    scraper = Chrono24Scraper()

    test_cases = [
        "hace 2 días",
        "hace 5 horas",
        "hace 3 semanas",
        "12.01.2024",
        "25/11/23",
        "2026-01-15",
        "25 ene 2024",
        "Jan 15, 2024",
    ]

    print("Test de parsing de fechas:")
    print("=" * 60)

    passed = 0
    failed = 0

    for test in test_cases:
        result = scraper._parse_date(test)
        status = "[OK]" if result is not None else "[FAIL]"

        if result is not None:
            passed += 1
        else:
            failed += 1

        print(f"{status} {test:25s} -> {result}")

    print("=" * 60)
    print(f"Resultados: {passed} OK, {failed} FAIL")

    if failed == 0:
        print("\n[OK] Todos los tests de parsing de fechas pasaron!")
        return True
    else:
        print(f"\n[WARN] {failed} tests fallaron")
        return False

if __name__ == "__main__":
    success = test_date_parsing()
    sys.exit(0 if success else 1)
