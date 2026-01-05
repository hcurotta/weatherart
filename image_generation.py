import argparse
import base64
import json
import logging
import os
import random
import re
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import urlopen

from google import genai
from google.genai import types
import yaml

from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    IMAGE_HEIGHT,
    IMAGE_WIDTH,
    MOCKS_FILE,
    OPEN_METEO_LAT,
    OPEN_METEO_LON,
    OPEN_METEO_TIMEZONE,
    OPEN_METEO_URL,
    OUTPUT_DIR,
    PROMPTS_FILE,
)
from logging_utils import setup_logging

# Usage:
#   uv run python image_generation.py
#   uv run python image_generation.py --prompt-id sydney-nolan
#   uv run python image_generation.py --mock-id clear_summer_day
#   uv run python image_generation.py --log-level DEBUG --log-file logs.txt


def _fetch_open_meteo():
    params = {
        "latitude": OPEN_METEO_LAT,
        "longitude": OPEN_METEO_LON,
        "hourly": "temperature_2m,precipitation,cloud_cover",
        "timezone": OPEN_METEO_TIMEZONE,
    }
    url = f"{OPEN_METEO_URL}?{urlencode(params)}"
    with urlopen(url, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _select_remaining_hours(hourly, now_local):
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    precip = hourly.get("precipitation", [])
    clouds = hourly.get("cloud_cover", [])

    hours = []
    today = now_local.date()
    for idx, ts in enumerate(times):
        try:
            dt = datetime.fromisoformat(ts)
        except ValueError:
            continue
        if dt.date() != today or dt < now_local:
            continue
        hours.append(
            {
                "dt": dt,
                "temp": temps[idx] if idx < len(temps) else None,
                "precip": precip[idx] if idx < len(precip) else None,
                "cloud": clouds[idx] if idx < len(clouds) else None,
            }
        )

    if hours:
        return hours

    for idx, ts in enumerate(times):
        try:
            dt = datetime.fromisoformat(ts)
        except ValueError:
            continue
        if dt.date() != today:
            continue
        hours.append(
            {
                "dt": dt,
                "temp": temps[idx] if idx < len(temps) else None,
                "precip": precip[idx] if idx < len(precip) else None,
                "cloud": clouds[idx] if idx < len(clouds) else None,
            }
        )

    return hours


def _describe_cloud_cover(cloud_cover):
    if cloud_cover is None:
        return "unknown cloud cover"
    if cloud_cover < 20:
        return "clear skies"
    if cloud_cover < 40:
        return "mostly clear skies"
    if cloud_cover < 60:
        return "partly cloudy skies"
    if cloud_cover < 80:
        return "mostly cloudy skies"
    return "overcast skies"


def _describe_precipitation(precip_mm):
    if precip_mm is None:
        return "unknown rainfall"
    if precip_mm < 0.1:
        return "no rain"
    if precip_mm < 0.5:
        return "very light rain"
    if precip_mm < 2:
        return "light rain"
    if precip_mm < 5:
        return "moderate rain"
    return "heavy rain"


def _summarize_segment(segment):
    clouds = [hour["cloud"] for hour in segment if hour["cloud"] is not None]
    precip = [hour["precip"] for hour in segment if hour["precip"] is not None]

    avg_cloud = sum(clouds) / len(clouds) if clouds else None
    avg_precip = sum(precip) / len(precip) if precip else None
    start_time = segment[0]["dt"].strftime("%H:%M")
    end_time = segment[-1]["dt"].strftime("%H:%M")

    return {
        "start_time": start_time,
        "end_time": end_time,
        "cloud_desc": _describe_cloud_cover(avg_cloud),
        "precip_desc": _describe_precipitation(avg_precip),
    }


def _build_segments(hours, segment_count=8):
    if not hours:
        return []
    segments = []
    total = len(hours)
    for idx in range(segment_count):
        start = int(idx * total / segment_count)
        end = int((idx + 1) * total / segment_count)
        if start >= total:
            start = total - 1
        if end <= start:
            end = min(total, start + 1)
        segments.append(_summarize_segment(hours[start:end]))
    return segments


def _format_segments_summary(segments):
    lines = []
    for idx, segment in enumerate(segments, start=1):
        lines.append(
            (
                f"{idx}) {segment['start_time']}-{segment['end_time']}: "
                f"{segment['cloud_desc']}, {segment['precip_desc']}"
            )
        )
    return " | ".join(lines)


def _build_prompt_context():
    data = _fetch_open_meteo()
    hourly = data.get("hourly", {})
    now_local = datetime.now()
    hours = _select_remaining_hours(hourly, now_local)
    if not hours:
        raise RuntimeError("No hourly data returned from Open-Meteo")

    temps = [hour["temp"] for hour in hours if hour["temp"] is not None]
    temp_min = str(int(round(min(temps)))) if temps else ""
    temp_max = str(int(round(max(temps)))) if temps else ""
    temp_range = f"{temp_min}-{temp_max} deg" if temp_min and temp_max else "unknown"

    segments = _build_segments(hours, segment_count=8)
    segments_summary = _format_segments_summary(segments)

    return {
        "width": IMAGE_WIDTH,
        "height": IMAGE_HEIGHT,
        "temp_min": temp_min,
        "temp_max": temp_max,
        "temp_range": temp_range,
        "segments_summary": segments_summary,
        "date": now_local.strftime("%Y-%m-%d"),
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
