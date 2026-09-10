"""
Smart Doorbell Hub -- Personal Face Enrollment Utility.

Features:
  - Live Webcam Auto-Capture: Rapidly captures 25-30 high-quality face samples of the owner.
  - Multi-Angle Support: Captures diverse angles (front, left, right, up, down, smiles).
  - Storage: Stores all personal face crops into known_faces/owner/ and my_face/.
  - Biometric Compilation: Extracts 128D deep metric embeddings via SFace ONNX and saves resident_gallery.npy.
  - Headless Recompile: Recompiles gallery directly from existing photos without opening webcam.

Usage:
  python enroll_me.py                  # Live 5-second guided webcam capture & enrollment
  python enroll_me.py --recompile      # Build gallery from photos already in known_faces/owner/
  python enroll_me.py --samples 30     # Capture 30 samples
"""

import os
import sys
from pathlib import Path
import argparse
import time
import cv2
import numpy as np

BASE_DIR = Path(__file__).resolve().parent

# Color Palette
COLOR_GREEN  = (94, 197, 34)    # Emerald Green
COLOR_RED    = (38, 38, 239)   # Bright Red
COLOR_AMBER  = (0, 204, 255)   # Amber
COLOR_DARK   = (20, 20, 24)    # Slate Dark
COLOR_WHITE  = (255, 255, 255)


