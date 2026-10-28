"""refresh.py [--rebuild] : (optionally re-pour, then) export geom.json + poured.json into $LCEDA_WORK"""
import sys
import _boot  # noqa: F401
import eda
eda.refresh(rebuild='--rebuild' in sys.argv)
print('ok')
