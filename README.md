# Smart Door Security System

## Overview

Smart Door Security is an edge-AI and IoT based security system designed to monitor a doorstep, identify visitors, and alert the owner through Telegram.

The system combines:

- A separate USB webcam for continuous visual monitoring
- YOLOv8n for person detection
- Face recognition for known/unknown visitor identification
- ESP32 for sensor-side processing and hardware control
- VL53L0X ToF sensor for distance and dwell-time confirmation
- Telegram bot for remote alerts and owner control
- Two-way voice communication between the owner and the doorstep
- Active buzzer for local alerting
- FastAPI live video streaming

The main idea is sensor fusion: a Telegram security alert is generated only when a person is detected by the camera and the ToF sensor confirms that the person is inside the configured detection zone for the required dwell time.

---

## System Architecture

```text
                    ┌──────────────────────┐
                    │     USB Webcam       │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │     YOLOv8n          │
                    │  Person Detection    │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │   Face Recognition   │
                    │ Known / Unknown       │
                    └──────────┬───────────┘
                               │
                               │
┌─────────────────┐            ▼
│ VL53L0X ToF     │──────► Sensor Fusion
│ Distance/Dwell  │            │
└────────┬────────┘            ▼
         │             ┌──────────────────┐
         │             │  State Machine   │
         │             │ PASSIVE          │
         │             │ DWELL CHECK      │
         │             │ HIGH ALERT       │
         │             └────────┬─────────┘
         │                      │
         ▼                      ▼
┌─────────────────┐     ┌──────────────────┐
│      ESP32      │     │  Telegram Bot    │
│ Sensor + Buzzer │     │ Alert + Control  │
└─────────────────┘     └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ Owner Smartphone │
                         └────────┬─────────┘
                                  │
                           Voice / Text Reply
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ Laptop Speaker   │
                         └──────────────────┘
```

---

## Core Detection Logic

The system has three main security states.

### 1. PASSIVE

The camera continuously runs person detection and the ESP32 continuously provides ToF distance information.

No Telegram push alert is generated.

The system can log the observation for history and monitoring.

### 2. DWELL CHECK

This state begins when:

```text
Person detected by camera
        AND
Person is inside configured ToF zone
```

The system starts measuring how long the person remains in the zone.

### 3. HIGH ALERT

A high alert is generated only when:

```text
Person detected
        AND
ToF distance is inside the configured zone
        AND
Required dwell time is reached
```

Face recognition determines whether the visitor is known or unknown.

The owner receives a Telegram alert containing the visitor information and a photo.

---

## Security Modes

### Individual House Mode

```text
Detection distance: < 120 cm
Required dwell time: > 2 seconds
```

This mode is intended for an individual house where a visitor approaching the door should be considered relevant.

### Apartment Mode

```text
Detection distance: < 50 cm
Required dwell time: > 3 seconds
```

This mode is stricter to reduce alerts caused by neighbours and people simply walking past the door.

The Telegram command can be used to change the mode:

```text
/mode individual
/mode apartment
```

---

## Visitor Identification

The project uses unique visitor IDs.

Example:

```text
VISITOR_001
VISITOR_002
VISITOR_003
```

Known visitors have a name associated with their visitor ID.

Example:

```text
Visitor ID: VISITOR_001
Name: Abidesh
Status: KNOWN
```

Unknown visitors are initially represented as:

```text
Visitor ID: VISITOR_002
Name: Unknown
Status: UNKNOWN
```

Security events also receive unique event IDs:

```text
EVT_0001
EVT_0002
EVT_0003
```

This allows individual visitor identities and individual security events to be tracked separately.

---

## Visual Status Overlay

The planned camera interface uses three visual states:

### Yellow — SEARCHING

A person has been detected and face recognition is being performed.

### Green — KNOWN

The face matches a registered visitor.

The display can show:

```text
KNOWN
Name: Abidesh
ID: VISITOR_001
```

### Red — UNKNOWN

The face does not match a registered visitor.

