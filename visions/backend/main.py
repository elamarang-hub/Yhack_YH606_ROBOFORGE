"""
Smart Doorbell Hub -- FastAPI Edge-AI Central Server.

Features:
  - Live Video Stream: Low-latency MJPEG HTTP stream at /api/live with millimeter-tight YuNet + SFace overlays.
  - Hardware I/O WebSocket: /ws/esp32 for real-time VL53L0X ToF sensor streaming and 5V relay actuation.
  - Dashboard WebSocket: /ws/alerts for live visitor cards, push-to-talk intercom, and sirens.
  - Dual-Sensor Fusion: ToF distance tracking + Vision validation with 15s cooldown latch.
  - Security Modes: Configurable Individual (1.2m, 2s dwell) vs Apartment (0.5m, 3s dwell) zone filtering.
"""

import os
import sys
import time
import base64
import asyncio
import threading
import json
import io
from pathlib import Path
import cv2
import numpy as np

# Add parent directory to sys.path to access test_doorbell vision engine
PARENT_DIR = Path(__file__).resolve().parent.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Request
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
import pygame

import config
import database
from test_doorbell import FastDoorbellVision

app = FastAPI(title="Smart Doorbell Hub API", version="2.0.0")

# Global Application State
class AppState:
    def __init__(self):
        self.person_detected = False
        self.current_tof_distance = 9999.0
        self.last_alert_time = 0.0
        self.frame = None
        self.annotated_frame = None
        self.jpeg_frame = b''
        self.lock = threading.Lock()
        self.esp32_ws = None
        self.dashboard_websockets = set()
        self.mode = config.MODE
        self.loop = None
        self.person_in_zone_since = None

state = AppState()

# Initialize High-Speed Vision Engine
vision_engine = None

def get_vision_engine():
    global vision_engine
    if vision_engine is None:
        vision_engine = FastDoorbellVision()
    return vision_engine

