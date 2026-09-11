import asyncio,threading,time
from datetime import datetime
import cv2

import config
from database.database import Database
from esp32.serial_controller import ESP32Controller
from vision.camera import USBCamera
from vision.yolo_detector import PersonDetector
from vision.face_engine import FaceEngine
from vision.overlay import box,header
from security.fusion import Fusion
from security.cooldown import Cooldown
from audio.manager import AudioManager
from bot_service.service import TelegramService
from web.server import set_system,start_server

class Queue:
    def __init__(self,loop):
        self.mode="individual"
        self.alerts=asyncio.Queue()
        self.loop=loop
        self.refresh_faces=lambda:None

class System:
    def __init__(self,loop):
        self.loop=loop
        self.db=Database(config.DB_PATH)
        self.esp=ESP32Controller(config.ESP32_PORT,config.ESP32_BAUD)
        self.cam=USBCamera(config.CAMERA_INDEX)
        self.det=PersonDetector(config.YOLO_MODEL,config.YOLO_CONFIDENCE)
        self.face=FaceEngine(config)
        self.audio=AudioManager(config.GREETING_WAV)
        self.q=Queue(loop)
        self.q.refresh_faces=self.face.load
        self.fusion=Fusion()
        self.cool=Cooldown(config.ALERT_COOLDOWN_SECONDS)
        self.running=False
        self.jpeg=None
        self.lock=threading.Lock()
        self.presence_alerted=False
        self.status_data={}

        self.tg=TelegramService(config,self.db,self.audio,self.esp,self.q)

    def publish(self,frame):
        ok,b=cv2.imencode(".jpg",frame)
        if ok:
            with self.lock: self.jpeg=b.tobytes()

    def get_jpeg(self):
        with self.lock: return self.jpeg

    def status(self):
        with self.lock: return dict(self.status_data)

    def next_event_id(self):
        rows=self.db.recent_events(1)
        if not rows: return "EVT_0001"
        return f"EVT_{int(rows[0]['event_id'].split('_')[-1])+1:04d}"

    def start(self):
        try:
            self.esp.connect()
            print("✅ ESP32 connected:",config.ESP32_PORT)
        except Exception as e:
            print("⚠️ ESP32 unavailable:",e)
            print("Camera can run, but ToF-based HIGH ALERT needs ESP32.")

        self.cam.open()
        self.running=True
        threading.Thread(target=self.loop_camera,daemon=True).start()

    def make_alert(self,frame,persons,result,distance):
        person=persons[0] if persons else None

        # Yellow while identity classification is being performed.
        searching=frame.copy()
        if person: box(searching,person,"SEARCHING")
        header(searching,"SEARCHING",distance,result["dwell"],
               self.q.mode,"HIGH ALERT")
        self.publish(searching)

        # Run the trained identity model exactly once per alert (not every
        # frame) to keep this real-time-friendly, per the fusion architecture.
        rec=None
        try:
            rec=self.face.recognize(frame,person)
        except Exception as e:
            print("⚠️ Identity recognition error:",e)

        # Fail-safe default: if no face could be classified at all, treat as
        # STRANGER. A false OWNER is worse than a false STRANGER.
        status=rec["status"] if rec else "STRANGER"
        confidence=rec["confidence"] if rec else 0.0

        # Internal-only event id, never shown to the owner/user.
        eid=self.next_event_id()
        photo=config.PHOTOS_DIR/f"{eid}.jpg"
        cv2.imwrite(str(photo),frame)

        event={
            "event_id":eid,"classification":status,"confidence":confidence,
            "distance_cm":float(distance),
            "dwell_seconds":float(result["dwell"]),"photo_path":str(photo),
            "status":"HIGH ALERT",
            "created_at":datetime.now().isoformat(timespec="seconds")
        }
        self.db.add_event(event)

        final=frame.copy()
        if person:
            box(final,person,status)
        header(final,status,distance,result["dwell"],
               self.q.mode,"HIGH ALERT")
        self.publish(final)
        return event

    def loop_camera(self):
        print("📷 USB webcam + YOLO running. Camera index:",config.CAMERA_INDEX)
        last_log=0

        while self.running:
            ok,frame=self.cam.read()
            if not ok:
                time.sleep(.2); continue

            persons=self.det.detect(frame)
            person=bool(persons)
            dist=self.esp.distance_cm

            if self.q.mode!=self.fusion.mode:
                self.fusion.set_mode(self.q.mode)

            r=self.fusion.update(person,dist)

            self.status_data={
                "state":r["state"],"mode":self.q.mode,
                "distance_cm":dist,"dwell_seconds":r["dwell"],
                "person_detected":person
            }

            # Only one alert per physical presence.
            if not person or not r["in_zone"]:
                self.presence_alerted=False

            if (r["state"]=="HIGH ALERT" and not self.presence_alerted
                    and self.cool.allowed() and dist is not None):
                try:
                    event=self.make_alert(frame,persons,r,dist)
                    self.cool.mark()
                    self.presence_alerted=True
                    self.fusion.reset()
                    asyncio.run_coroutine_threadsafe(
                        self.q.alerts.put(event),self.loop
                    )
                except Exception as e:
                    print("❌ Alert error:",e)
            else:
                view=frame.copy()
                if persons:
                    box(view,persons[0],"SEARCHING")
                header(view,"SEARCHING",dist,r["dwell"],
                       self.q.mode,r["state"])
                self.publish(view)
                cv2.imshow("Smart Door Security - USB Webcam", view)

                now=time.monotonic()
                if person and now-last_log>=5:
                    note=("PASSIVE: outside ToF zone" if not r["in_zone"]
                          else "DWELL CHECK: inside ToF zone")
                    self.db.add_passive(dist,note)
                    last_log=now

            if cv2.waitKey(1)&0xFF==ord("q"):
                self.running=False
                break
            time.sleep(.01)

        self.cam.release()
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
        print("📷 USB webcam stopped")

    def stop(self):
        self.running=False
        try:self.esp.close()
        except:pass
        try:self.cam.release()
        except:pass

async def run():
    loop=asyncio.get_running_loop()
    system=System(loop)
    set_system(system)
    start_server(config.STREAM_HOST,config.STREAM_PORT)
    system.start()

    print("🌐 http://127.0.0.1:8000/api/live")
    print("🌐 http://127.0.0.1:8000/api/status")

    await system.tg.app.initialize()
    await system.tg.app.start()
    await system.tg.app.updater.start_polling()
    worker=asyncio.create_task(system.tg.alert_worker())

    try:
        while system.running:
            await asyncio.sleep(1)
    finally:
        worker.cancel()
        try: await worker
        except asyncio.CancelledError: pass
        await system.tg.app.updater.stop()
        await system.tg.app.stop()
        await system.tg.app.shutdown()
        system.stop()

if __name__=="__main__":
    asyncio.run(run())
