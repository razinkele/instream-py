"""pytest config for ices-mcp tests.

Adds the ices-mcp/ directory to sys.path so `from ices_clients import …`
works regardless of where pytest is invoked.
"""
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ICES_MCP = _HERE.parent
if str(_ICES_MCP) not in sys.path:
    sys.path.insert(0, str(_ICES_MCP))
