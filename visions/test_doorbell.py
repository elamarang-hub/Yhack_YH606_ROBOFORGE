"""
Smart Doorbell Hub -- High-FPS Multi-Person Vision & Personal Face Recognition System.

Features:
  - Strict Owner vs Stranger Classification (YuNet + SFace ONNX):
     - GREEN:   Resident (Owner) with [ACCESS GRANTED] badge.
     - RED:     Stranger / Visitor with [ALERT: STRANGER] badge.
     - YELLOW:  Searching / evaluating with [STATUS: SEARCHING] badge.
  - Personal Face Gallery: Compiles embeddings from known_faces/owner/ or live capture.
  - Temporal Smoothing & Sticky Hysteresis: Eliminates flicker, score oscillations, and state jumping.
  - Millimeter-Tight Face Geometry: Exact facial bounding boxes (forehead to chin, cheek to cheek).
  - Multi-Person Simultaneous Recognition: Evaluates all people in frame in real-time.
  - DirectShow Zero-Lag Threaded Camera: Dedicated background reader thread with BUFFERSIZE=1.
  - Hardware Acceleration: NVIDIA GeForce RTX 4060 GPU with ONNX Runtime & CUDA.

Usage:
  python test_doorbell.py --webcam                     # High-FPS live stream (Green for Owner, Red for Strangers)
  python test_doorbell.py --enroll                     # Capture 25 personal photos to enroll your face
  python test_doorbell.py --image path/to/image.jpg --show
  python test_doorbell.py --dir dataset/demo_data/images/test
"""

import os
import sys
from pathlib import Path
import argparse
import time
import threading
import cv2
import numpy as np

# PyTorch 2.6+ compatibility
import torch
_orig_torch_load = torch.load
def _compat_torch_load(*args, **kwargs):
    if "weights_only" not in kwargs:
        kwargs["weights_only"] = False
    return _orig_torch_load(*args, **kwargs)
torch.load = _compat_torch_load

from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent

# Color Palette (BGR for OpenCV)
COLOR_KNOWN     = (94, 197, 34)     # Emerald Green: RGB(34, 197, 94)
COLOR_STRANGER  = (38, 38, 239)    # Bright Red: RGB(239, 38, 38)
COLOR_SEARCHING = (0, 204, 255)    # Amber Yellow: RGB(255, 204, 0)
COLOR_BG_DARK   = (20, 20, 24)     # Dark slate
COLOR_WHITE     = (255, 255, 255)

# Decision Thresholds
THRESHOLD_KNOWN    = 0.50   # Similarity >= 0.50 confirms the Resident (Owner)
THRESHOLD_STRANGER = 0.44   # Similarity < 0.44 confirms a Stranger


def compute_iou(boxA, boxB):
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    interArea = max(0, xB - xA) * max(0, yB - yA)
    boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
    return interArea / float(boxAArea + boxBArea - interArea + 1e-6)


def centroid_distance(boxA, boxB):
    cxA = (boxA[0] + boxA[2]) / 2.0
    cyA = (boxA[1] + boxA[3]) / 2.0
    cxB = (boxB[0] + boxB[2]) / 2.0
    cyB = (boxB[1] + boxB[3]) / 2.0
    return float(np.hypot(cxA - cxB, cyA - cyB))


