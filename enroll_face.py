"""
Owner face enrollment / gallery recompile utility.

This is a small standalone tool (not used by main.py at runtime) for
(re)building models/resident_gallery.npy from photos in known_faces/owner/,
using the same YuNet + SFace models that vision/face_engine.py uses for the
live OWNER/STRANGER decision. Handy if the supplied 2-photo gallery needs
more angles for reliable recognition during the demo.

Usage:
    python enroll_face.py --recompile
        Rebuild the gallery from whatever photos are already in
        known_faces/owner/ (drop your own photos in there first).

    python enroll_face.py --capture
        Open the configured USB webcam (config.CAMERA_INDEX) and capture a
        few dozen face crops of the owner, save them into known_faces/owner/,
        then recompile the gallery.
"""

import argparse
import time
from pathlib import Path

import cv2
import numpy as np

import config


def _build_engine():
    detector = cv2.FaceDetectorYN.create(
        model=config.FACE_DETECTOR_MODEL, config="",
        input_size=(320, 240), score_threshold=0.5, nms_threshold=0.3,
    )
    recognizer = cv2.FaceRecognizerSF.create(model=config.FACE_RECOGNIZER_MODEL, config="")
    return detector, recognizer


def compile_gallery(detector, recognizer, owner_dir: Path):
    files = sorted(list(owner_dir.glob("*.jpg")) + list(owner_dir.glob("*.png")) + list(owner_dir.glob("*.jpeg")))
    if not files:
        print(f"[WARNING] No photos found in {owner_dir}")
        return None

    print(f"[INFO] Compiling gallery from {len(files)} photos in {owner_dir}...")
    features = []
    for f in files:
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
            print(f"  enrolled: {f.name}")
        else:
            print(f"  no face detected in: {f.name}")

    if not features:
        print("[ERROR] No valid faces extracted; gallery not updated.")
        return None

    gallery = np.vstack(features).astype(np.float32)
    config.RESIDENT_GALLERY_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.save(str(config.RESIDENT_GALLERY_PATH), gallery)
    print(f"[SUCCESS] Saved gallery ({len(gallery)} vectors) to {config.RESIDENT_GALLERY_PATH}")
    return gallery


def capture_owner_photos(detector, num_samples=25):
    owner_dir = config.KNOWN_FACES_DIR / "owner"
    owner_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(config.CAMERA_INDEX, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap.release()
        cap = cv2.VideoCapture(config.CAMERA_INDEX)
    if not cap.isOpened():
        print(f"[ERROR] Could not open camera index {config.CAMERA_INDEX}")
        return

    print("Move your head slightly (front / left / right). Press 'q' to stop early.")
    captured = 0
    last_capture = 0.0
    try:
        while captured < num_samples:
            ok, frame = cap.read()
            if not ok:
                continue
            h, w = frame.shape[:2]
            detector.setInputSize((w, h))
            _, faces = detector.detect(frame)
            annotated = frame.copy()
            if faces is not None and len(faces) > 0:
                best = max(faces, key=lambda f: f[2] * f[3])
                fx, fy, fw, fh = best[:4]
                x1, y1, x2, y2 = int(fx), int(fy), int(fx + fw), int(fy + fh)
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)

                now = time.time()
                if now - last_capture >= 0.2:
                    last_capture = now
                    captured += 1
                    pad_x, pad_y = int(fw * 0.25), int(fh * 0.25)
                    cx1, cy1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
                    cx2, cy2 = min(w, x2 + pad_x), min(h, y2 + pad_y)
                    crop = frame[cy1:cy2, cx1:cx2]
                    cv2.imwrite(str(owner_dir / f"owner_{captured:02d}.jpg"), crop)

            cv2.putText(annotated, f"Captured {captured}/{num_samples}", (20, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.imshow("Owner Enrollment", annotated)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()

    print(f"[SUCCESS] Captured {captured} photos into {owner_dir}")


def main():
    parser = argparse.ArgumentParser(description="Owner face enrollment / gallery recompile")
    parser.add_argument("--recompile", action="store_true",
                         help="Rebuild resident_gallery.npy from known_faces/owner/")
    parser.add_argument("--capture", action="store_true",
                         help="Capture new owner photos from the USB webcam, then recompile")
    parser.add_argument("--samples", type=int, default=25)
    args = parser.parse_args()

    detector, recognizer = _build_engine()
    owner_dir = config.KNOWN_FACES_DIR / "owner"

    if args.capture:
        capture_owner_photos(detector, num_samples=args.samples)
        compile_gallery(detector, recognizer, owner_dir)
    elif args.recompile:
        compile_gallery(detector, recognizer, owner_dir)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
