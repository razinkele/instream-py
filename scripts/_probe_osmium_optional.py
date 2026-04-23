"""Verify create_model_osm imports both with and without osmium present."""
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

print("--- with osmium present ---")
from modules.create_model_osm import query_waterways, _HAS_OSMIUM, _HydroHandler  # noqa
print(f"import ok; _HAS_OSMIUM={_HAS_OSMIUM}")

print("\n--- simulating missing osmium ---")
# Force reimport with osmium hidden
for mod in list(sys.modules):
    if mod.startswith("modules.create_model_osm") or mod == "osmium":
        del sys.modules[mod]
# Block osmium import
class _BlockOsmium:
    def find_spec(self, name, path, target=None):
        if name == "osmium" or name.startswith("osmium."):
            raise ImportError("simulated: osmium not installed")
        return None
sys.meta_path.insert(0, _BlockOsmium())

try:
    from modules.create_model_osm import _HAS_OSMIUM  # noqa: F811
    print(f"import ok without osmium; _HAS_OSMIUM={_HAS_OSMIUM}")
    # Try instantiating _HydroHandler — should raise a clear error
    from modules.create_model_osm import _HydroHandler  # noqa: F811
    try:
        h = _HydroHandler()
        print("FAIL: _HydroHandler() should have raised")
    except RuntimeError as e:
        print(f"_HydroHandler() raised RuntimeError as expected: {e}")
except Exception as e:
    print(f"FAIL on fallback import: {type(e).__name__}: {e}")
