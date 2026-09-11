import cv2

class USBCamera:
    def __init__(self,index=1):
        self.index=index
        self.cap=None

    def open(self):
        self.cap=cv2.VideoCapture(self.index,cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            self.cap.release()
            self.cap=cv2.VideoCapture(self.index)
        if not self.cap.isOpened():
            raise RuntimeError(f"USB webcam index {self.index} could not be opened")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT,720)

    def read(self):
        return self.cap.read()

    def release(self):
        if self.cap:
            self.cap.release()
            self.cap=None
