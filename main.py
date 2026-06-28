from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import json
import os
from datetime import datetime

app = FastAPI(title="QGIS Plugin API")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LOG_FILE = os.path.join(BASE_DIR, "reproject_logs.json")
EXTENT_GEOJSON_FILE = os.path.join(BASE_DIR, "reproject_extents.geojson")
GEOMETRY_CACHE_DIR = os.path.join(BASE_DIR, "geometry_cache")


# -----------------------------
# MODELS
# -----------------------------
class ReprojectRequest(BaseModel):
    layer_name: str
    input_crs: str
    output_crs: str
    feature_count: int | None = None
    geometry_type: str | None = None
    user: str | None = None
    project_name: str | None = None
    project_path: str | None = None
    process_time: float | None = None
    extent_coords_4326: list | None = None
    layer_geojson_4326: dict | None = None


# -----------------------------
# STORAGE SERVICE
# -----------------------------
class JsonStorageService:
    @staticmethod
    def read_json(path, default_value):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as file:
                return json.load(file)

        return default_value

    @staticmethod
    def write_json(path, data):
        folder = os.path.dirname(path)

        if folder:
            os.makedirs(folder, exist_ok=True)

        with open(path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4, ensure_ascii=False)


# -----------------------------
# LOG SERVICE
# -----------------------------
class ReprojectLogService:
    def __init__(self):
        os.makedirs(GEOMETRY_CACHE_DIR, exist_ok=True)

    def get_logs(self):
        return JsonStorageService.read_json(LOG_FILE, [])

    def append_log(self, entry):
        logs = self.get_logs()
        log_index = len(logs)

        entry["log_index"] = log_index
        logs.append(entry)

        JsonStorageService.write_json(LOG_FILE, logs)

        return log_index

    def get_log(self, log_index):
        logs = self.get_logs()

        if log_index < 0 or log_index >= len(logs):
            return None

        return logs[log_index]

    def save_extent_geojson(self, log_index, entry):
        coords = entry.get("extent_coords_4326") or []

        if len(coords) != 4:
            return

        polygon_coords = coords + [coords[0]]

        geojson = JsonStorageService.read_json(
            EXTENT_GEOJSON_FILE,
            {
                "type": "FeatureCollection",
                "features": []
            }
        )

        feature = {
            "type": "Feature",
            "properties": {
                "log_index": log_index,
                "timestamp": entry.get("timestamp"),
                "layer_name": entry.get("layer_name"),
                "input_crs": entry.get("input_crs"),
                "output_crs": entry.get("output_crs"),
                "feature_count": entry.get("feature_count"),
                "geometry_type": entry.get("geometry_type"),
                "user": entry.get("user"),
                "project_name": entry.get("project_name"),
                "process_time": entry.get("process_time")
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [polygon_coords]
            }
        }

        geojson["features"].append(feature)
        JsonStorageService.write_json(EXTENT_GEOJSON_FILE, geojson)

    def get_extent_geojson(self):
        return JsonStorageService.read_json(
            EXTENT_GEOJSON_FILE,
            {
                "type": "FeatureCollection",
                "features": []
            }
        )

    def get_single_extent_geojson(self, log_index):
        extent_geojson = self.get_extent_geojson()

        for feature in extent_geojson.get("features", []):
            if feature.get("properties", {}).get("log_index") == log_index:
                return {
                    "type": "FeatureCollection",
                    "features": [feature]
                }

        return None

    def geometry_file_path(self, log_index):
        return os.path.join(GEOMETRY_CACHE_DIR, f"geometry_{log_index}.geojson")

    def save_layer_geometry(self, log_index, entry, layer_geojson):
        if not layer_geojson:
            return

        layer_geojson["metadata"] = {
            "log_index": log_index,
            "timestamp": entry.get("timestamp"),
            "layer_name": entry.get("layer_name"),
            "input_crs": entry.get("input_crs"),
            "output_crs": entry.get("output_crs"),
            "feature_count": entry.get("feature_count"),
            "geometry_type": entry.get("geometry_type"),
            "user": entry.get("user"),
            "project_name": entry.get("project_name"),
            "project_path": entry.get("project_path"),
            "process_time": entry.get("process_time")
        }

        JsonStorageService.write_json(
            self.geometry_file_path(log_index),
            layer_geojson
        )

    def get_layer_geometry(self, log_index):
        path = self.geometry_file_path(log_index)

        if not os.path.exists(path):
            return None

        return JsonStorageService.read_json(
            path,
            {
                "type": "FeatureCollection",
                "features": []
            }
        )


log_service = ReprojectLogService()


# -----------------------------
# HELPERS
# -----------------------------
def safe_file_name(value, fallback):
    text = value or fallback

    return "".join(
        char if char.isalnum() or char in ("-", "_") else "_"
        for char in text
    )


