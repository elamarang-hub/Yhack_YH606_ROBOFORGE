import time

class Cooldown:
    def __init__(self,seconds):
        self.seconds=seconds
        self.last=0

    def allowed(self):
        return time.monotonic()-self.last>=self.seconds

    def mark(self):
        self.last=time.monotonic()
