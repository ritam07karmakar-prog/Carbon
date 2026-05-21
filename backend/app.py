import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from models.soil_analyzer import analyze, calibrate_with_known
from satellite.verifier import verify_location, regional_avg_som

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="../frontend", static_url_path="")
CORS(app)

_analysis_history = []


def get_history():
    return _analysis_history


def add_history_entry(entry):
    _analysis_history.append(entry)
    if len(_analysis_history) > 100:
        _analysis_history[:] = _analysis_history[-100:]


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/api/analyze", methods=["POST"])
def analyze_soil():
    if "image" not in request.files:
        return jsonify({"error": "No image provided"}), 400

    file = request.files["image"]
    image_bytes = file.read()
    lat = request.form.get("lat", type=float)
    lon = request.form.get("lon", type=float)
    calibration = request.form.get("calibration", type=float, default=1.0)

    try:
        result = analyze(image_bytes, calibration_factor=calibration)
    except Exception as e:
        logger.exception("Analysis failed")
        return jsonify({"error": str(e)}), 500

    satellite = None
    biome = None
    if lat is not None and lon is not None:
        try:
            satellite = verify_location(lat, lon)
            biome = regional_avg_som(lat, lon)
        except Exception as e:
            logger.warning(f"Satellite lookup failed: {e}")

    entry = {
        "som": result["som_percent"],
        "som_rating": result["som_rating"],
        "moisture": result["moisture_index"],
        "co2e": result["co2e_per_ha_estimate"],
        "carbon_stock": result["carbon_stock_percent"],
        "satellite": satellite,
        "biome": biome,
    }
    add_history_entry(entry)

    return jsonify({
        "analysis": result,
        "satellite": satellite,
        "biome": biome,
    })


@app.route("/api/calibrate", methods=["POST"])
def calibrate():
    if "image" not in request.files:
        return jsonify({"error": "No image provided"}), 400
    known_som = request.form.get("known_som", type=float)
    if not known_som:
        return jsonify({"error": "known_som required"}), 400

    image_bytes = request.files["image"].read()
    try:
        factor = calibrate_with_known(image_bytes, known_som)
        return jsonify({"calibration_factor": factor})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/satellite", methods=["GET"])
def sat_query():
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    if lat is None or lon is None:
        return jsonify({"error": "lat and lon required"}), 400
    result = verify_location(lat, lon)
    biome = regional_avg_som(lat, lon)
    return jsonify({"satellite": result, "biome": biome})


@app.route("/api/history", methods=["GET"])
def history():
    return jsonify(get_history())
