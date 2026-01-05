import argparse
import base64
import logging
import os
import random
import re
from datetime import datetime
from urllib.request import urlopen
import xml.etree.ElementTree as ET

from google import genai
from google.genai import types
import yaml

from config import (
    AREA_NAME,
    BOM_URL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    IMAGE_HEIGHT,
    IMAGE_WIDTH,
    MOCKS_FILE,
    OUTPUT_DIR,
    PROMPTS_FILE,
)
from logging_utils import setup_logging

# Usage:
#   uv run python image_generation.py
#   uv run python image_generation.py --prompt-id sydney-nolan
#   uv run python image_generation.py --mock-id clear_summer_day
#   uv run python image_generation.py --log-level DEBUG --log-file logs.txt


def _fetch_bom_xml():
    with urlopen(BOM_URL, timeout=20) as response:
        return response.read()


def _find_area(root, area_name):
    target = area_name.strip().lower()
    for area in root.iter("area"):
        if area.get("description", "").strip().lower() == target:
            return area
    return None


def _get_forecast_period(area):
    periods = list(area.findall(".//forecast-period"))
    for desired in ("0", "1"):
        for period in periods:
            if period.get("index") == desired:
                return period
    return periods[0] if periods else None


def _get_text_by_type(period, tag, type_value):
    for node in period.findall(tag):
        if node.get("type") == type_value and node.text:
            return node.text.strip()
    return ""


def _find_first_element_text(area, type_value):
    for node in area.findall(".//element"):
        if node.get("type") == type_value and node.text:
            return node.text.strip()
    return ""


def _build_prompt_context():
    xml_data = _fetch_bom_xml()
    root = ET.fromstring(xml_data)
    area = _find_area(root, AREA_NAME)
    if area is None:
        raise RuntimeError(f"Area not found in BOM XML: {AREA_NAME}")

    period = _get_forecast_period(area)
    if period is None:
        raise RuntimeError(f"No forecast periods found for area: {AREA_NAME}")

    temp_min = _get_text_by_type(period, "element", "air_temperature_minimum")
    temp_max = _get_text_by_type(period, "element", "air_temperature_maximum")
    if not temp_min:
        temp_min = _find_first_element_text(area, "air_temperature_minimum")
    if not temp_max:
        temp_max = _find_first_element_text(area, "air_temperature_maximum")
    forecast = _get_text_by_type(period, "text", "forecast")
    if not forecast:
        forecast = _get_text_by_type(period, "text", "precis")
    if temp_min and temp_max:
        temp_range = f"{temp_min}-{temp_max} deg"
    else:
        temp_range = "unknown"

    return {
        "width": IMAGE_WIDTH,
        "height": IMAGE_HEIGHT,
        "temp_min": temp_min,
        "temp_max": temp_max,
        "temp_range": temp_range,
        "forecast": forecast,
        "date": datetime.now().strftime("%Y-%m-%d"),
    }


def _load_prompt_templates():
    with open(PROMPTS_FILE, "r") as f:
        data = yaml.safe_load(f) or {}

    prompts = data.get("prompts", [])
    if not prompts:
        raise RuntimeError("No prompts found in prompts.yaml")
    return prompts


def _load_weather_mocks():
    if not os.path.exists(MOCKS_FILE):
        raise RuntimeError("weather_mocks.yaml not found")
    with open(MOCKS_FILE, "r") as f:
        data = yaml.safe_load(f) or {}
    return data.get("conditions", [])


def _get_mock_context(mock_id):
    if not mock_id:
        return None
    conditions = _load_weather_mocks()
    for condition in conditions:
        if condition.get("id") == mock_id:
            return condition
    raise RuntimeError(f"Mock id not found: {mock_id}")


def _render_template(template, context):
    def repl(match):
        key = match.group(1).strip()
        return str(context.get(key, ""))

    return re.sub(r"{{\s*([a-zA-Z0-9_]+)\s*}}", repl, template)


def _pick_prompt(prompts, prompt_id):
    if not prompt_id:
        return random.choice(prompts)
    for prompt in prompts:
        if prompt.get("id") == prompt_id:
            return prompt
    raise RuntimeError(f"Prompt id not found: {prompt_id}")


def build_prompt_text(prompt_id=None, mock_id=None):
    prompts = _load_prompt_templates()
    prompt = _pick_prompt(prompts, prompt_id)
    template = prompt.get("template", "")
    if not template:
        raise RuntimeError("Prompt template is missing")

    context = _get_mock_context(mock_id) or _build_prompt_context()
    return _render_template(template, context)


def write_prompt_file(prompt_text, timestamp):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    prompt_path = os.path.join(OUTPUT_DIR, f"{timestamp}.txt")
    with open(prompt_path, "w") as f:
        f.write(prompt_text)
    return prompt_path


def _extract_image_bytes(response):
    for candidate in getattr(response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            inline = getattr(part, "inline_data", None)
            if not inline:
                continue
            data = getattr(inline, "data", None)
            if not data:
                continue
            if isinstance(data, bytes):
                return data, getattr(inline, "mime_type", None)
            if isinstance(data, str):
                try:
                    return base64.b64decode(data), getattr(inline, "mime_type", None)
                except (ValueError, TypeError):
                    continue
    return None, None


def generate_image(prompt_text, timestamp):
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY is not set")

    client = genai.Client(api_key=GEMINI_API_KEY)
    config = types.GenerateContentConfig(
        response_modalities=[types.Modality.IMAGE],
        image_config=types.ImageConfig(image_size="4K", aspect_ratio="16:9"),
    )
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt_text,
        config=config,
    )

    image_bytes, mime_type = _extract_image_bytes(response)
    if not image_bytes:
        raise RuntimeError("No image data returned from Gemini")

    ext = ".png"
    if mime_type == "image/jpeg":
        ext = ".jpg"

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    image_path = os.path.join(OUTPUT_DIR, f"{timestamp}{ext}")
    with open(image_path, "wb") as f:
        f.write(image_bytes)
    return image_path


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Generate a weather-based image prompt and image.",
        epilog=(
            "Examples:\n"
            "  uv run python image_generation.py\n"
            "  uv run python image_generation.py --prompt-id sydney-nolan\n"
            "  uv run python image_generation.py --mock-id clear_summer_day\n"
            "  uv run python image_generation.py --log-level DEBUG\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--prompt-id",
        help="Prompt id to use from prompts.yaml (default: random).",
    )
    parser.add_argument(
        "--mock-id",
        help="Weather mock id to use from weather_mocks.yaml.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (default: INFO).",
    )
    parser.add_argument(
        "--log-file",
        help="Optional log file path. When set, logs are written to this file too.",
    )
    return parser.parse_args()


def main():
    args = _parse_args()
    setup_logging(args.log_level, args.log_file)
    logger = logging.getLogger(__name__)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prompt_text = build_prompt_text(
        prompt_id=args.prompt_id,
        mock_id=args.mock_id,
    )
    prompt_path = write_prompt_file(prompt_text, timestamp)
    logger.info("Prompt saved to %s", prompt_path)

    image_path = generate_image(prompt_text, timestamp)
    logger.info("Generated image saved to %s", image_path)


if __name__ == "__main__":
    main()
