## 🌤️ WeatherArt for Samsung Frame
WeatherArt is an automated script that generates daily weather-inspired artwork for the Samsung Frame TV. It is designed as an experiment in Calm Technology—replacing dashboard widgets with ambient visualization.

### How it Works
- **Fetch:** Runs every morning to grab local weather data.
- **Generate:** Uses Google Gemini Nano Banana to generate a prompt-based image (defined in prompts.yaml) reflecting the current weather conditions.
- **Embed:** Subtly embeds the min/max temperature range into the image pixels, making the data visible only when you look for it.
- **Display:** Uploads the final piece to the Frame TV via the local API.

## Inspiration
Inspired by Max Braun's Accent.ink, this project aims to make the "smart home" feel less like a computer and more like a home.

## Features
- Weather-driven prompt generation (BOM XML).
- Optional mock weather data for testing.
- Image generation via Gemini.
- Upload/replace images on a Samsung Frame TV.
- Logging and CLI flags for production use.

---

## Requirements
- macOS (tested workflow on Mac mini).
- A Samsung Frame TV on the same network.
- Python 3.11+ (for local development and venv runtime).
- A Gemini API key with image generation access.

---

## Quick Start (self-contained venv)

This approach does not require `uv` on the target machine.

1) Clone the repo
```
git clone <your-repo-url>
cd weatherart/tv
```

2) Create a virtual environment
```
python3 -m venv .venv
```

3) Activate it
```
source .venv/bin/activate
```

4) Install dependencies
```
pip install -r requirements.txt
```

5) Create a `.env` file
```
cp .env.example .env
```

6) Edit `.env`
- Add `GEMINI_API_KEY`.
- Set `WEATHERART_TV_IP` to your TV IP.

7) Run the main script
```
python main.py
```

---

## Configuration

Configuration is via `.env` or environment variables. Defaults are in `config.py`.

Key variables:
- `GEMINI_API_KEY` (required)
- `WEATHERART_TV_IP` (recommended)
- `WEATHERART_TV_MAC` (optional, used to resolve IP via ARP)
- `WEATHERART_WOL_PORT` (default: 9)
- `WEATHERART_WOL_BROADCAST` (default: 255.255.255.255)
- `WEATHERART_WOL_WAIT_S` (default: 8)
- `WEATHERART_TIMEOUT_S`
- `WEATHERART_UPLOAD_TIMEOUT_S`
- `WEATHERART_CATEGORY` (defaults to `MY-C0002`)
- `WEATHERART_BOM_URL` (defaults to BOM IDN11060)
- `WEATHERART_AREA_NAME` (defaults to `Sydney`)
- `WEATHERART_IMAGE_PATH` (fallback local image)
- `GEMINI_MODEL` (default `gemini-3-pro-image-preview`)

Example `.env`:
```
GEMINI_API_KEY=your-key-here
WEATHERART_TV_IP=192.168.200.200
WEATHERART_AREA_NAME=Sydney
```

---

## Scripts

### 1) Generate + Upload (main)
```
python main.py
```

Options:
- `--prompt-id <id>`: choose a prompt from `prompts.yaml`
- `--ip <ip>`: override TV IP
- `--mac <mac>`: TV MAC address for resolving IP
- `--matte <matte>`: default `none`
- `--wake`: send Wake-on-LAN packet before connecting
- `--wake-broadcast <addr>`: broadcast address for WOL
- `--wake-port <port>`: UDP port for WOL
- `--wake-wait <seconds>`: wait after WOL before connecting
- `--timeout <seconds>`: connection timeout
- `--upload-timeout <seconds>`: upload timeout
- `--log-level <LEVEL>`: INFO, DEBUG, etc
- `--log-file <path>`: log file output

Example:
```
python main.py --prompt-id sydney-nolan-classic --log-level DEBUG
```

### 2) Generate Image Only
```
python image_generation.py
```

Options:
- `--prompt-id <id>`: choose a prompt
- `--mock-id <id>`: use mock weather data from `weather_mocks.yaml`
- `--log-level <LEVEL>`
- `--log-file <path>`

Example:
```
python image_generation.py --mock-id clear_summer_day --log-level DEBUG
```

### 3) Upload a Specific Image
```
python push_image.py ./path/to/image.png
```

Options:
- `--replace-last`: delete previously uploaded image after selecting new one
- `--ip <ip>`
- `--mac <mac>`
- `--matte <matte>`
- `--wake`
- `--wake-broadcast <addr>`
- `--wake-port <port>`
- `--wake-wait <seconds>`
- `--timeout <seconds>`
- `--upload-timeout <seconds>`
- `--log-level <LEVEL>`
- `--log-file <path>`

Example:
```
python push_image.py ./generated/20260101_120000.png --replace-last
```

### 4) Remove Today’s Images
```
python remove_today.py
```

Options:
- `--category <id>`: filter category (default: My Photos)
- `--ip <ip>`
- `--mac <mac>`
- `--wake`
- `--wake-broadcast <addr>`
- `--wake-port <port>`
- `--wake-wait <seconds>`
- `--timeout <seconds>`
- `--log-level <LEVEL>`
- `--log-file <path>`

---

## Prompts

`prompts.yaml` contains a list of prompt templates. Each template can reference these variables:
- `{{width}}`, `{{height}}`
- `{{temp_min}}`, `{{temp_max}}`, `{{temp_range}}`
- `{{forecast}}`
- `{{date}}`

---

## Weather Mocks

`weather_mocks.yaml` provides reusable mock conditions for testing prompt generation without hitting the BOM feed.

Use:
```
python image_generation.py --mock-id clear_summer_day
```

---

## Scheduling (macOS)

Use `launchd` for production scheduling on a Mac mini.

Example LaunchAgent (`~/Library/LaunchAgents/com.weatherart.tv.plist`):
```
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.weatherart.tv</string>
    <key>ProgramArguments</key>
    <array>
      <string>/Users/youruser/weatherart/tv/.venv/bin/python</string>
      <string>/Users/youruser/weatherart/tv/main.py</string>
      <string>--log-file</string>
      <string>/Users/youruser/weatherart/tv/logs/weatherart.log</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
      <key>Hour</key>
      <integer>7</integer>
      <key>Minute</key>
      <integer>0</integer>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/youruser/weatherart/tv/logs/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/youruser/weatherart/tv/logs/stderr.log</string>
  </dict>
</plist>
```

Load it:
```
launchctl load ~/Library/LaunchAgents/com.weatherart.tv.plist
```

---

## Troubleshooting

- If you see `Connection refused`, verify the TV IP and that the TV is on the same network.
- The first connection may require you to approve access on the TV.
- If image generation fails, verify the Gemini API key has image access.

---

## License

MIT.