def build_log_entry(data: ReprojectRequest):
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "layer_name": data.layer_name,
        "input_crs": data.input_crs,
        "output_crs": data.output_crs,
        "feature_count": data.feature_count,
        "geometry_type": data.geometry_type,
        "user": data.user,
        "project_name": data.project_name,
        "project_path": data.project_path,
        "process_time": data.process_time,
        "extent_coords_4326": data.extent_coords_4326,
        "has_layer_geometry": bool(
            data.layer_geojson_4326
            and data.layer_geojson_4326.get("features")
        )
    }


# -----------------------------
# ROOT
# -----------------------------
@app.get("/")
def root():
    return {"message": "API çalışıyor 🚀"}


# -----------------------------
# POST /reproject
# -----------------------------
@app.post("/reproject")
def receive_reproject(data: ReprojectRequest):
    log_entry = build_log_entry(data)

    log_index = log_service.append_log(log_entry)
    log_service.save_extent_geojson(log_index, log_entry)
    log_service.save_layer_geometry(
        log_index,
        log_entry,
        data.layer_geojson_4326
    )

    return {
        "status": "success",
        "message": "Log, extent GeoJSON ve layer geometry kaydedildi",
        "log_index": log_index,
        "data": log_entry
    }


# -----------------------------
# GET /logs
# -----------------------------
@app.get("/logs")
def get_logs():
    return log_service.get_logs()


# -----------------------------
# GET /extent-geojson
# -----------------------------
@app.get("/extent-geojson")
def get_extent_geojson():
    return log_service.get_extent_geojson()


# -----------------------------
# GET /extent-geojson/download/{log_index}
# -----------------------------
@app.get("/extent-geojson/download/{log_index}")
def download_single_extent_geojson(log_index: int):
    single_geojson = log_service.get_single_extent_geojson(log_index)

    if not single_geojson:
        return JSONResponse(
            content={"error": "Extent not found"},
            status_code=404
        )

    log_entry = log_service.get_log(log_index) or {}
    file_name = safe_file_name(
        log_entry.get("layer_name"),
        f"extent_{log_index}"
    )

    return JSONResponse(
        content=single_geojson,
        headers={
            "Content-Disposition": f"attachment; filename={file_name}_extent.geojson"
        }
    )


# -----------------------------
# GET /geometry-geojson/{log_index}
# -----------------------------
@app.get("/geometry-geojson/{log_index}")
def get_layer_geometry_geojson(log_index: int):
    layer_geojson = log_service.get_layer_geometry(log_index)

    if not layer_geojson:
        return JSONResponse(
            content={
                "type": "FeatureCollection",
                "features": [],
                "message": "Geometry not found"
            },
            status_code=404
        )

    return layer_geojson


# -----------------------------
# GET /geometry-geojson/download/{log_index}
# -----------------------------
@app.get("/geometry-geojson/download/{log_index}")
def download_layer_geometry_geojson(log_index: int):
    layer_geojson = log_service.get_layer_geometry(log_index)

    if not layer_geojson:
        return JSONResponse(
            content={"error": "Geometry not found"},
            status_code=404
        )

    log_entry = log_service.get_log(log_index) or {}
    file_name = safe_file_name(
        log_entry.get("layer_name"),
        f"geometry_{log_index}"
    )

    return JSONResponse(
        content=layer_geojson,
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}_geometry.geojson"',
            "Content-Type": "application/geo+json"
        }
    )


# -----------------------------
# GET /logs/view
# -----------------------------
@app.get("/logs/view", response_class=HTMLResponse)
def logs_view():
    logs = log_service.get_logs()

    rows = ""

    for item in reversed(logs):
        log_index = item.get("log_index")
        coords = item.get("extent_coords_4326") or []
        feature_count = item.get("feature_count", "-")

        if coords:
            coords_preview = "<br>".join([
                f"{round(coord[0], 6)}, {round(coord[1], 6)}"
                for coord in coords
            ])
            coords_cell = (
                f'<a class="coord-link" href="/map?feature_index={log_index}&mode=extent" '
                f'title="Open extent on map">{coords_preview}</a>'
            )
        else:
            coords_cell = "-"

        if item.get("has_layer_geometry"):
            geometry_cell = (
                f'<a class="view-link" href="/map?feature_index={log_index}&mode=geometry" '
                f'title="View real layer geometry">View Geometry</a> '
                f'<span class="muted">({feature_count})</span>'
            )
            download_cell = (
                f'<a class="download-link" href="/geometry-geojson/download/{log_index}" '
                f'download>Download GeoJSON</a>'
            )
        else:
            geometry_cell = (
                f'<span class="muted">No geometry</span> '
                f'<span class="muted">({feature_count})</span>'
            )
            download_cell = "-"

        rows += f"""
        <tr>
            <td>{item.get("timestamp", "-")}</td>
            <td>{item.get("user", "-")}</td>
            <td>{item.get("project_name", "-")}</td>
            <td>{item.get("layer_name", "-")}</td>
            <td>{item.get("geometry_type", "-")}</td>
            <td>{geometry_cell}</td>
            <td>{item.get("input_crs", "-")} → {item.get("output_crs", "-")}</td>
            <td>{item.get("process_time", "-")} s</td>
            <td>{download_cell}</td>
            <td class="coords">{coords_cell}</td>
        </tr>
        """

    html = f"""
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>QGIS Plugin Logs</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 24px;
                background: #f6f7f9;
                color: #222;
            }}

            h1 {{
                margin-bottom: 8px;
            }}

            .links {{
                margin-bottom: 20px;
            }}

            .links a {{
                margin-right: 12px;
                color: #2454d6;
                text-decoration: none;
                font-weight: 600;
            }}

            table {{
                border-collapse: collapse;
                width: 100%;
                background: white;
                box-shadow: 0 2px 10px rgba(0,0,0,0.06);
                border-radius: 10px;
                overflow: hidden;
            }}

            th {{
                background: #202938;
                color: white;
                text-align: left;
                padding: 12px;
                font-size: 13px;
            }}

            td {{
                border-bottom: 1px solid #eee;
                padding: 10px 12px;
                font-size: 13px;
                vertical-align: top;
            }}

            tr:hover {{
                background: #f1f5ff;
            }}

            .coords {{
                font-family: Consolas, monospace;
                white-space: nowrap;
            }}

            .coord-link {{
                color: #111827;
                text-decoration: none;
                display: inline-block;
                padding: 4px 6px;
                border-radius: 6px;
            }}

            .coord-link:hover {{
                background: #eaf1ff;
                color: #2454d6;
            }}

            .view-link, .download-link {{
                color: #2454d6;
                font-weight: 600;
                text-decoration: none;
                padding: 4px 6px;
                border-radius: 6px;
                display: inline-block;
            }}

            .view-link:hover, .download-link:hover {{
                background: #eaf1ff;
            }}

            .muted {{
                color: #6b7280;
                font-size: 12px;
            }}
        </style>
    </head>

    <body>
        <h1>QGIS Plugin Logs</h1>

        <div class="links">
            <a href="/logs">Raw JSON logs</a>
            <a href="/extent-geojson">Extent GeoJSON</a>
            <a href="/map">Map View</a>
            <a href="/docs">API Docs</a>
        </div>

        <table>
            <thead>
                <tr>
                    <th>Time</th>
                    <th>User</th>
                    <th>Project</th>
                    <th>Layer</th>
                    <th>Geometry</th>
                    <th>View Geometry</th>
                    <th>CRS</th>
                    <th>Process Time</th>
                    <th>GeoJSON</th>
                    <th>Extent Coordinates EPSG:4326</th>
                </tr>
            </thead>

            <tbody>
                {rows if rows else '<tr><td colspan="10">No logs yet.</td></tr>'}
            </tbody>
        </table>
    </body>
    </html>
    """

    return html


# -----------------------------
# GET /map
# -----------------------------
@app.get("/map", response_class=HTMLResponse)
def map_view():
    html = """
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>QGIS Logged Geometry Map</title>

        <link
            rel="stylesheet"
            href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
        />

        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

        <style>
            html, body {
                height: 100%;
                margin: 0;
                font-family: Arial, sans-serif;
            }

            #map {
                height: 100%;
                width: 100%;
            }

            .top-panel {
                position: absolute;
                top: 12px;
                left: 56px;
                z-index: 1000;
                background: white;
                padding: 12px 14px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.25);
                font-size: 13px;
            }

            .top-panel h2 {
                margin: 0 0 6px 0;
                font-size: 18px;
            }

            .top-panel a {
                color: #2454d6;
                font-weight: 600;
                text-decoration: none;
                margin-right: 10px;
            }

            .coord-box {
                font-family: Consolas, monospace;
                font-size: 13px;
                line-height: 1.5;
            }
        </style>
    </head>

    <body>
        <div id="map"></div>

        <div class="top-panel">
            <h2>QGIS Logged Geometry Map</h2>
            <div>
                <a href="/logs/view">Logs Table</a>
                <a href="/extent-geojson">Extent GeoJSON</a>
                <a href="/docs">API Docs</a>
            </div>
            <div style="margin-top:8px;">
                View Geometry → real layer features<br>
                Coordinate click → extent box<br>
                Right click on map → get coordinate
            </div>
        </div>

        <script>
            const map = L.map("map").setView([39.0, 35.0], 6);

            const googleSatellite = L.tileLayer(
                "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
                {
                    maxZoom: 21,
                    attribution: "Google Satellite"
                }
            ).addTo(map);

            const osm = L.tileLayer(
                "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
                {
                    maxZoom: 19,
                    attribution: "© OpenStreetMap contributors"
                }
            );

            L.control.layers({
                "Google Satellite": googleSatellite,
                "OpenStreetMap": osm
            }).addTo(map);

            const params = new URLSearchParams(window.location.search);
            const selectedIndex = params.has("feature_index")
                ? parseInt(params.get("feature_index"), 10)
                : null;

            const mode = params.get("mode") || "extent";

            const selectedDataUrl = selectedIndex !== null && mode === "geometry"
                ? `/geometry-geojson/${selectedIndex}`
                : "/extent-geojson";

            fetch(selectedDataUrl)
                .then(response => response.json())
                .then(data => {
                    if (mode === "extent" && data.features) {
                        data.features.forEach((feature, index) => {
                            feature.properties = feature.properties || {};
                            if (feature.properties.log_index === undefined) {
                                feature.properties.log_index = index;
                            }
                        });
                    }

                    let selectedLayer = null;

                    const layerGroup = L.geoJSON(data, {
                        style: function(feature) {
                            if (mode === "geometry") {
                                return {
                                    color: "#00e5ff",
                                    weight: 2,
                                    fillColor: "#00e5ff",
                                    fillOpacity: 0.22
                                };
                            }

                            const logIndex = feature.properties.log_index;

                            if (selectedIndex !== null && logIndex === selectedIndex) {
                                return {
                                    color: "#ff3300",
                                    weight: 5,
                                    fillColor: "#ff3300",
                                    fillOpacity: 0.28
                                };
                            }

                            return {
                                color: "#ffcc00",
                                weight: 3,
                                fillColor: "#ffcc00",
                                fillOpacity: 0.18
                            };
                        },

                        onEachFeature: function (feature, layer) {
                            const p = feature.properties || {};
                            const logIndex = p.log_index;

                            let popupHtml = "";

                            if (mode === "geometry") {
                                popupHtml = `
                                    <b>Feature ID:</b> ${p.fid ?? "-"}<br>
                                    <b>Layer Geometry</b><br>
                                `;

                                Object.keys(p).slice(0, 12).forEach(key => {
                                    popupHtml += `<b>${key}:</b> ${p[key]}<br>`;
                                });
                            } else {
                                popupHtml = `
                                    <b>Layer:</b> ${p.layer_name || "-"}<br>
                                    <b>User:</b> ${p.user || "-"}<br>
                                    <b>Project:</b> ${p.project_name || "-"}<br>
                                    <b>Geometry:</b> ${p.geometry_type || "-"}<br>
                                    <b>Features:</b> ${p.feature_count ?? "-"}<br>
                                    <b>CRS:</b> ${p.input_crs || "-"} → ${p.output_crs || "-"}<br>
                                    <b>Process Time:</b> ${p.process_time ?? "-"} s<br>
                                    <b>Time:</b> ${p.timestamp || "-"}
                                `;
                            }

                            layer.bindPopup(popupHtml);

                            if (selectedIndex !== null && logIndex === selectedIndex) {
                                selectedLayer = layer;
                            }
                        }
                    }).addTo(map);

                    const allLayers = layerGroup.getLayers();

                    if (mode === "geometry" && allLayers.length > 0) {
                        map.fitBounds(layerGroup.getBounds(), {
                            padding: [60, 60],
                            maxZoom: 20
                        });
                    } else if (selectedLayer) {
                        map.fitBounds(selectedLayer.getBounds(), {
                            padding: [80, 80],
                            maxZoom: 19
                        });
                        selectedLayer.openPopup();
                    } else if (allLayers.length > 0) {
                        const lastLayer = allLayers[allLayers.length - 1];

                        map.fitBounds(lastLayer.getBounds(), {
                            padding: [60, 60],
                            maxZoom: 18
                        });
                    }
                })
                .catch(error => {
                    console.error("GeoJSON load error:", error);
                    alert("GeoJSON yüklenemedi.");
                });

            map.on("contextmenu", function (event) {
                const lat = event.latlng.lat.toFixed(7);
                const lng = event.latlng.lng.toFixed(7);

                const googleMapsUrl = `https://www.google.com/maps?q=${lat},${lng}`;

                const popupHtml = `
                    <div class="coord-box">
                        <b>Coordinate</b><br>
                        Lat: ${lat}<br>
                        Lon: ${lng}<br>
                        <br>
                        <b>Copy:</b><br>
                        ${lat}, ${lng}<br>
                        <br>
                        <a href="${googleMapsUrl}" target="_blank">Open in Google Maps</a>
                    </div>
                `;

                L.popup()
                    .setLatLng(event.latlng)
                    .setContent(popupHtml)
                    .openOn(map);
            });
        </script>
    </body>
    </html>
    """

    return html
