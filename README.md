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
        |
        v
ToF Distance Detection
        |
        v
Dwell-Time Validation
        |
        v
Person Detection
        |
        v
Face Recognition
        |
        v
Camera Capture
        |
        v
 +---------------+
 |               |
Known         Stranger
Person           |
 │               |
 +-------+-------+
         |
         v
Telegram Notification + image 
         |
         v
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

- The active buzzer acts as the local audible alarm.
- An active buzzer can generate a sound when activated by the ESP32.

   Main Functions:
   - Generate a local security alert
   - Warn a visitor or stranger
   - Respond to security-system commands
   - Support Telegram-controlled alarm functionality
   - Automatically turn off after the configured duration

5. INMP441 I2S Microphone:

- The INMP441 is a digital MEMS microphone used to capture the visitor's voice.
- It communicates digitally with the ESP32 using the I2S interface.

   Main Functions:
   - Capture audio near the door
   - Record visitor voice
   - Send microphone audio to the ESP32
   - Support visitor-to-owner communication
   - Provide audio for Telegram communication

6. MAX98357A I2S Audio Amplifier:

- The MAX98357A is a digital I2S audio amplifier used to drive the speaker.
- The ESP32 sends digital audio to the MAX98357A, which converts and amplifies the signal for the speaker.

   Main Functions:
   - Receive I2S digital audio from the ESP32
   - Convert digital audio for speaker playback
   - Amplify the audio signal
   - Drive the speaker

7. Speaker:

- The speaker provides audio output near the door.
- It works with the MAX98357A amplifier and ESP32.

   Main Functions:
   - Play owner's voice
   - Play warning audio
   - Provide local audio output

8. Laptop / Local Computer:
- The laptop or local computer acts as the main Edge AI processing unit and backend server.
- The ESP32 is used mainly for sensors and hardware control, while the laptop performs computationally intensive AI operations.

   Main Functions:
   - Receive camera frames
   - Run YOLOv8n person detection
   - Perform face detection
   - Perform face recognition
   - Compare known-face encodings
   - Perform visitor tracking
   - Run dwell-time logic
   - Handle WebSocket communication
   - Run the Telegram bot
   - Send Telegram notifications
   - Store visitor events
   - Manage the SQLite database
   - Handle audio bridging

### Hardware workflow

```text

Visitor Approaches Door
          |
          v
+-------------------------+
|        Camera           |
| Captures live video     |
+-----------+-------------+
            |
            | USB Video
            v
+-------------------------+
| Edge AI Laptop          |
|                         |
| - OpenCV                |
| - YOLOv8n               |
| - Face Recognition      |
| - SQLite                |
| - Resnet                |
| - Telegram              |
+-----------+-------------+
            ^
            |
          Wi-Fi 
            |
            v
+-------------------------+
| ESP32 Controller        |
+-----------+-------------+
            |
      +-----+------+----------------+
      |            |                |
      v            v                v
 VL53L0X       INMP441          Active Buzzer
 ToF Sensor    Microphone       Alarm
      |            |
 Distance       Visitor Voice
      |            |
      +------------+
            |
            v
          ESP32
            |
            | I2S Audio Output
            v
      +-------------+
      | MAX98357A   |
      | Amplifier   |
      +------+------+
             |
             v
        4Ω 3W Speaker
             |
             v
          Visitor

```