The display can show:

```text
UNKNOWN
ID: VISITOR_002
```

The live display can also show:

- Distance
- Dwell time
- Security mode
- Current state
- Alert status

---

## Telegram Features

The Telegram bot is the remote control interface for the system.

Implemented/tested commands include:

```text
/start
/test
/alarm
/mode
/history
/addknown
/addunknown
/addevent
/testalert
/testunknownalert
/testcooldown
```

### `/start`

Displays the bot connection status and available commands.

### `/test`

Tests Telegram communication.

### `/alarm`

Triggers the alarm/buzzer command interface.

### `/mode`

Displays the current security mode.

It can also change the mode:

```text
/mode individual
/mode apartment
```

### `/history`

Displays recent security events.

Each event can contain:

```text
Event ID
Visitor
Time
Distance
Dwell
Status
```

### `/addknown`

Creates a known visitor record.

Example:

```text
/addknown Abidesh
```

### `/addunknown`

Creates an unknown visitor record.

### `/testalert`

Tests a known visitor alert with a photo.

### `/testunknownalert`

Tests an unknown visitor alert with a photo.

### `/testcooldown`

Tests the alert cooldown system.

---

## Telegram Alert Format

### Known Visitor

Example:

```text
🟢 KNOWN VISITOR ALERT

👤 Name: Abidesh
🆔 Visitor ID: VISITOR_001
🆔 Event ID: EVT_0001

📏 Distance: 82 cm
⏱ Dwell: 3.2 sec
📌 Status: HIGH ALERT
```

A visitor photo is attached to the alert.

### Unknown Visitor

Example:

```text
🔴 UNKNOWN VISITOR ALERT

👤 Visitor ID: VISITOR_002
🆔 Event ID: EVT_0002

📏 Distance: 45 cm
⏱ Dwell: 3.5 sec
📌 Status: HIGH ALERT
```

A visitor photo is attached to the alert.

---

## Alert Cooldown

A cooldown prevents repeated Telegram alerts while the same visitor remains at the door.

Current test configuration:

```text
Cooldown: 10 seconds
```

The cooldown is checked before sending an alert.

This prevents notification spam.

---

## Two-Way Voice Communication

The system supports owner-to-door voice communication.

### Owner → Door

The owner sends a Telegram voice message.

The laptop:

1. Receives the Telegram voice message
2. Downloads the `.ogg` file
3. Converts it to WAV using FFmpeg
4. Plays the WAV through the configured speaker

The owner voice communication has been tested successfully.

The current tested workflow produces messages such as:

```text
🎤 Voice message received!
💾 Voice saved as owner_voice.ogg
🔄 Voice converted from OGG to WAV
🔊 Playing owner voice...
✅ Voice playback completed.
```

### Visitor → Owner

The planned reverse communication path is:

```text
Visitor microphone
       ↓
Laptop records audio
       ↓
Audio saved
       ↓
Telegram voice message
       ↓
Owner smartphone
```

The communication can support multiple turns.

---

## Hardware

Current hardware architecture:

- Laptop for edge-AI inference and system control
- Separate USB webcam
- ESP32 development board
- VL53L0X Time-of-Flight distance sensor
- Active buzzer
- USB microphone
- Speaker
- USB cable / serial communication
- Breadboard and jumper wires
- Suitable power supply

The ESP32 is used for sensor-side operations and buzzer control.

The laptop performs the computationally heavier vision and AI tasks.

---

## Software Stack

### Python

Main application language.

### OpenCV

Used for webcam capture and image processing.

### YOLOv8n

Used for real-time person detection.

### Face Recognition

Used to compare detected faces with registered visitors.

### FastAPI + Uvicorn

Used for the live camera API/server.

### Telegram Bot API

Used for:

- Security alerts
- Photos
- Voice communication
- Commands
- History
- Mode control

### PySerial

Used for laptop ↔ ESP32 serial communication.

### Pygame

Used for audio playback.

### FFmpeg

