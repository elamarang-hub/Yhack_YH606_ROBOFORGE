import cv2
for i in range(5):
    cap=cv2.VideoCapture(i,cv2.CAP_DSHOW)
    if cap.isOpened():
        print("Camera found:",i)
        ok,frame=cap.read()
        if ok:
            cv2.imshow(f"Camera {i}",frame)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        cap.release()
    else:
        print("No camera:",i)
