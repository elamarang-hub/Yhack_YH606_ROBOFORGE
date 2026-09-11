import time

class Fusion:
    def __init__(self,mode="individual"):
        self.mode=mode
        self.start=None

    def set_mode(self,mode):
        self.mode=mode
        self.reset()

    def reset(self):
        self.start=None

    def limits(self):
        if self.mode=="apartment":
            return 50.0,3.0
        return 120.0,2.0

    def update(self,person,distance):
        now=time.monotonic()
        limit,dwell_limit=self.limits()
        zone=distance is not None and distance < limit

        if person and zone:
            if self.start is None:
                self.start=now
            dwell=now-self.start
        else:
            self.start=None
            dwell=0

        if person and zone and dwell>=dwell_limit:
            state="HIGH ALERT"
        elif person and zone:
            state="DWELL CHECK"
        else:
            state="PASSIVE"

        return {"state":state,"in_zone":zone,"dwell":dwell,
                "dwell_reached":dwell>=dwell_limit}
