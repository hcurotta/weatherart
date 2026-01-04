import os

from dotenv import load_dotenv

load_dotenv()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_TV_IP = os.getenv("WEATHERART_TV_IP", "192.168.200.200")
DEFAULT_TIMEOUT_S = int(os.getenv("WEATHERART_TIMEOUT_S", "15"))
DEFAULT_UPLOAD_TIMEOUT_S = int(os.getenv("WEATHERART_UPLOAD_TIMEOUT_S", "25"))
TV_MAC = os.getenv("WEATHERART_TV_MAC")
DEFAULT_WOL_PORT = int(os.getenv("WEATHERART_WOL_PORT", "9"))
DEFAULT_WOL_BROADCAST = os.getenv("WEATHERART_WOL_BROADCAST", "255.255.255.255")
DEFAULT_WOL_WAIT_S = int(os.getenv("WEATHERART_WOL_WAIT_S", "8"))
MY_PICTURES_CATEGORY = os.getenv("WEATHERART_CATEGORY", "MY-C0002")

LAST_ID_FILE = os.path.join(SCRIPT_DIR, "last_uploaded_id.txt")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "generated")
PROMPTS_FILE = os.path.join(SCRIPT_DIR, "prompts.yaml")
MOCKS_FILE = os.path.join(SCRIPT_DIR, "weather_mocks.yaml")

BOM_URL = os.getenv(
    "WEATHERART_BOM_URL",
    "ftp://ftp.bom.gov.au/anon/gen/fwo/IDN11060.xml",
)
AREA_NAME = os.getenv("WEATHERART_AREA_NAME", "Sydney")

IMAGE_WIDTH = int(os.getenv("WEATHERART_IMAGE_WIDTH", "3840"))
IMAGE_HEIGHT = int(os.getenv("WEATHERART_IMAGE_HEIGHT", "2160"))
IMAGE_PATH_OVERRIDE = os.getenv("WEATHERART_IMAGE_PATH")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-pro-image-preview")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