def find_asset(filename):
    candidates = [
        BASE_DIR / filename,
        Path(r"C:\Users\Goutham B\OneDrive\Desktop\doorhub") / filename,
        Path(r"c:\Users\Goutham B\OneDrive\Desktop\ANTIGRAVITY\smart-doorbell-hub\smart-doorbell-hub") / filename
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def get_storage_dirs():
    dirs = [
        BASE_DIR / "known_faces" / "owner",
        BASE_DIR / "my_face",
        Path(r"C:\Users\Goutham B\OneDrive\Desktop\doorhub\known_faces\owner"),
        Path(r"c:\Users\Goutham B\OneDrive\Desktop\ANTIGRAVITY\smart-doorbell-hub\smart-doorbell-hub\known_faces\owner")
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def compile_gallery(detector, recognizer, owner_dir):
    """Compiles all photos in owner_dir into resident_gallery.npy."""
    files = sorted(list(owner_dir.glob("*.jpg")) + list(owner_dir.glob("*.png")) + list(owner_dir.glob("*.jpeg")))
    if not files:
        print(f"[WARNING] No photos found in {owner_dir}")
        return None

    print(f"\n[INFO] Compiling biometric gallery from {len(files)} photos in {owner_dir.name}...")
    features = []

    for idx, f in enumerate(files, 1):
        img = cv2.imread(str(f))
        if img is None:
            continue
        h, w = img.shape[:2]
        detector.setInputSize((w, h))
        _, faces = detector.detect(img)
        if faces is not None and len(faces) > 0:
            aligned = recognizer.alignCrop(img, faces[0])
            feat = recognizer.feature(aligned)
            feat_norm = feat / (np.linalg.norm(feat) + 1e-6)
            features.append(feat_norm)
            print(f"  [{idx}/{len(files)}] Enrolled: {f.name}")
        else:
            print(f"  [{idx}/{len(files)}] No face detected in: {f.name}")

    if not features:
        print("[ERROR] No valid faces extracted.")
        return None

    gallery = np.vstack(features).astype(np.float32)

    # Save to both doorhub and workspace
    target_paths = [
        BASE_DIR / "resident_gallery.npy",
        Path(r"C:\Users\Goutham B\OneDrive\Desktop\doorhub\resident_gallery.npy"),
        Path(r"c:\Users\Goutham B\OneDrive\Desktop\ANTIGRAVITY\smart-doorbell-hub\smart-doorbell-hub\resident_gallery.npy")
    ]

    for tp in target_paths:
        try:
            tp.parent.mkdir(parents=True, exist_ok=True)
            np.save(str(tp), gallery)
            print(f"[SUCCESS] Saved biometric gallery ({len(gallery)} vectors) to: {tp}")
        except Exception as e:
            pass

    return gallery


def run_webcam_enrollment(num_samples=25, cam_idx=0):
    yunet_p = find_asset("face_detection_yunet_2023mar.onnx")
    sface_p = find_asset("face_recognition_sface_2021dec.onnx")

    if not yunet_p or not sface_p:
        print("[ERROR] YuNet or SFace models missing!")
        return

    detector = cv2.FaceDetectorYN.create(str(yunet_p), "", (320, 240), 0.50, 0.30)
    recognizer = cv2.FaceRecognizerSF.create(str(sface_p), "")

    backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY
    cap = cv2.VideoCapture(cam_idx, backend)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    if not cap.isOpened():
        print("[ERROR] Could not open camera.")
        return

    storage_dirs = get_storage_dirs()
    primary_dir = storage_dirs[0]

    print("=" * 65)
    print(" Smart Doorbell Hub -- Personal Face Enrollment")
    print(f" Target Samples: {num_samples} frames")
    print(f" Saving to: {primary_dir}")
    print(" Press SPACE to start capture, or 'q' / ESC to cancel.")
    print("=" * 65)

    capturing = False
    captured_count = 0
    last_capture_time = 0.0
    countdown = 3
    start_time = time.time()

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            h, w = frame.shape[:2]
            detector.setInputSize((w, h))
            _, faces = detector.detect(frame)

            annotated = frame.copy()

            # Draw HUD
            cv2.rectangle(annotated, (0, 0), (w, 50), COLOR_DARK, -1)
            cv2.putText(annotated, "PERSONAL FACE ENROLLMENT", (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.65, COLOR_WHITE, 2, cv2.LINE_AA)

            has_valid_face = False
            best_face = None

            if faces is not None and len(faces) > 0:
                # Find largest face
                best_face = max(faces, key=lambda f: f[2] * f[3])
                fx, fy, fw, fh = best_face[:4]
                fx1 = max(0, int(fx))
                fy1 = max(0, int(fy))
                fx2 = min(w, int(fx + fw))
                fy2 = min(h, int(fy + fh))

                if fw >= 60 and fh >= 60:
                    has_valid_face = True
                    box_color = COLOR_GREEN if capturing else COLOR_AMBER
                    cv2.rectangle(annotated, (fx1, fy1), (fx2, fy2), box_color, 2, cv2.LINE_AA)

                    # Corner brackets
                    blen = min(20, fw // 4, fh // 4)
                    cv2.line(annotated, (fx1, fy1), (fx1 + blen, fy1), box_color, 4)
                    cv2.line(annotated, (fx1, fy1), (fx1, fy1 + blen), box_color, 4)
                    cv2.line(annotated, (fx2, fy1), (fx2 - blen, fy1), box_color, 4)
                    cv2.line(annotated, (fx2, fy1), (fx2, fy1 + blen), box_color, 4)
                    cv2.line(annotated, (fx1, fy2), (fx1 + blen, fy2), box_color, 4)
                    cv2.line(annotated, (fx1, fy2), (fx1, fy2 - blen), box_color, 4)
                    cv2.line(annotated, (fx2, fy2), (fx2 - blen, fy2), box_color, 4)
                    cv2.line(annotated, (fx2, fy2), (fx2, fy2 - blen), box_color, 4)

            # State Logic
            if not capturing:
                elapsed = time.time() - start_time
                rem = max(0, countdown - int(elapsed))
                if rem > 0:
                    msg = f"Auto-starting in {rem}s... (Or press SPACEBAR)"
                    color = COLOR_AMBER
                else:
                    capturing = True
                    msg = "Capturing! Move head slightly: front, left, right..."
                    color = COLOR_GREEN

                cv2.putText(annotated, msg, (w // 2 - 220, h - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.60, color, 2, cv2.LINE_AA)
            else:
                progress_text = f"Captured: {captured_count}/{num_samples} | Move head gently..."
                cv2.putText(annotated, progress_text, (w // 2 - 200, h - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.60, COLOR_GREEN, 2, cv2.LINE_AA)

                # Capture photo every 120ms if face is present
                cur_t = time.time()
                if has_valid_face and (cur_t - last_capture_time) >= 0.12:
                    last_capture_time = cur_t
                    captured_count += 1

                    # Save full frame and crop
                    fx, fy, fw, fh = best_face[:4]
                    # Crop with 25% margin
                    pad_x = int(fw * 0.25)
                    pad_y = int(fh * 0.25)
                    cx1 = max(0, int(fx) - pad_x)
                    cy1 = max(0, int(fy) - pad_y)
                    cx2 = min(w, int(fx + fw) + pad_x)
                    cy2 = min(h, int(fy + fh) + pad_y)
                    face_crop = frame[cy1:cy2, cx1:cx2]

                    fname = f"user_capture_{captured_count:02d}.jpg"
                    for d in storage_dirs:
                        cv2.imwrite(str(d / fname), face_crop)

                    # Flash effect
                    cv2.rectangle(annotated, (0, 0), (w, h), (255, 255, 255), 10)

                    if captured_count >= num_samples:
                        print(f"\n[SUCCESS] Captured {captured_count} personal face photos!")
                        break

            cv2.imshow("Doorbell Hub -- Face Enrollment", annotated)
            key = cv2.waitKey(1) & 0xFF
            if key == ord(' '):
                capturing = True
            elif key in (27, ord('q')):
                print("\nEnrollment cancelled by user.")
                return

    finally:
        cap.release()
        cv2.destroyAllWindows()

    # Automatically compile gallery from newly captured images
    compile_gallery(detector, recognizer, primary_dir)
    print("\n" + "=" * 65)
    print(" ENROLLMENT COMPLETE!")
    print(" Only YOU will now receive the GREEN box [ACCESS GRANTED].")
    print(" Everyone else will receive the RED box [ALERT: STRANGER].")
    print(" Run the live camera: python test_doorbell.py --webcam")
    print("=" * 65)


def main():
    parser = argparse.ArgumentParser(description="Smart Doorbell Personal Face Enrollment")
    parser.add_argument("--samples", type=int, default=25, help="Number of face frames to capture")
    parser.add_argument("--camera", type=int, default=0, help="Webcam device index")
    parser.add_argument("--recompile", action="store_true", help="Recompile gallery from existing photos in known_faces/owner/")
    args = parser.parse_args()

    if args.recompile:
        yunet_p = find_asset("face_detection_yunet_2023mar.onnx")
        sface_p = find_asset("face_recognition_sface_2021dec.onnx")
        detector = cv2.FaceDetectorYN.create(str(yunet_p), "", (320, 240), 0.50, 0.30)
        recognizer = cv2.FaceRecognizerSF.create(str(sface_p), "")
        compile_gallery(detector, recognizer, get_storage_dirs()[0])
        return

    run_webcam_enrollment(num_samples=args.samples, cam_idx=args.camera)


if __name__ == "__main__":
    main()
