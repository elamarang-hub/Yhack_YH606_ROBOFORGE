from ultralytics import YOLO

class PersonDetector:
    def __init__(self,model_path="yolov8n.pt",confidence=0.50):
        self.model=YOLO(model_path)
        self.confidence=confidence

    def detect(self,frame):
        result=self.model(frame,verbose=False)[0]
        persons=[]
        if result.boxes is not None:
            for b in result.boxes:
                if int(b.cls[0])==0 and float(b.conf[0])>=self.confidence:
                    x1,y1,x2,y2=map(int,b.xyxy[0].tolist())
                    persons.append((x1,y1,x2,y2,float(b.conf[0])))
        return persons
