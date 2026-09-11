"""
Identity engine for the Smart Door Security System.

Backed by the trained ML model supplied for the hackathon:
  - Face detector : YuNet (face_detection_yunet_2023mar.onnx) via cv2.FaceDetectorYN
  - Face recognizer: SFace (face_recognition_sface_2021dec.onnx) via cv2.FaceRecognizerSF
  - Owner gallery  : resident_gallery.npy - pre-enrolled 128-D owner embeddings

This replaces the previous face_recognition/dlib-based engine. The public
interface (recognize()) is kept close to the original so main.py needed only
minimal changes.

Output is deliberately reduced to a simple abstraction:

    status = "OWNER"    -> high-confidence match against the owner gallery
    status = "STRANGER" -> anyone else, or no confident match

No visitor IDs, no auto-enrollment of unknown faces. Internal database IDs
(event_id, etc.) are handled elsewhere and never touch this module.
"""

import cv2
import numpy as np


class FaceEngine:
    def __init__(self, config):
        self.config = config
        self.threshold = config.OWNER_CONFIDENCE_THRESHOLD

        self.detector = cv2.FaceDetectorYN.create(
            model=config.FACE_DETECTOR_MODEL,
            config="",
            input_size=(320, 240),
            score_threshold=0.45,
            nms_threshold=0.30,
        )
        self.recognizer = cv2.FaceRecognizerSF.create(
            model=config.FACE_RECOGNIZER_MODEL,
            config="",
        )

        self.gallery = self._load_gallery()

    # -- gallery -----------------------------------------------------------

    def _load_gallery(self):
        path = self.config.RESIDENT_GALLERY_PATH
        if not path.exists():
            print(f"⚠️ Owner gallery not found at {path}; every visitor will be STRANGER.")
            return None
        gallery = np.load(str(path)).astype(np.float32)
        if gallery.ndim == 1:
            gallery = gallery.reshape(1, -1)
        norms = np.linalg.norm(gallery, axis=1, keepdims=True)
        norms[norms == 0] = 1e-6
        return gallery / norms

    def load(self):
        """Kept for interface compatibility with main.py's Queue.refresh_faces.
        The owner gallery is static for this system (no per-visitor
        enrollment); re-loads the gallery file in case it was recompiled
        (e.g. via enroll_face.py) while the system is running."""
        self.gallery = self._load_gallery()

    # -- matching ------------------------------------------------------------

    def _match_gallery(self, feat):
        if self.gallery is None or len(self.gallery) == 0:
            return 0.0
        feat_norm = feat / (np.linalg.norm(feat) + 1e-6)
        cosines = np.dot(self.gallery, feat_norm.T).flatten()
        k = min(3, len(cosines))
        top_k = np.sort(cosines)[-k:]
        return float(np.mean(top_k))

    def _best_face(self, frame, person_box=None):
        """Detect faces in the frame and return the one that best matches
        the YOLO person box (if given), else the largest face."""
        h, w = frame.shape[:2]
        self.detector.setInputSize((w, h))
        _, faces = self.detector.detect(frame)
        if faces is None or len(faces) == 0:
            return None

        if person_box:
            x1, y1, x2, y2, _ = person_box
            inside = []
            for f in faces:
                fx, fy, fw, fh = f[:4]
                cx, cy = fx + fw / 2, fy + fh / 2
                if x1 <= cx <= x2 and y1 <= cy <= y2:
                    inside.append(f)
            if inside:
                faces = inside

        # Prefer the largest candidate face.
        return max(faces, key=lambda f: f[2] * f[3])

    def recognize(self, frame, person_box=None):
        """Run the trained identity model on one frame.

        Returns {"status": "OWNER"|"STRANGER", "confidence": float}
        or None if no face could be found at all.
        """
        face = self._best_face(frame, person_box)
        if face is None:
            return None

        aligned = self.recognizer.alignCrop(frame, face)
        feat = self.recognizer.feature(aligned)
        score = self._match_gallery(feat)

        # Safety rule: only a high-confidence match counts as OWNER.
        # Anything else (including the model's own "uncertain" band) is
        # treated as STRANGER -- a false OWNER is worse than a false STRANGER.
        status = "OWNER" if score >= self.threshold else "STRANGER"
        return {"status": status, "confidence": score}
