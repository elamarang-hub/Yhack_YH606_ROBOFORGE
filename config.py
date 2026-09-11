import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent
PHOTOS_DIR = BASE_DIR / "photos"
RECORDINGS_DIR = BASE_DIR / "recordings"
KNOWN_FACES_DIR = BASE_DIR / "known_faces"
SOUNDS_DIR = BASE_DIR / "sounds"
DB_PATH = BASE_DIR / "database" / "visitors.db"

for p in [PHOTOS_DIR, RECORDINGS_DIR, KNOWN_FACES_DIR, SOUNDS_DIR, DB_PATH.parent]:
    p.mkdir(parents=True, exist_ok=True)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ESP32_PORT = os.getenv("ESP32_PORT", "COM6")
ESP32_BAUD = int(os.getenv("ESP32_BAUD", "115200"))

CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "1"))
YOLO_CONFIDENCE = float(os.getenv("YOLO_CONFIDENCE", "0.50"))

# --- Identity model (YuNet face detector + SFace face recognizer, ONNX) ---
# These are the trained model files supplied for the hackathon. They are used
# ONLY for the OWNER/STRANGER identity decision after a HIGH ALERT is raised;
# person presence detection still uses YOLO (PersonDetector) above.
MODELS_DIR = BASE_DIR / "models"
FACE_DETECTOR_MODEL = str(MODELS_DIR / "face_detection_yunet_2023mar.onnx")
FACE_RECOGNIZER_MODEL = str(MODELS_DIR / "face_recognition_sface_2021dec.onnx")
RESIDENT_GALLERY_PATH = MODELS_DIR / "resident_gallery.npy"

# Confidence threshold for the OWNER decision. This is the same value the
# trained model's own reference implementation (test_doorbell.py) uses for
# its "KNOWN" (owner) cutoff: top-3 cosine similarity >= 0.50.
# Safety rule: anything below this threshold (including the model's own
# "uncertain" band down to 0.44) is treated as STRANGER, never as OWNER.
OWNER_CONFIDENCE_THRESHOLD = float(os.getenv("OWNER_CONFIDENCE_THRESHOLD", "0.50"))

INDIVIDUAL_DISTANCE_CM = float(os.getenv("INDIVIDUAL_DISTANCE_CM", "120"))
INDIVIDUAL_DWELL_SECONDS = float(os.getenv("INDIVIDUAL_DWELL_SECONDS", "2"))
APARTMENT_DISTANCE_CM = float(os.getenv("APARTMENT_DISTANCE_CM", "50"))
APARTMENT_DWELL_SECONDS = float(os.getenv("APARTMENT_DWELL_SECONDS", "3"))

ALERT_COOLDOWN_SECONDS = float(os.getenv("ALERT_COOLDOWN_SECONDS", "15"))
VISITOR_RECORD_SECONDS = max(5, min(15, int(os.getenv("VISITOR_RECORD_SECONDS", "5"))))

YOLO_MODEL = "yolov8n.pt"
GREETING_WAV = SOUNDS_DIR / "greeting.wav"
STREAM_HOST = "0.0.0.0"
STREAM_PORT = 8000