async def notify_owner(label, confidence, image_b64, status):
    """Dispatches Telegram notifications to owner if configured."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_OWNER_CHAT_ID:
        return
    try:
        import urllib.request
        import urllib.parse
        caption = f"🚪 Doorbell Alert: {label} [{status}]\nConfidence: {confidence:.0f}%\nTime: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        img_bytes = base64.b64decode(image_b64)
        
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendPhoto"
        # Multipart form dispatch for telegram photo
        boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
        data = []
        data.append(f'--{boundary}'.encode())
        data.append(f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{config.TELEGRAM_OWNER_CHAT_ID}'.encode())
        data.append(f'--{boundary}'.encode())
        data.append(f'Content-Disposition: form-data; name="caption"\r\n\r\n{caption}'.encode())
        data.append(f'--{boundary}'.encode())
        data.append(f'Content-Disposition: form-data; name="photo"; filename="alert.jpg"\r\nContent-Type: image/jpeg\r\n'.encode())
        data.append(img_bytes)
        data.append(f'--{boundary}--\r\n'.encode())
        body = b'\r\n'.join(data)

        req = urllib.request.Request(url, data=body)
        req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")

def camera_vision_worker():
    """Decoupled background vision thread maintaining 30+ FPS stream."""
    engine = get_vision_engine()
    backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY
    cap = cv2.VideoCapture(config.CAMERA_INDEX, backend)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    fps_smooth = 30.0
    prev_t = time.time()

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            time.sleep(0.01)
            continue

        cur_t = time.time()
        dt = cur_t - prev_t
        prev_t = cur_t
        if dt > 0:
            fps_smooth = 0.9 * fps_smooth + 0.1 * (1.0 / dt)

        # Process with multi-person biometric tracking
        persons = engine.process_frame(frame, is_live=True)
        annotated = engine.render_overlay(frame, persons, fps=fps_smooth)

        # Encode frame to JPEG
        ret_jpg, jpeg_buf = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
        jpeg_bytes = jpeg_buf.tobytes() if ret_jpg else b''

        with state.lock:
            state.frame = frame
            state.annotated_frame = annotated
            state.jpeg_frame = jpeg_bytes
            state.person_detected = len(persons) > 0

def sensor_fusion_worker():
    """Dual-sensor fusion: evaluates ToF distance + Camera detections for High Alert dwell triggers."""
    while True:
        time.sleep(0.1)
        with state.lock:
            person_detected = state.person_detected
            dist = state.current_tof_distance
            mode = state.mode
            now = time.time()
            frame_copy = state.frame.copy() if state.frame is not None else None

        if not person_detected or frame_copy is None:
            state.person_in_zone_since = None
            continue

        threshold = config.TOF_ZONE_THRESHOLD_INDIVIDUAL if mode == "individual" else config.TOF_ZONE_THRESHOLD_APARTMENT
        dwell_limit = config.TOF_DWELL_INDIVIDUAL if mode == "individual" else config.TOF_DWELL_APARTMENT

        # High Alert triggers only when both sensors confirm presence + dwell time
        if dist < threshold:
            if state.person_in_zone_since is None:
                state.person_in_zone_since = now
            elif now - state.person_in_zone_since >= dwell_limit:
                # 15-second cooldown latch on visitor alert dispatches
                if now - state.last_alert_time > config.ALERT_COOLDOWN:
                    state.last_alert_time = now
                    if state.loop is not None:
                        asyncio.run_coroutine_threadsafe(trigger_visitor_alert(frame_copy), state.loop)
        else:
            state.person_in_zone_since = None

async def trigger_visitor_alert(frame):
    """Processes verified visitor alert, logs to database, and broadcasts to dashboard & Telegram."""
    engine = get_vision_engine()
    persons = engine.process_frame(frame, is_live=False)
    annotated = engine.render_overlay(frame, persons)

    _, jpeg = cv2.imencode('.jpg', annotated)
    img_b64 = base64.b64encode(jpeg.tobytes()).decode('utf-8')

    main_person = persons[0] if persons else None
    label = main_person.label if main_person else "Unknown Visitor"
    status = main_person.status if main_person else "STRANGER"
    conf = float(main_person.conf * 100) if main_person else 0.0

    with state.lock:
        tof_val = state.current_tof_distance

    # Log event
    database.log_event(
        label=label,
        confidence=conf,
        image_b64=img_b64,
        tof_distance=tof_val,
        face_id=1 if status == "KNOWN" else 0,
        action_taken=f"HIGH_ALERT_{status}"
    )

    # Broadcast to dashboard WebSockets
    payload = {
        "event": "VISITOR_DETECTED",
        "label": label,
        "confidence": round(conf, 1),
        "status": status,
        "image": img_b64,
        "timestamp": time.strftime("%H:%M:%S"),
        "is_known": status == "KNOWN"
    }

    dead = set()
    for ws in state.dashboard_websockets:
        try:
            await ws.send_text(json.dumps(payload))
        except Exception:
            dead.add(ws)
    state.dashboard_websockets -= dead

    # Dispatch telegram alert
    await notify_owner(label, conf, img_b64, status)

@app.on_event("startup")
async def startup_event():
    state.loop = asyncio.get_running_loop()
    database.init_db()
    try:
        pygame.mixer.init()
    except Exception:
        pass

    threading.Thread(target=camera_vision_worker, daemon=True).start()
    threading.Thread(target=sensor_fusion_worker, daemon=True).start()
    print("[INFO] Smart Doorbell Hub Startup Complete. Server ready on http://0.0.0.0:8000")

# WebSocket for ESP32 DevKit V1 Hardware Bridge
@app.websocket("/ws/esp32")
async def esp32_ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    state.esp32_ws = websocket
    print("[HARDWARE] ESP32 Connected via WiFi WebSocket.")
    try:
        while True:
            data = await websocket.receive_text()
            if data.startswith("DIST:"):
                try:
                    val = float(data.split(":")[1])
                    with state.lock:
                        state.current_tof_distance = val
                except ValueError:
                    pass
    except WebSocketDisconnect:
        if state.esp32_ws == websocket:
            state.esp32_ws = None
        print("[HARDWARE] ESP32 Disconnected.")

# WebSocket for Web Dashboard
@app.websocket("/ws/alerts")
async def alerts_ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    state.dashboard_websockets.add(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            action = msg.get("action")

            if action == "trigger_alarm" and state.esp32_ws:
                await state.esp32_ws.send_text("CMD_ALARM_ON")
            elif action == "silence_alarm" and state.esp32_ws:
                await state.esp32_ws.send_text("CMD_ALARM_OFF")
            elif action == "change_mode":
                new_mode = msg.get("mode")
                if new_mode in ["individual", "apartment"]:
                    with state.lock:
                        state.mode = new_mode
    except WebSocketDisconnect:
        state.dashboard_websockets.discard(websocket)

def generate_mjpeg():
    while True:
        with state.lock:
            f = state.jpeg_frame
        if f:
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + f + b'\r\n')
        time.sleep(0.033)

@app.get("/api/live")
async def video_feed():
    return StreamingResponse(generate_mjpeg(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/api/logs")
async def get_logs():
    return JSONResponse(database.get_recent_logs())

@app.post("/api/intercom")
async def upload_intercom(audio: UploadFile = File(...)):
    contents = await audio.read()
    mem_file = io.BytesIO(contents)
    try:
        pygame.mixer.music.load(mem_file)
        pygame.mixer.music.play()
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    return JSONResponse({"status": "success"})

@app.get("/")
async def serve_dashboard():
    html_path = PARENT_DIR / "frontend" / "index.html"
    if html_path.exists():
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<html><body><h1>Smart Doorbell Hub</h1><p>Frontend not found.</p></body></html>")