Used to convert Telegram OGG/Opus voice messages into WAV audio suitable for playback.

### pyttsx3

Used for converting owner text replies into speech.

### SQLite

Used for persistent security history and visitor/event records.

---

## Suggested Project Structure

```text
SMART_DOOR_SECURITY/
│
├── main.py
├── config.py
├── requirements.txt
├── README.md
│
├── telegram/
│   ├── __init__.py
│   ├── bot.py
│   ├── commands.py
│   ├── alerts.py
│   └── voice.py
│
├── esp32/
│   ├── esp32.ino
│   └── serial_controller.py
│
├── vision/
│   ├── camera.py
│   ├── yolo_detector.py
│   ├── face_recognition.py
│   └── visual_overlay.py
│
├── security/
│   ├── fusion.py
│   ├── state_machine.py
│   └── cooldown.py
│
├── database/
│   ├── database.py
│   └── visitors.db
│
├── audio/
│   ├── audio_manager.py
│   ├── recorder.py
│   ├── player.py
│   └── tts.py
│
├── web/
│   ├── server.py
│   └── live_stream.py
│
├── photos/
├── recordings/
├── sounds/
│   └── greeting.wav
│
└── tests/
    ├── test_telegram.py
    ├── test_esp32.py
    ├── test_camera.py
    └── test_tof.py
```

---

## System Workflow

```text
1. System starts
        ↓
2. USB webcam starts
        ↓
3. YOLO continuously detects people
        ↓
4. ESP32 reads VL53L0X distance
        ↓
5. Person + distance are combined
        ↓
6. If outside zone → PASSIVE
        ↓
7. If inside zone → DWELL CHECK
        ↓
8. Required dwell time reached?
        ↓
9. Yes → Face recognition
        ↓
10. Known or Unknown
        ↓
11. Capture visitor photo
        ↓
12. Create Visitor ID / Event ID
        ↓
13. Send Telegram alert
        ↓
14. Trigger local buzzer if configured
        ↓
15. Begin owner/visitor communication
        ↓
16. Apply cooldown
```

---

## Development and Testing Progress

The following parts have already been tested during development:

- Telegram bot connection
- Telegram `/start`
- Telegram communication test
- Known visitor alert
- Unknown visitor alert
- Photo attachment to Telegram alert
- Event IDs
- Visitor IDs
- Security history
- Individual/apartment mode commands
- Alert cooldown
- Telegram voice reception
- OGG voice download
- OGG → WAV conversion using FFmpeg
- WAV audio playback

Next integration stages are:

1. Test separate USB webcam with OpenCV
2. Integrate YOLOv8n person detection
3. Add face recognition
4. Add visual bounding-box states
5. Test ESP32 serial communication
6. Integrate VL53L0X ToF
7. Implement dwell-time logic
8. Combine camera + ToF using sensor fusion
9. Connect real detection pipeline to Telegram alerts
10. Add visitor microphone recording
11. Complete visitor → owner voice communication
12. Add text → speech owner response
13. Integrate FastAPI live stream
14. Final end-to-end demonstration

---

## Security and Privacy

The Telegram bot token should never be committed to GitHub.

Use environment variables or a local configuration file that is excluded by `.gitignore`.

Example:

```text
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

Do not upload:

- Telegram bot tokens
- Private chat IDs
- Personal visitor photographs
- Recorded private conversations
- Local database files containing private information

Use `.gitignore` for secrets, generated recordings, photos, and local databases.

---

## Hackathon Goal

The project demonstrates a practical smart-door security architecture where computer vision and physical sensing work together.

Instead of relying only on a camera, the system uses:

```text
Vision + Distance + Dwell Time + Face Recognition
```

This reduces unnecessary alerts caused by people who are merely passing the camera.

The final system aims to provide:

- Intelligent visitor detection
- Known/unknown identification
- Sensor-based confirmation
- Real-time Telegram alerts
- Visitor photographs
- Event history
- Remote security controls
- Two-way voice communication
- Local audible warning
- Live video monitoring
