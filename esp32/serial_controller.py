import time, threading
import serial

class ESP32Controller:
    def __init__(self,port,baud=115200):
        self.port=port; self.baud=baud
        self.ser=None; self.distance_cm=None
        self.running=False

    def connect(self):
        self.ser=serial.Serial(self.port,self.baud,timeout=.5)
        time.sleep(2)
        self.ser.reset_input_buffer()
        self.running=True
        threading.Thread(target=self._reader,daemon=True).start()

    def _reader(self):
        while self.running and self.ser:
            try:
                line=self.ser.readline().decode(errors="ignore").strip()
                if line.startswith("DIST:"):
                    mm=float(line.split(":",1)[1])
                    if mm < 8000:
                        self.distance_cm=mm/10
                    else:
                        self.distance_cm=None
                elif line=="DIST_INVALID":
                    # Sensor sees nothing in range -> treat as "far away",
                    # not "keep last known close reading".
                    self.distance_cm=None
            except Exception:
                time.sleep(.2)

    def send(self,cmd):
        if self.ser and self.ser.is_open:
            self.ser.write((cmd+"\n").encode())

    def buzzer_on(self): self.send("BUZZER_ON")
    def buzzer_off(self): self.send("BUZZER_OFF")
    def ping(self): self.send("PING")

    def close(self):
        self.running=False
        try:
            self.buzzer_off()
            if self.ser: self.ser.close()
        except Exception:
            pass