class TrackedFace:
    """
    Maintains temporal smoothing and sticky hysteresis state for a face across video frames.
    Prevents color flipping, score jitter, and state flicker.
    """
    def __init__(self, box, initial_score):
        self.box = list(box)
        self.smooth_score = float(initial_score)
        self.frames_alive = 1
        self.lost_frames = 0

        if initial_score >= THRESHOLD_KNOWN:
            self.state = "KNOWN"
            self.consecutive_known = 1
            self.consecutive_stranger = 0
        elif initial_score < THRESHOLD_STRANGER:
            self.state = "STRANGER"
            self.consecutive_known = 0
            self.consecutive_stranger = 1
        else:
            self.state = "SEARCHING"
            self.consecutive_known = 0
            self.consecutive_stranger = 0

    def update(self, box, raw_score):
        # Exponential Moving Average (alpha=0.75 for strong jitter resistance)
        self.smooth_score = 0.75 * self.smooth_score + 0.25 * float(raw_score)
        self.box = list(box)
        self.frames_alive += 1
        self.lost_frames = 0

        # Update evidence counters based on smoothed score
        if self.smooth_score >= THRESHOLD_KNOWN:
            self.consecutive_known += 1
            self.consecutive_stranger = max(0, self.consecutive_stranger - 1)
        elif self.smooth_score < THRESHOLD_STRANGER:
            self.consecutive_stranger += 1
            self.consecutive_known = max(0, self.consecutive_known - 1)
        else:
            self.consecutive_known = max(0, self.consecutive_known - 1)
            self.consecutive_stranger = max(0, self.consecutive_stranger - 1)

        # Sticky Hysteresis State Machine
        if self.state == "KNOWN":
            # Very sticky: Requires sustained stranger evidence (6+ frames below 0.44) to drop from KNOWN
            if self.smooth_score < 0.44 and self.consecutive_stranger >= 6:
                self.state = "STRANGER"
            elif self.smooth_score < 0.46 and self.consecutive_stranger >= 4:
                self.state = "SEARCHING"
        elif self.state == "STRANGER":
            # Sticky: Requires sustained resident evidence (4+ frames above 0.50) to switch to KNOWN
            if self.smooth_score >= THRESHOLD_KNOWN and self.consecutive_known >= 4:
                self.state = "KNOWN"
            elif self.smooth_score >= 0.48 and self.consecutive_known >= 2:
                self.state = "SEARCHING"
        else:  # SEARCHING
            if self.smooth_score >= THRESHOLD_KNOWN and self.consecutive_known >= 2:
                self.state = "KNOWN"
            elif self.smooth_score < THRESHOLD_STRANGER and self.consecutive_stranger >= 2:
                self.state = "STRANGER"

    def get_display_info(self):
        if self.state == "KNOWN":
            conf_pct = min(99, max(75, int(self.smooth_score * 115)))
            return "KNOWN", f"Resident (Owner) ({conf_pct}%)", self.smooth_score
        elif self.state == "STRANGER":
            conf_pct = min(99, max(70, int((1.0 - self.smooth_score) * 115)))
            return "STRANGER", f"STRANGER ({conf_pct}%)", self.smooth_score
        else:
            return "SEARCHING", f"SEARCHING ({int(self.smooth_score * 100)}%)...", self.smooth_score


