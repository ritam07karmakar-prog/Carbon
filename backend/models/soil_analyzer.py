import cv2
import numpy as np
from PIL import Image
import io
import logging

logger = logging.getLogger(__name__)

REFERENCE_SOM_RANGES = [
    {"label": "Very Low", "range": (0.0, 1.0), "color_desc": "Pale / Light gray"},
    {"label": "Low", "range": (1.0, 2.0), "color_desc": "Light brown / Gray-brown"},
    {"label": "Moderate", "range": (2.0, 3.5), "color_desc": "Brown"},
    {"label": "High", "range": (3.5, 5.0), "color_desc": "Dark brown"},
    {"label": "Very High", "range": (5.0, 12.0), "color_desc": "Very dark brown / Black"},
]

def load_image(image_bytes):
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = np.array(img)[:, :, ::-1]
    return img

def analyze_soil_color(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    mean_bgr = cv2.mean(img)[:3]
    mean_hsv = cv2.mean(hsv)[:3]
    mean_lab = cv2.mean(lab)[:3]
    mean_val = np.mean(gray)

    b, g, r = mean_bgr
    darkness_index = (255 - mean_val) / 255.0

    return {
        "mean_bgr": {"b": round(b, 1), "g": round(g, 1), "r": round(r, 1)},
        "mean_hsv": {"h": round(mean_hsv[0], 1), "s": round(mean_hsv[1], 1), "v": round(mean_hsv[2], 1)},
        "mean_lab": {"l": round(mean_lab[0], 1), "a": round(mean_lab[1], 1), "b": round(mean_lab[2], 1)},
        "darkness_index": round(darkness_index, 3),
        "mean_gray": round(mean_val, 1),
    }

def estimate_moisture(img):
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l_channel = lab[:, :, 0]
    dark_ratio = np.sum(l_channel < 80) / l_channel.size
    saturation = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[:, :, 1]
    mean_sat = np.mean(saturation)

    moisture_score = min(dark_ratio * 1.5 + (1 - mean_sat / 255) * 0.5, 1.0)
    return round(moisture_score, 3)

def estimate_texture_roughness(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    high_freq = cv2.subtract(gray, blur)
    energy = np.std(high_freq)

    roughness = min(laplacian_var / 500 + energy / 50, 1.0)
    return round(roughness, 3), round(laplacian_var, 1), round(energy, 1)

def estimate_biomass_density(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lower_green = np.array([35, 30, 30])
    upper_green = np.array([85, 255, 255])
    green_mask = cv2.inRange(hsv, lower_green, upper_green)
    green_ratio = np.sum(green_mask > 0) / green_mask.size

    lower_brown = np.array([10, 30, 20])
    upper_brown = np.array([30, 255, 200])
    brown_mask = cv2.inRange(hsv, lower_brown, upper_brown)
    brown_ratio = np.sum(brown_mask > 0) / brown_mask.size

    ndi = (green_ratio - brown_ratio) / (green_ratio + brown_ratio + 1e-6)
    return {
        "green_cover_ratio": round(green_ratio, 3),
        "brown_cover_ratio": round(brown_ratio, 3),
        "ndi_index": round(ndi, 3),
    }

def estimate_som(color_data, moisture, biomass):
    darkness = color_data["darkness_index"]
    l = color_data["mean_lab"]["l"]
    moisture_factor = moisture
    biomass_factor = biomass["ndi_index"]

    som_raw = (darkness * 8.0) * (1 + moisture_factor * 0.3) + max(biomass_factor * 2, 0)
    som = min(som_raw, 12.0)

    for r in REFERENCE_SOM_RANGES:
        if r["range"][0] <= som < r["range"][1]:
            rating = r["label"]
            break
    else:
        rating = "Very High"

    return round(som, 2), rating

def calibrate_with_known(image_bytes, known_som):
    img = load_image(image_bytes)
    color = analyze_soil_color(img)
    moisture = estimate_moisture(img)
    biomass = estimate_biomass_density(img)
    estimated, _ = estimate_som(color, moisture, biomass)
    correction = known_som / estimated if estimated > 0 else 1.0
    return round(correction, 4)

def analyze(image_bytes, calibration_factor=1.0):
    img = load_image(image_bytes)
    if img is None:
        raise ValueError("Could not decode image")

    color = analyze_soil_color(img)
    moisture = estimate_moisture(img)
    roughness, lap, energy = estimate_texture_roughness(img)
    biomass = estimate_biomass_density(img)
    som_value, som_rating = estimate_som(color, moisture, biomass)

    som_value = round(som_value * calibration_factor, 2)
    for r in REFERENCE_SOM_RANGES:
        if r["range"][0] <= som_value < r["range"][1]:
            som_rating = r["label"]
            break

    carbon_stock = round(som_value * 0.58, 2)
    co2e_per_ha = round(carbon_stock * 3.67, 2)

    return {
        "som_percent": som_value,
        "som_rating": som_rating,
        "moisture_index": moisture,
        "texture_roughness": roughness,
        "texture_laplacian": lap,
        "texture_energy": energy,
        "carbon_stock_percent": carbon_stock,
        "co2e_per_ha_estimate": co2e_per_ha,
        "color_metrics": color,
        "biomass_metrics": biomass,
        "calibration_factor": calibration_factor,
    }
