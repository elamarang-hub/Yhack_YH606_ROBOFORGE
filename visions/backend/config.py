import os

try:
    from dotenv import load_dotenv
    # Load .env from project root
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))
except ImportError:
    pass

CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", 0))
FACE_MATCH_THRESHOLD = float(os.getenv("FACE_MATCH_THRESHOLD", 0.45))
ALERT_COOLDOWN = int(os.getenv("ALERT_COOLDOWN", 15))
ALARM_TIMEOUT = int(os.getenv("ALARM_TIMEOUT", 5))

MODE = os.getenv("MODE", "individual")

TOF_ZONE_THRESHOLD_INDIVIDUAL = float(os.getenv("TOF_ZONE_THRESHOLD_INDIVIDUAL", 1200))
TOF_ZONE_THRESHOLD_APARTMENT = float(os.getenv("TOF_ZONE_THRESHOLD_APARTMENT", 500))

TOF_DWELL_INDIVIDUAL = float(os.getenv("TOF_DWELL_INDIVIDUAL", 2.0))
TOF_DWELL_APARTMENT = float(os.getenv("TOF_DWELL_APARTMENT", 3.0))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_OWNER_CHAT_ID = os.getenv("TELEGRAM_OWNER_CHAT_ID", "")

ESP32_WS_PORT = int(os.getenv("ESP32_WS_PORT", 8001))

AUDIO_DIR = os.getenv("AUDIO_DIR", os.path.join(os.path.dirname(__file__), "audio"))
DEFAULT_GREETING_PATH = os.getenv("DEFAULT_GREETING_PATH", os.path.join(AUDIO_DIR, "greeting.wav"))

# Ensure audio dir exists
os.makedirs(AUDIO_DIR, exist_ok=True)
