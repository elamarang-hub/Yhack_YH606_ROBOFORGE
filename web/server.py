import threading,uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app=FastAPI(title="Smart Door Security")
SYSTEM=None

def set_system(system):
    global SYSTEM
    SYSTEM=system

def frames():
    while True:
        if SYSTEM is None:
            continue
        b=SYSTEM.get_jpeg()
        if b:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"+b+b"\r\n"

@app.get("/api/live")
def live():
    return StreamingResponse(frames(),media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/api/status")
def status():
    return SYSTEM.status() if SYSTEM else {"status":"starting"}

def start_server(host="0.0.0.0",port=8000):
    t=threading.Thread(
        target=uvicorn.run,
        args=(app,),
        kwargs={"host":host,"port":port,"log_level":"warning"},
        daemon=True
    )
    t.start()