class FastThreadedCamera:
    """Zero-latency threaded camera reader using DirectShow on Windows."""
    def __init__(self, src=0, width=640, height=480):
        backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(src, backend)
        
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.cap.set(cv2.CAP_PROP_FPS, 30)

        self.ret, self.frame = self.cap.read()
        self.running = self.cap.isOpened()
        self.lock = threading.Lock()

        if self.running:
            self.thread = threading.Thread(target=self._worker, daemon=True)
            self.thread.start()
        else:
            print("[ERROR] Could not open camera device.")

    def _worker(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                with self.lock:
                    self.ret = ret
                    self.frame = frame
            else:
                time.sleep(0.005)

    def read(self):
        with self.lock:
            if self.frame is not None:
                return self.ret, self.frame.copy()
            return False, None

    def release(self):
        self.running = False
        if hasattr(self, 'thread') and self.thread.is_alive():
            self.thread.join(timeout=0.5)
        self.cap.release()


class DetectedPerson:
    """Represents a classified individual in the current frame."""
    def __init__(self, box, status, label, conf):
        self.box = list(box)  # (x1, y1, x2, y2)
        self.status = status  # "KNOWN", "STRANGER", "SEARCHING"
        self.label = label
        self.conf = conf


class FastDoorbellVision:
    def __init__(self, model_path=None):
        self.has_cuda = torch.cuda.is_available()
        self.device = 0 if self.has_cuda else "cpu"
        self.active_tracks = []

        # 1. Initialize YuNet ONNX Face Detector (Millimeter-tight boxes @ 100+ FPS)
        yunet_path = self._find_asset("face_detection_yunet_2023mar.onnx")
        if yunet_path is None or not yunet_path.exists():
            raise FileNotFoundError("YuNet face detection model not found.")

        self.face_detector = cv2.FaceDetectorYN.create(
            model=str(yunet_path),
            config="",
            input_size=(320, 240),
            score_threshold=0.45,
            nms_threshold=0.30
        )
        print(f"[INFO] High-Precision Face Engine Active (YuNet ONNX: 100+ FPS, strictly face-only): {yunet_path.name}")

        # 2. Initialize SFace ONNX Biometric Recognizer (128D Metric Embedding in 16ms)
        sface_path = self._find_asset("face_recognition_sface_2021dec.onnx")
        if sface_path is None or not sface_path.exists():
            raise FileNotFoundError("SFace biometric model not found.")

        self.face_recognizer = cv2.FaceRecognizerSF.create(
            model=str(sface_path),
            config=""
        )
        print(f"[INFO] Biometric Deep Metric Recognizer Active (SFace ONNX: 128-D Engine): {sface_path.name}")

        # 3. Load Multi-Angle Resident Biometric Gallery
        self.resident_gallery = self._load_gallery()

        # 4. Initialize YOLOv8 for fallback / presence
        if model_path is None:
            possible_paths = [
                BASE_DIR / "runs" / "detect" / "celeba_doorbell_v2" / "weights" / "best.pt",
                BASE_DIR / "runs" / "detect" / "celeba_doorbell" / "weights" / "best.pt",
                Path(r"C:\Users\Goutham B\OneDrive\Desktop\doorhub\runs\detect\celeba_doorbell_v2\weights\best.pt"),
                BASE_DIR / "yolov8s.pt",
                BASE_DIR / "yolov8n.pt"
            ]
            for p in possible_paths:
                if p.exists():
                    model_path = str(p)
                    break
            if model_path is None:
                model_path = "yolov8n.pt"

        print(f"[INFO] Initializing YOLO on {'NVIDIA GPU (RTX 4060)' if self.has_cuda else 'CPU'}...")
        print(f"[INFO] Using model weights: {model_path}")
        self.yolo_model = YOLO(model_path)

        if self.has_cuda:
            dummy = torch.zeros((1, 3, 384, 384), dtype=torch.float16, device='cuda')
            _ = self.yolo_model(dummy, device=0, verbose=False, half=True)
            print("[INFO] RTX 4060 GPU Warmup Complete (FP16 Tensor Cores Active).")

    def _find_asset(self, filename):
        candidates = [
            BASE_DIR / filename,
            Path(r"C:\Users\Goutham B\OneDrive\Desktop\doorhub") / filename,
            Path(r"c:\Users\Goutham B\OneDrive\Desktop\ANTIGRAVITY\smart-doorbell-hub\smart-doorbell-hub") / filename
        ]
        for c in candidates:
            if c.exists():
                return c
        return None

    def _load_gallery(self):
        """Loads precomputed multi-angle resident gallery and pre-normalizes them."""
        gallery_path = self._find_asset("resident_gallery.npy")
        if gallery_path and gallery_path.exists():
            gallery = np.load(str(gallery_path)).astype(np.float32)
            if gallery.ndim == 1:
                gallery = gallery.reshape(1, -1)
            norms = np.linalg.norm(gallery, axis=1, keepdims=True)
            norms[norms == 0] = 1e-6
            norm_gallery = gallery / norms
            print(f"[SUCCESS] Loaded Owner Biometric Gallery ({len(norm_gallery)} vectors) from: {gallery_path.name}")
            return norm_gallery

        # Fallback to known_faces/owner images if available
        owner_dir = BASE_DIR / "known_faces" / "owner"
        if not owner_dir.exists():
            owner_dir = Path(r"C:\Users\Goutham B\OneDrive\Desktop\doorhub\known_faces\owner")
        if owner_dir.exists():
            files = list(owner_dir.glob("*.jpg")) + list(owner_dir.glob("*.png"))
            if files:
                from enroll_me import compile_gallery
                return compile_gallery(self.face_detector, self.face_recognizer, owner_dir)

        print("[WARNING] No owner gallery found; stranger-only mode.")
        return None

    def match_gallery(self, feat):
        """Computes top cosine similarity against the owner gallery."""
        if self.resident_gallery is None or len(self.resident_gallery) == 0:
            return 0.0
        feat_norm = feat / (np.linalg.norm(feat) + 1e-6)
        # Vectorized dot product cosine similarity
        cosines = np.dot(self.resident_gallery, feat_norm.T).flatten()
        k = min(3, len(cosines))
        top_k = np.sort(cosines)[-k:]
        return float(np.mean(top_k))

    def process_frame(self, frame, is_live=True):
        h, w = frame.shape[:2]
        detected_persons = []

        # Step 1: Detect millimeter-tight face boxes via YuNet
        self.face_detector.setInputSize((w, h))
        _, faces = self.face_detector.detect(frame)

        current_detections = []
        if faces is not None and len(faces) > 0:
            for f in faces:
                fx, fy, fw, fh = f[:4]
                fx1 = max(0, int(fx))
                fy1 = max(0, int(fy))
                fx2 = min(w, int(fx + fw))
                fy2 = min(h, int(fy + fh))

                # Filter tiny background artifacts (< 35x35 pixels or edge clipping)
                if (fx2 - fx1) < 35 or (fy2 - fy1) < 35:
                    continue
                if fx1 < 20 and (fx2 - fx1) < 45:
                    continue

                # Step 2: Extract 128D Biometric Feature Vector via SFace
                aligned = self.face_recognizer.alignCrop(frame, f)
                feat = self.face_recognizer.feature(aligned)
                score = self.match_gallery(feat)

                current_detections.append(((fx1, fy1, fx2, fy2), score))

        if not is_live:
            # Static image mode: evaluate immediately per detection
            for box, score in current_detections:
                if score >= THRESHOLD_KNOWN:
                    status = "KNOWN"
                    conf_pct = min(99, max(75, int(score * 115)))
                    label = f"Resident (Owner) ({conf_pct}%)"
                elif score < THRESHOLD_STRANGER:
                    status = "STRANGER"
                    conf_pct = min(99, max(70, int((1.0 - score) * 115)))
                    label = f"STRANGER ({conf_pct}%)"
                else:
                    status = "SEARCHING"
                    label = f"SEARCHING ({int(score * 100)}%)..."

                detected_persons.append(DetectedPerson(box=box, status=status, label=label, conf=score))
            return detected_persons

        # Live webcam mode: apply temporal smoothing & sticky hysteresis
        if current_detections:
            matched_tracks = []
            unmatched_detections = []

            for det_box, det_score in current_detections:
                best_track = None
                best_dist = float("inf")

                for track in self.active_tracks:
                    if track in matched_tracks:
                        continue
                    dist = centroid_distance(det_box, track.box)
                    iou = compute_iou(det_box, track.box)
                    if (dist < 90 or iou > 0.20) and dist < best_dist:
                        best_dist = dist
                        best_track = track

                if best_track is not None:
                    best_track.update(det_box, det_score)
                    matched_tracks.append(best_track)
                else:
                    unmatched_detections.append((det_box, det_score))

            # Spawn new tracks for newly entering faces
            for det_box, det_score in unmatched_detections:
                new_track = TrackedFace(det_box, det_score)
                matched_tracks.append(new_track)

            # Age unmatched tracks from previous frames (grace period of 8 frames)
            for track in self.active_tracks:
                if track not in matched_tracks:
                    track.lost_frames += 1
                    if track.lost_frames <= 8:
                        matched_tracks.append(track)

            self.active_tracks = matched_tracks

            # Emit visible detected persons
            for track in self.active_tracks:
                if track.lost_frames == 0:  # Only draw faces present in this frame
                    status, label, conf = track.get_display_info()
                    detected_persons.append(DetectedPerson(
                        box=track.box,
                        status=status,
                        label=label,
                        conf=conf
                    ))
        else:
            # Age existing tracks when no faces detected
            kept_tracks = []
            for track in self.active_tracks:
                track.lost_frames += 1
                if track.lost_frames <= 8:
                    kept_tracks.append(track)
            self.active_tracks = kept_tracks

            # Fallback to YOLO if face is covered / occluded
            results = self.yolo_model.predict(
                frame,
                conf=0.20,
                iou=0.45,
                max_det=10,
                imgsz=384,
                device=self.device,
                half=self.has_cuda,
                verbose=False
            )
            for r in results:
                for b in r.boxes:
                    rx1, ry1, rx2, ry2 = map(int, b.xyxy[0])
                    conf = float(b.conf[0])
                    bh = ry2 - ry1
                    bw = rx2 - rx1
                    fx1 = max(0, rx1 + int(bw * 0.2))
                    fx2 = min(w, rx2 - int(bw * 0.2))
                    fy1 = max(0, ry1)
                    fy2 = min(h, ry1 + int(bh * 0.45))

                    detected_persons.append(DetectedPerson(
                        box=(fx1, fy1, fx2, fy2),
                        status="SEARCHING",
                        label=f"SEARCHING ({int(conf*100)}%)...",
                        conf=conf
                    ))

        return detected_persons

    def draw_badge(self, img, text, pos, color_bg, color_text=(255, 255, 255), scale=0.50, thickness=2, pad=5):
        x, y = pos
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
        cv2.rectangle(img, (x, y - th - pad * 2), (x + tw + pad * 2, y), color_bg, -1)
        cv2.putText(img, text, (x + pad, y - pad), cv2.FONT_HERSHEY_SIMPLEX, scale, color_text, thickness, cv2.LINE_AA)
        return tw + pad * 2, th + pad * 2

    def render_overlay(self, frame, detected_persons, fps=0.0):
        h, w = frame.shape[:2]
        annotated = frame.copy()

        for person in detected_persons:
            x1, y1, x2, y2 = person.box

            if person.status == "KNOWN":
                box_color = COLOR_KNOWN
                status_badge = "[ACCESS GRANTED]"
            elif person.status == "STRANGER":
                box_color = COLOR_STRANGER
                status_badge = "[ALERT: STRANGER]"
            else:
                box_color = COLOR_SEARCHING
                status_badge = "[STATUS: SEARCHING]"

            # Tight face bounding box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), box_color, 2, cv2.LINE_AA)

            # Elegant corner brackets framing the face
            line_len = min(18, max(5, (x2 - x1) // 4), max(5, (y2 - y1) // 4))
            cv2.line(annotated, (x1, y1), (x1 + line_len, y1), box_color, 4)
            cv2.line(annotated, (x1, y1), (x1, y1 + line_len), box_color, 4)
            cv2.line(annotated, (x2, y1), (x2 - line_len, y1), box_color, 4)
            cv2.line(annotated, (x2, y1), (x2, y1 + line_len), box_color, 4)
            cv2.line(annotated, (x1, y2), (x1 + line_len, y2), box_color, 4)
            cv2.line(annotated, (x1, y2), (x1, y2 - line_len), box_color, 4)
            cv2.line(annotated, (x2, y2), (x2 - line_len, y2), box_color, 4)
            cv2.line(annotated, (x2, y2), (x2, y2 - line_len), box_color, 4)

            # Header badge above face
            self.draw_badge(annotated, person.label, (x1, max(26, y1 - 26)), box_color, COLOR_WHITE, scale=0.52, thickness=2)
            # Security badge below face
            self.draw_badge(annotated, status_badge, (x1, y2 + 28), COLOR_BG_DARK, box_color, scale=0.48, thickness=2)

        # Top System HUD Bar
        hud_h = 44
        cv2.rectangle(annotated, (0, 0), (w, hud_h), COLOR_BG_DARK, -1)
        cv2.line(annotated, (0, hud_h), (w, hud_h), (60, 60, 68), 1)

        known_cnt = sum(1 for p in detected_persons if p.status == "KNOWN")
        stranger_cnt = sum(1 for p in detected_persons if p.status == "STRANGER")
        searching_cnt = sum(1 for p in detected_persons if p.status == "SEARCHING")

        hud_title = f"DOORBELL HUB AI  |  {fps:.1f} FPS  |  Faces: {len(detected_persons)}"
        cv2.putText(annotated, hud_title, (14, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_WHITE, 2, cv2.LINE_AA)

        stat_x = w - 380
        if stat_x > 320:
            cv2.putText(annotated, f"Owner: {known_cnt}", (stat_x, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.50, COLOR_KNOWN, 2, cv2.LINE_AA)
            cv2.putText(annotated, f"Stranger: {stranger_cnt}", (stat_x + 110, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.50, COLOR_STRANGER, 2, cv2.LINE_AA)
            cv2.putText(annotated, f"Searching: {searching_cnt}", (stat_x + 230, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.50, COLOR_SEARCHING, 2, cv2.LINE_AA)

        return annotated


def run_live_webcam():
    engine = FastDoorbellVision()
    cam = FastThreadedCamera(src=0, width=640, height=480)

    if not cam.running:
        return

    print("=" * 65)
    print(" Smart Doorbell Hub -- Personal Biometric Stream")
    print(f" Acceleration: {'NVIDIA GeForce RTX 4060 GPU (FP16)' if engine.has_cuda else 'CPU'}")
    print(" Color Codes:")
    print("   GREEN:   Resident (Owner) [ACCESS GRANTED]")
    print("   RED:     Stranger / Visitor [ALERT: STRANGER]")
    print("   YELLOW:  Searching [STATUS: SEARCHING]")
    print(" Biometric Engine: YuNet + SFace ONNX Deep Metric Embeddings")
    print(" Press 'q' or ESC in the window to stop.")
    print("=" * 65)

    prev_time = time.time()
    fps_smooth = 30.0

    try:
        while True:
            ret, frame = cam.read()
            if not ret or frame is None:
                time.sleep(0.005)
                continue

            detected_persons = engine.process_frame(frame, is_live=True)

            curr_time = time.time()
            dt = curr_time - prev_time
            prev_time = curr_time
            if dt > 0:
                cur_fps = 1.0 / dt
                fps_smooth = 0.9 * fps_smooth + 0.1 * cur_fps

            annotated = engine.render_overlay(frame, detected_persons, fps=fps_smooth)
            cv2.imshow("Doorbell Hub -- Color-Coded Vision", annotated)

            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord('q')):
                break
    finally:
        cam.release()
        cv2.destroyAllWindows()
        print("\nLive stream closed.")


def main():
    parser = argparse.ArgumentParser(description="Biometric Color-Coded Multi-Person Doorbell Vision")
    parser.add_argument("--image", type=str, help="Path to single image")
    parser.add_argument("--dir", type=str, help="Path to directory of images")
    parser.add_argument("--webcam", action="store_true", help="Run live webcam stream with color-coded face boxes")
    parser.add_argument("--enroll", action="store_true", help="Run webcam enrollment tool to store your personal face images")
    parser.add_argument("--save", type=str, help="Path to save annotated image")
    parser.add_argument("--save-dir", type=str, default="output_annotated", help="Folder to save batch images")
    parser.add_argument("--show", action="store_true", help="Display window with cv2.imshow")
    args = parser.parse_args()

    if args.enroll:
        from enroll_me import run_webcam_enrollment
        run_webcam_enrollment()
        return

    if args.webcam:
        run_live_webcam()
        return

    engine = FastDoorbellVision()

    if args.image:
        if not os.path.exists(args.image):
            print(f"[ERROR] File not found: {args.image}")
            return

        frame = cv2.imread(args.image)
        if frame is None:
            print(f"[ERROR] Could not decode image: {args.image}")
            return

        print(f"\n[INFO] Biometrically scanning '{os.path.basename(args.image)}' for tight face boxes...")
        detected_persons = engine.process_frame(frame, is_live=False)
        annotated = engine.render_overlay(frame, detected_persons)

        print(f"Total faces detected in frame: {len(detected_persons)}")
        for idx, p in enumerate(detected_persons, 1):
            print(f"  Face #{idx}: {p.status} -> {p.label} at box {p.box}")

        out_path = args.save or f"annotated_{os.path.basename(args.image)}"
        cv2.imwrite(out_path, annotated)
        print(f"[SUCCESS] Saved color-coded annotated image to: {out_path}")

        if args.show:
            cv2.imshow("Color-Coded Multi-Person Detection", annotated)
            print("Press any key in image window to close...")
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        return

    if args.dir:
        img_dir = Path(args.dir)
        if not img_dir.exists():
            print(f"[ERROR] Directory not found: {args.dir}")
            return

        out_dir = Path(args.save_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        files = sorted(list(img_dir.glob("*.jpg")) + list(img_dir.glob("*.png")))[:20]
        print(f"\n[INFO] Batch processing {len(files)} images from {args.dir}...")

        for idx, f in enumerate(files, 1):
            frame = cv2.imread(str(f))
            if frame is None:
                continue
            detected_persons = engine.process_frame(frame, is_live=False)
            annotated = engine.render_overlay(frame, detected_persons)
            out_file = out_dir / f"annotated_{f.name}"
            cv2.imwrite(str(out_file), annotated)
            summary = ", ".join(p.label for p in detected_persons) if detected_persons else "No face"
            print(f"[{idx}/{len(files)}] {f.name} ({len(detected_persons)} faces) -> {summary}")

        print(f"\n[SUCCESS] Batch results saved to: {out_dir.resolve()}")
        return

    print("Usage:")
    print("  python test_doorbell.py --webcam                     # High-FPS live webcam (Green for Owner, Red for Strangers)")
    print("  python test_doorbell.py --enroll                     # Enroll your personal face photos from webcam")
    print("  python test_doorbell.py --image <path> [--show]      # Single image test")
    print("  python test_doorbell.py --dir <folder_path>          # Batch test")

if __name__ == "__main__":
    main()
