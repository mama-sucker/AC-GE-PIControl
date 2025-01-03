from flask import Flask, render_template, jsonify, request
import RPi.GPIO as GPIO
import time
from datetime import datetime
import threading
import schedule
import socket
import json
import os

app = Flask(__name__)

# GPIO Setup
FAN_LOW = 17
FAN_MEDIUM = 27
FAN_HIGH = 22
COMPRESSOR = 26
SPEAKER = 23

# Global variables
current_mode = "off"
current_fan_speed = "low"
timer_thread = None
schedule_thread = None
stop_timer = threading.Event()

def get_ip_address():
    """Get the local IP address of the Raspberry Pi"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

class ACController:
    def __init__(self):
        # Setup GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        # Setup pins
        self.pins = {
            FAN_LOW: "Fan Low",
            FAN_MEDIUM: "Fan Medium",
            FAN_HIGH: "Fan High",
            COMPRESSOR: "Compressor",
            SPEAKER: "Speaker"
        }
        
        # Initialize all pins to OFF state (LOW)
        for pin in self.pins:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)
        
        self.current_fan = None
        self.compressor_running = False
        self.timer_running = False
    
    def beep(self):
        """Activate speaker for status change indication"""
        GPIO.output(SPEAKER, GPIO.HIGH)
        time.sleep(0.2)
        GPIO.output(SPEAKER, GPIO.LOW)
    
    def turn_on_fan(self, fan_pin):
        """Turn on selected fan speed"""
        # Turn off all fans first
        for pin in [FAN_LOW, FAN_MEDIUM, FAN_HIGH]:
            GPIO.output(pin, GPIO.LOW)
        
        # Turn on selected fan
        GPIO.output(fan_pin, GPIO.HIGH)
        self.current_fan = fan_pin
        self.beep()
        return True
    
    def turn_on_compressor(self):
        """Turn on compressor with safety delay"""
        if self.current_fan is not None:
            print("Waiting 3 seconds before starting compressor...")
            time.sleep(3)
            GPIO.output(COMPRESSOR, GPIO.HIGH)
            self.compressor_running = True
            self.beep()
            return True
        return False
    
    def turn_off_compressor(self):
        """Turn off compressor first"""
        if self.compressor_running:
            GPIO.output(COMPRESSOR, GPIO.LOW)
            self.compressor_running = False
            self.beep()
            print("Waiting 3 seconds before turning off fan...")
            time.sleep(3)
    
    def turn_off_all(self):
        """Turn off all outputs with proper sequencing"""
        self.turn_off_compressor()
        for pin in [FAN_LOW, FAN_MEDIUM, FAN_HIGH]:
            GPIO.output(pin, GPIO.LOW)
        self.current_fan = None
        self.beep()
    
    def run_compressor_cycle(self, fan_pin):
        """Run the 30/15 minute cycle for compressor operation"""
        while not stop_timer.is_set():
            print("Starting new compressor cycle...")
            self.turn_on_fan(fan_pin)
            self.turn_on_compressor()
            
            cycle_end_time = time.time() + 1800  # 30 minutes
            while time.time() < cycle_end_time and not stop_timer.is_set():
                time.sleep(1)
            
            if stop_timer.is_set():
                break
            
            self.turn_off_compressor()
            
            fan_cycle_end = time.time() + 900  # 15 minutes
            while time.time() < fan_cycle_end and not stop_timer.is_set():
                time.sleep(1)
            
            if stop_timer.is_set():
                break
    
    def safe_shutdown(self):
        """Safely shut down the system"""
        self.turn_off_all()
        time.sleep(1)
        GPIO.cleanup()

ac = ACController()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/control', methods=['POST'])
def control():
    global timer_thread, current_mode, current_fan_speed
    
    try:
        print(f"Raw request data: {request.get_data().decode('utf-8', errors='ignore')}")
        print(f"Content-Type: {request.content_type}")
        
        # Initialize data dictionary
        data = {}
        
        # Handle different content types
        if request.content_type == 'application/json':
            data = request.get_json(force=True, silent=True) or {}
        elif request.content_type == 'application/x-www-form-urlencoded':
            data = request.form.to_dict()
        elif 'xml' in request.content_type:
            # Parse Fauxmo's XML data
            xml_data = request.get_data().decode('utf-8')
            if 'BinaryState' in xml_data:
                state = '1' in xml_data
                data = {
                    'mode': 'with_compressor' if state else 'off',
                    'fan_speed': 'low'
                }
        else:
            # Try to parse as form data if content type is not specified
            data = request.form.to_dict()
            if not data and request.get_data():
                # Try to parse as URL-encoded data
                raw_data = request.get_data().decode('utf-8')
                if 'mode=' in raw_data:
                    data = dict(item.split('=') for item in raw_data.split('&'))
        
        print(f"Processed request data: {data}")
        
        if not data:
            return jsonify({"status": "error", "message": "No valid data received"}), 400
        
        # Get mode from data, default to 'off'
        mode = data.get('mode', 'off')
        current_mode = mode
        
        # Stop any running timer
        stop_timer.set()
        if timer_thread and timer_thread.is_alive():
            timer_thread.join()
        stop_timer.clear()
        
        if mode == 'off':
            print("Turning off AC")
            ac.turn_off_all()
            return jsonify({"status": "success", "message": "AC turned off"})
        
        fan_speed = data.get('fan_speed', 'low')
        current_fan_speed = fan_speed
        
        fan_pins = {
            'low': FAN_LOW,
            'medium': FAN_MEDIUM,
            'high': FAN_HIGH
        }
        
        fan_pin = fan_pins.get(fan_speed)
        if not fan_pin:
            print(f"Invalid fan speed: {fan_speed}")
            return jsonify({"status": "error", "message": "Invalid fan speed"}), 400
        
        if mode == 'fan_only':
            print("Activating fan only mode")
            ac.turn_on_fan(fan_pin)
            return jsonify({"status": "success", "message": "Fan mode activated"})
        elif mode == 'with_compressor':
            print("Starting compressor cycle")
            timer_thread = threading.Thread(target=ac.run_compressor_cycle, args=(fan_pin,))
            timer_thread.start()
            return jsonify({"status": "success", "message": "Compressor cycle started"})
        
        print(f"Invalid mode selected: {mode}")
        return jsonify({"status": "error", "message": "Invalid mode selected"}), 400
    
    except Exception as e:
        print(f"Error in control endpoint: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({"status": "error", "message": str(e)}), 500

def create_fauxmo_config():
    """Create Fauxmo configuration file"""
    local_ip = get_ip_address()
    print(f"Creating Fauxmo config with local IP: {local_ip}")
    
    config = {
        "FAUXMO": {
            "ip_address": local_ip
        },
        "PLUGINS": {
            "SimpleHTTPPlugin": {
                "DEVICES": [
                    {
                        "name": "AC",
                        "port": 12340,
                        "on_cmd": f"http://{local_ip}:5000/api/control",
                        "off_cmd": f"http://{local_ip}:5000/api/control",
                        "method": "POST",
                        "on_data": "mode=with_compressor&fan_speed=low",  # Changed to form data format
                        "off_data": "mode=off",  # Changed to form data format
                        "state_cmd": f"http://{local_ip}:5000/api/status",
                        "state_method": "GET",
                        "state_response_on": "on",
                        "state_response_off": "off",
                        "headers": {
                            "Content-Type": "application/x-www-form-urlencoded"  # Changed content type
                        }
                    }
                ]
            }
        }
    }
    
    config_path = os.path.abspath('fauxmo_config.json')
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)
    print(f"Fauxmo config saved to: {config_path}")
    return config_path 

@app.route('/api/status', methods=['GET'])
def get_status():
    global current_mode, current_fan_speed
    
    # Return "on" if the AC is in any active mode (fan_only or with_compressor)
    # Return "off" if the AC is off
    status = "on" if current_mode != "off" else "off"
    
    return jsonify({
        "status": status,
        "mode": current_mode,
        "fan_speed": current_fan_speed
    })

if __name__ == '__main__':
    try:
        config_path = create_fauxmo_config()
        print(f"Starting Flask app. Use 'fauxmo -c {config_path} -v' to start Fauxmo")
        app.run(host='0.0.0.0', port=5000, debug=True)
    finally:
        ac.safe_shutdown()
