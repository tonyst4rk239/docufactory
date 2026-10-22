#!/usr/bin/env python3
"""CLI para generación de miniaturas desde el directorio thumbnail_studio."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from scripts.generar_miniatura import main

if __name__ == "__main__":
    sys.exit(main())
