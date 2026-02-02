"""
Script para verificar que FlareSolverr está funcionando correctamente.
"""

import requests
import json
from config import FLARESOLVERR_URL

def test_flaresolverr():
    """Prueba la conectividad con FlareSolverr."""
    print("=" * 60)
    print("VERIFICACIÓN DE FLARESOLVERR")
    print("=" * 60)
    print()

    # Test 1: Verificar conectividad
    print("[1/2] Verificando conectividad...")
    try:
        response = requests.get(
            FLARESOLVERR_URL.replace("/v1", ""),
            timeout=5
        )
        if response.status_code == 200:
            print("[OK] FlareSolverr esta corriendo")
        else:
            print(f"[ERROR] FlareSolverr respondio con codigo: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("[ERROR] No se puede conectar a FlareSolverr")
        print("  - Asegurate de que Docker esta corriendo")
        print("  - Ejecuta: start_flaresolverr.bat")
        return False
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        return False

    # Test 2: Resolver una página simple
    print("[2/2] Probando resolución de URL...")
    try:
        payload = {
            "cmd": "request.get",
            "url": "https://www.chrono24.es",
            "maxTimeout": 60000,
        }

        response = requests.post(
            FLARESOLVERR_URL,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=70
        )

        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "ok":
                solution = result.get("solution", {})
                print(f"[OK] FlareSolverr resolvio correctamente")
                print(f"  - Status: {solution.get('status')}")
                print(f"  - Cookies: {len(solution.get('cookies', []))}")
                return True
            else:
                print(f"[ERROR] FlareSolverr error: {result.get('message')}")
                return False
        else:
            print(f"[ERROR] HTTP {response.status_code}")
            return False

    except Exception as e:
        print(f"[ERROR] Error probando resolucion: {e}")
        return False

if __name__ == "__main__":
    success = test_flaresolverr()

    print()
    print("=" * 60)
    if success:
        print("[OK] FLARESOLVERR FUNCIONANDO CORRECTAMENTE")
        print()
        print("Ahora puedes ejecutar el scraper de Chrono24:")
        print("  py main.py --scrape --chrono24-only")
    else:
        print("[ERROR] FLARESOLVERR NO ESTA FUNCIONANDO")
        print()
        print("Pasos para solucionar:")
        print("  1. Inicia Docker Desktop")
        print("  2. Ejecuta: start_flaresolverr.bat")
        print("  3. Vuelve a ejecutar este script")
    print("=" * 60)
