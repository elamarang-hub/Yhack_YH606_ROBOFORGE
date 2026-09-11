import sys
import time
import serial


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "COM6"

    print(f"Connecting to {port}...")

    ser = serial.Serial(
        port=port,
        baudrate=115200,
        timeout=1
    )

    print("Serial port opened.")
    print("Waiting for ESP32 to finish rebooting...")

    # Opening COM port may reset ESP32.
    time.sleep(3)

    # Remove boot messages already waiting in the buffer
    ser.reset_input_buffer()

    print("Sending PING...")

    ser.write(b"PING\n")
    ser.flush()

    start = time.time()
    got_pong = False

    while time.time() - start < 3:
        line = ser.readline().decode(
            errors="ignore"
        ).strip()

        if line:
            print("ESP32:", line)

            if line == "PONG":
                got_pong = True

    print()

    if got_pong:
        print("================================")
        print("PING/PONG TEST: SUCCESS")
        print("ESP32 COMMUNICATION: OK")
        print("================================")
    else:
        print("================================")
        print("PING/PONG TEST: FAILED")
        print("No PONG received.")
        print("================================")

    print()
    print("Reading distance for 10 seconds...")

    start = time.time()

    while time.time() - start < 10:

        line = ser.readline().decode(
            errors="ignore"
        ).strip()

        if line.startswith("DIST:"):
            print(line)

    ser.close()

    print()
    print("Serial test finished.")


if __name__ == "__main__":
    main()