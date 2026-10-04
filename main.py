#!/usr/bin/env python3
"""Launch Afterlight, or the exact preserved game with --classic."""
import runpy
import sys
from pathlib import Path

if __name__ == '__main__':
    if '--classic' in sys.argv:
        sys.argv.remove('--classic')
        path=Path(__file__).resolve().parent/'legacy'/'v1'/'main.py'
        sys.path.insert(0,str(path.parent))
        runpy.run_path(str(path),run_name='__main__')
    else:
        from glyph_city.game import main
        raise SystemExit(main())
