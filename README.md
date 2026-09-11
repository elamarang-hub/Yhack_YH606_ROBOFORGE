# Smart Door Security System — Complete Hackathon Build

Complete target pipeline:
USB Webcam -> YOLOv8n -> ToF zone/dwell -> Face Recognition -> Visitor/Event ID
-> Telegram photo alert -> greeting -> visitor microphone recording -> Telegram
-> owner voice/text -> speaker -> ESP32 active buzzer -> history/passive logs
-> FastAPI live stream.

Actual hardware setup:
- Laptop = edge AI/application host
- USB webcam = camera index 1
- ESP32 = sensor/controller
- VL53L0X ToF
- Active buzzer
- USB microphone
- Speaker

Camera index 0 is intentionally NOT used.

Thresholds:
- Individual: <120 cm and >=2 seconds
- Apartment: <50 cm and >=3 seconds

HIGH ALERT requires camera person detection + ToF in-zone + dwell threshold.

Visual colors:
- Yellow = SEARCHING
- Green = KNOWN
- Red = UNKNOWN

IDs:
- VISITOR_001 etc. = person IDs
- EVT_0001 etc. = event IDs

Telegram:
 /start
 /test
 /alarm
 /mode
 /mode individual
 /mode apartment
 /history
 /rename VISITOR_001 Ravi
 /endcall

Voice from owner is downloaded, converted OGG->WAV with FFmpeg and played.
Owner text is converted to speech with pyttsx3.
After a HIGH ALERT, greeting plays, visitor voice is recorded for 5 seconds,
then sent to Telegram with the visitor photo.

## Setup

Recommended on Windows: Python 3.11 for face_recognition/dlib compatibility.

    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt

Copy `.env.example` to `.env` and fill your bot token, chat ID and ESP32 COM port.
Never upload `.env`.

Check:

    python setup_check.py
    ffmpeg -version

## ESP32

Install Adafruit VL53L0X in Arduino IDE.
Open `esp32/esp32.ino`, select your ESP32 board/COM port and upload.

Typical classic ESP32 DevKit wiring:
VL53L0X SDA -> GPIO21
VL53L0X SCL -> GPIO22
VL53L0X GND -> GND
VL53L0X VCC -> documented sensor supply

Active buzzer module:
SIG -> GPIO26
GND -> GND
VCC -> module's documented supply

Do not drive a high-current bare buzzer directly from GPIO.

Test serial:

    python esp32/esp32_test.py COM5

Expected PONG and DIST:mm.

## Run complete system

    python main.py

Live stream:
http://127.0.0.1:8000/api/live

Status:
http://127.0.0.1:8000/api/status

Press Q in the OpenCV window to stop.


## Multi-turn intercom behavior

HIGH ALERT starts a conversation:
visitor records -> owner receives voice -> owner replies by voice/text
-> owner response plays at the door -> visitor records again -> owner receives
the next voice -> repeat until `/endcall`.

The recording is intentionally limited to 5–15 seconds per turn.

## What is automatic vs manual

Automatic:
- USB webcam person detection
- ToF zone/dwell fusion
- face recognition at HIGH ALERT
- known/unknown classification
- visitor/event IDs
- photo capture
- Telegram alert
- greeting
- visitor voice capture
- buzzer
- owner reply playback
- multi-turn visitor recording

Manual:
- `/mode` changes mode
- `/rename` changes visitor display name
- `/alarm` manually activates buzzer
- `/endcall` ends intercom
