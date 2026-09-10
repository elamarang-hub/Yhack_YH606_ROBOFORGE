# Yhack_YH606_ROBOFORGE
An intelligent door security system combining ToF sensing, person detection, face recognition, and Telegram notifications.

## Project Description

The **Smart Door Security System Using Edge AI** is an intelligent security system designed to detect and identify people standing near a door and immediately notify the owner through **Telegram**.

The system combines an **ESP32, Time-of-Flight (ToF) distance sensor, camera, active buzzer, microphone, speaker, and Edge AI processing**.

The ToF sensor continuously measures the distance in front of the door. When a person comes within the configured detection range, the system starts monitoring how long the person remains near the door.

This **dwell-time detection** helps prevent unnecessary alerts when somebody simply walks past the door.

Once a visitor is confirmed, the camera captures the person and the Edge AI system performs:

- Person detection
- Face detection
- Face recognition
- Known/unknown visitor classification

If the visitor is recognized, the system sends a Telegram notification containing the person's name.

Example:

> 🚪 **Visitor Alert**  
> visitorName has arrived at your house.

If the visitor is not recognized, the owner receives a security alert.

Example:

> ⚠️ **Security Alert**  
> Stranger detected at your door.

A captured image of the visitor can also be sent through Telegram.

The owner can interact with the security system using the Telegram bot. The system also supports alarm/buzzer control and is designed to support two-way audio communication between the owner and the visitor.

### Basic System Flow

```text
Person Approaches Door
        ↓
ToF Distance Detection
        ↓
Dwell-Time Validation
        ↓
Person Detection
        ↓
Face Recognition
        ↓
Camera Capture
        ↓ 
 ┌───────────────┐
 │               │
Known         Stranger
Person
 │               │
 └───────┬───────┘
         ↓
Telegram Notification + image 
         ↓
       Owner
```

## Hardware Components 
1. ESP32 Development Board:

- The ESP32 is the main microcontroller and hardware-control unit of the Smart Door Security System.
- It provides communication between the physical door-side hardware and the Edge AI system running on the laptop/local computer.

    Main Responsibilities:
    - Connect to Wi-Fi
    - Read the VL53L0X ToF sensor
    - Send sensor readings to the backend
    - Receive commands from the backend
    - Control the active buzzer
    - Interface with the microphone
    - Interface with the speaker/amplifier
    - Handle real-time hardware communication

2. VL53L0X Time-of-Flight Sensor:

- The VL53L0X is a Time-of-Flight distance sensor used to determine whether a person is physically close to the door.
- It measures the distance between the sensor and the object/person in front of it.

    Purpose:
    - Detect a visitor near the door
    - Measure visitor distance
    - Start dwell-time monitoring
    - Confirm whether a person remains near the door
    - Reduce false alerts
    - Distinguish between a passer-by and a visitor

3. Camera:

- The camera provides visual information to the Edge AI system.
- The camera continuously captures frames that can be processed by the computer-vision modules.

   Main Functions:
   - Capture visitor video
   - Capture visitor images
   - Provide frames for person detection
   - Provide frames for face detection
   - Provide facial information for recognition
   - Capture images for Telegram notifications

4. Active Buzzer:
