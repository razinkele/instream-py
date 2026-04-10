"""Check alignment: compare cell polygon coords with basemap tile coords."""

from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, args=["--use-gl=angle"])
    page = browser.new_page()
    page.on(
        "console",
        lambda msg: (
            print(f"  [{msg.type}] {msg.text}")
            if "deckgl" in msg.text.lower() or "error" in msg.type
            else None
        ),
    )

    page.goto("http://127.0.0.1:18910", wait_until="load", timeout=30000)
    time.sleep(3)

    # Go to movement tab
    page.locator('[role="tab"]', has_text="Movement").click()
    time.sleep(2)

    # Run sim
    page.evaluate("""() => {
        Shiny.setInputValue('start_date', '2011-04-01');
        Shiny.setInputValue('end_date', '2011-04-05');
    }""")
    time.sleep(1)
    page.locator("#run_btn").click()

    for i in range(30):
        time.sleep(2)
        progress = page.locator("#progress_text").inner_text()
        if "Complete" in progress:
            break

    time.sleep(5)

    # Detailed layer inspection
    result = page.evaluate("""() => {
        var info = {};
        var inst = window.__deckgl_instances && window.__deckgl_instances['movement-movement_map'];
        if (!inst) {
            info.error = 'No map instance found';
            info.all_keys = Object.keys(window.__deckgl_instances || {});
            return info;
        }

        info.map_center = inst.map ? [inst.map.getCenter().lng, inst.map.getCenter().lat] : null;
        info.map_zoom = inst.map ? inst.map.getZoom() : null;
        info.map_bounds = inst.map ? {
            sw: [inst.map.getBounds().getSouthWest().lng, inst.map.getBounds().getSouthWest().lat],
            ne: [inst.map.getBounds().getNorthEast().lng, inst.map.getBounds().getNorthEast().lat]
        } : null;

        // Check layers
        if (inst.lastLayers) {
            info.layers = inst.lastLayers.map(function(l) {
                var linfo = {type: l.type, id: l.id};
                // Check GeoJSON data
                if (l.type === 'GeoJsonLayer' && l.data) {
                    if (l.data.features) {
                        linfo.num_features = l.data.features.length;
                        var f0 = l.data.features[0];
                        if (f0 && f0.geometry) {
                            linfo.geom_type = f0.geometry.type;
                            var c = f0.geometry.coordinates;
                            if (f0.geometry.type === 'Polygon' && c[0]) {
                                linfo.first_coord = c[0][0];
                                linfo.coord_range = {
                                    min_x: Infinity, max_x: -Infinity,
                                    min_y: Infinity, max_y: -Infinity
                                };
                                l.data.features.forEach(function(feat) {
                                    if (feat.geometry && feat.geometry.coordinates) {
                                        var ring = feat.geometry.coordinates[0];
                                        if (ring) ring.forEach(function(pt) {
                                            if (pt[0] < linfo.coord_range.min_x) linfo.coord_range.min_x = pt[0];
                                            if (pt[0] > linfo.coord_range.max_x) linfo.coord_range.max_x = pt[0];
                                            if (pt[1] < linfo.coord_range.min_y) linfo.coord_range.min_y = pt[1];
                                            if (pt[1] > linfo.coord_range.max_y) linfo.coord_range.max_y = pt[1];
                                        });
                                    }
                                });
                            } else if (f0.geometry.type === 'MultiPolygon' && c[0] && c[0][0]) {
                                linfo.first_coord = c[0][0][0];
                            }
                        }
                    }
                }
                // Check ScatterplotLayer data
                if (l.type === 'ScatterplotLayer' && l.data) {
                    linfo.num_points = Array.isArray(l.data) ? l.data.length : 'not array';
                    if (Array.isArray(l.data) && l.data.length > 0) {
                        linfo.first_point = l.data[0];
                        // Compute bounds
                        var minx=Infinity, maxx=-Infinity, miny=Infinity, maxy=-Infinity;
                        l.data.forEach(function(pt) {
                            var pos = pt.position || pt;
                            if (Array.isArray(pos) && pos.length >= 2) {
                                if (pos[0] < minx) minx = pos[0];
                                if (pos[0] > maxx) maxx = pos[0];
                                if (pos[1] < miny) miny = pos[1];
                                if (pos[1] > maxy) maxy = pos[1];
                            }
                        });
                        linfo.point_bounds = {min_x: minx, max_x: maxx, min_y: miny, max_y: maxy};
                    }
                }
                // Check coordinateSystem
                linfo.coordinateSystem = l.coordinateSystem;
                linfo.getPosition = l.getPosition;
                return linfo;
            });
        }

        return info;
    }""")

    print("=== MAP STATE ===")
    print("Center:", result.get("map_center"))
    print("Zoom:", result.get("map_zoom"))
    print("Bounds:", result.get("map_bounds"))

    print("\n=== LAYERS ===")
    for l in result.get("layers", []):
        print(f"\nLayer: {l.get('type')} id={l.get('id')}")
        print(f"  coordinateSystem: {l.get('coordinateSystem')}")
        if "num_features" in l:
            print(f"  features: {l['num_features']}")
            print(f"  geom_type: {l.get('geom_type')}")
            print(f"  first_coord: {l.get('first_coord')}")
            print(f"  coord_range: {l.get('coord_range')}")
        if "num_points" in l:
            print(f"  points: {l['num_points']}")
            print(f"  first_point: {l.get('first_point')}")
            print(f"  point_bounds: {l.get('point_bounds')}")
            print(f"  getPosition: {l.get('getPosition')}")

    if "error" in result:
        print("\nERROR:", result["error"])
        print("All instances:", result.get("all_keys"))

    # Take screenshot at high zoom
    page.screenshot(path="alignment_check.png")
    print("\nScreenshot saved to alignment_check.png")
    browser.close()
