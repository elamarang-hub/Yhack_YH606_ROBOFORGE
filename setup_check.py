import importlib,shutil
mods=["cv2","ultralytics","serial","telegram","pygame","numpy",
      "fastapi","uvicorn","pyttsx3","pyaudio","dotenv"]
for m in mods:
    try:
        importlib.import_module(m); print("OK  ",m)
    except Exception as e:
        print("FAIL",m,":",e)
print("FFmpeg:",shutil.which("ffmpeg") or "NOT FOUND")

# Identity model check (YuNet + SFace, ONNX, loaded via OpenCV).
try:
    import cv2
    import config
    assert hasattr(cv2,"FaceDetectorYN") and hasattr(cv2,"FaceRecognizerSF")
    print("OK  ","cv2.FaceDetectorYN / cv2.FaceRecognizerSF")
    for label,path in [("YuNet model",config.FACE_DETECTOR_MODEL),
                        ("SFace model",config.FACE_RECOGNIZER_MODEL)]:
        print("OK  " if __import__("os").path.exists(path) else "FAIL", label, path)
    print("OK  " if config.RESIDENT_GALLERY_PATH.exists() else "FAIL",
          "Owner gallery", config.RESIDENT_GALLERY_PATH)
except Exception as e:
    print("FAIL","identity model check:",e)
