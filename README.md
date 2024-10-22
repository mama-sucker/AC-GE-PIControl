# Raspberry Pi AC Control System

## Description
This project is a web-based Python script that allows you to control an air conditioner using a Raspberry Pi and an 8-channel relay. The system is built using Flask for the web interface and RPi.GPIO for controlling the GPIO pins on the Raspberry Pi. It includes features like setting schedules and controlling fan speeds and the compressor.

## Features
- Web-based control interface.
- Control fan speeds (low, medium, high).
- Control the compressor.
- Set schedules for automatic control.
- Audio feedback using a speaker.

## Requirements
- Flask
- RPi.GPIO
- schedule

## Installation
1. Clone the repository:
    ```bash
    git clone https://github.com/yourusername/raspberry-pi-ac-control.git
    cd raspberry-pi-ac-control
    ```

2. Install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```

3. Run the Flask application:
    ```bash
    python app.py
    ```

## Usage
1. Open your web browser and navigate to `http://<Raspberry_Pi_IP>:5000`.
2. Use the interface to control the AC, set fan speeds, and schedule operations.

## GPIO Pinout
- **FAN_LOW**: GPIO 17
- **FAN_MEDIUM**: GPIO 27
- **FAN_HIGH**: GPIO 22
- **COMPRESSOR**: GPIO 26
- **SPEAKER**: GPIO 23

## Notes
- Ensure that your relay is connected correctly to the GPIO pins listed above.
- The system gives audio feedback via the speaker for status changes.

## Safety Shutdown
The system includes a safe shutdown procedure that ensures all GPIO pins are turned off and cleaned up properly when the application is terminated.

## License
This project is licensed under the MIT License.
