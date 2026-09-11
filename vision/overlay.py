import cv2

# User-facing identity colors only: SEARCHING (yellow), OWNER (green), STRANGER (red).
_COLORS = {"SEARCHING": (0, 255, 255), "OWNER": (0, 255, 0), "STRANGER": (0, 0, 255)}


def box(frame, person, status, label=None):
    color = _COLORS.get(status, (0, 255, 255))
    x1, y1, x2, y2, conf = person
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    cv2.putText(frame, label or status, (x1, max(20, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, .55, color, 2)


def header(frame, status, distance, dwell, mode, state):
    """Live overlay header. Only ever shows SEARCHING / OWNER / STRANGER --
    no visitor IDs or event IDs are ever drawn here."""
    color = _COLORS.get(status, (0, 255, 255))
    cv2.putText(frame, status, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, .7, color, 2)
    d = "N/A" if distance is None else f"{distance:.0f} cm"
    info = f"MODE:{mode.upper()}  STATE:{state}  TOF:{d}  DWELL:{dwell:.1f}s"
    cv2.putText(frame, info, (20, 68), cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 2)
