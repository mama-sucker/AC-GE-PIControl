from flask import Flask, render_template, jsonify, request
import RPi.GPIO as GPIO
import time
from datetime import datetime
import threading
import schedule

app = Flask(__name__)

# GPIO Setup
FAN_LOW = 17
FAN_MEDIUM = 27
FAN_HIGH = 22
COMPRESSOR = 26
SPEAKER = 23

# Global variables
current_mode = "off"
timer_thread = None
schedule_thread = None
stop_timer = threading.Event()

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
        
        # Initialize all pins to ON state (LOW)
        for pin in self.pins:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)
        
        self.current_fan = None
        self.compressor_running = False
        self.timer_running = False
    
    def beep(self):
        """Activate speaker for status change indication"""
        GPIO.output(SPEAKER, GPIO.HIGH)  # Turn speaker ON
        time.sleep(0.2)
        GPIO.output(SPEAKER, GPIO.LOW)   # Turn speaker OFF
    
    def turn_on_fan(self, fan_pin):
        """Turn on selected fan speed"""
        # Turn off all fans first
        for pin in [FAN_LOW, FAN_MEDIUM, FAN_HIGH]:
            GPIO.output(pin, GPIO.LOW)  # Ensure all fans are off initially
        
        # Turn on selected fan
        GPIO.output(fan_pin, GPIO.HIGH)  # Activate selected fan
        self.current_fan = fan_pin
        self.beep()
        
        # Return success status
        return True
    
    def turn_on_compressor(self):
        """Turn on compressor with safety delay"""
        if self.current_fan is not None:
            print("Waiting 3 seconds before starting compressor...")
            time.sleep(3)  # 3-second safety delay
            GPIO.output(COMPRESSOR, GPIO.HIGH)  # Turn on compressor
            self.compressor_running = True
            self.beep()
            return True
        return False
    
    def turn_off_compressor(self):
        """Turn off compressor first"""
        if self.compressor_running:
            GPIO.output(COMPRESSOR, GPIO.LOW)  # Turn off compressor
            self.compressor_running = False
            self.beep()
            print("Waiting 3 seconds before turning off fan...")
            time.sleep(3)  # 3-second safety delay before fan can be turned off
    
    def turn_off_all(self):
        """Turn off all outputs with proper sequencing"""
        # First turn off compressor if running
        self.turn_off_compressor()
        
        # Then turn off all fans
        for pin in [FAN_LOW, FAN_MEDIUM, FAN_HIGH]:
            GPIO.output(pin, GPIO.LOW)
        
        self.current_fan = None
        self.beep()
    
    def run_compressor_cycle(self, fan_pin):
        """Run the 30/15 minute cycle for compressor operation"""
        while not stop_timer.is_set():
            print("Starting new compressor cycle...")
            
            # Turn on fan first
            self.turn_on_fan(fan_pin)
            
            # Turn on compressor after delay
            self.turn_on_compressor()
            
            # Run for 30 minutes
            cycle_end_time = time.time() + 1800  # 30 minutes
            while time.time() < cycle_end_time and not stop_timer.is_set():
                time.sleep(1)
            
            if stop_timer.is_set():
                break
            
            # Turn off compressor but keep fan running
            self.turn_off_compressor()
            
            # Run fan only for 15 minutes
            fan_cycle_end = time.time() + 900  # 15 minutes
            while time.time() < fan_cycle_end and not stop_timer.is_set():
                time.sleep(1)
            
            if stop_timer.is_set():
                break
    
    def safe_shutdown(self):
        """Safely shut down the system"""
        self.turn_off_all()
        time.sleep(1)  # Give time for all operations to complete
        GPIO.cleanup()

ac = ACController()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/control', methods=['POST'])
def control():
    global timer_thread, current_mode
    
    data = request.get_json()
    mode = data.get('mode')
    current_mode = mode
    
    # Stop any running timer
    stop_timer.set()
    if timer_thread and timer_thread.is_alive():
        timer_thread.join()
    stop_timer.clear()
    
    if mode == 'off':
        ac.turn_off_all()
        return jsonify({"status": "success", "message": "AC turned off"})
    
    fan_pins = {
        'low': FAN_LOW,
        'medium': FAN_MEDIUM,
        'high': FAN_HIGH
    }
    
    fan_pin = fan_pins.get(data.get('fan_speed', 'low'))
    
    if 'fan_only' in mode:
        ac.turn_on_fan(fan_pin)
        return jsonify({"status": "success", "message": "Fan mode activated"})
    elif 'with_compressor' in mode:
        timer_thread = threading.Thread(target=ac.run_compressor_cycle, args=(fan_pin,))
        timer_thread.start()
        return jsonify({"status": "success", "message": "Compressor cycle started"})
    
    return jsonify({"status": "error", "message": "Invalid mode selected"})

@app.route('/api/schedule', methods=['POST'])
def set_schedule():
    data = request.get_json()
    start_time = data.get('start_time')
    end_time = data.get('end_time')
    mode = data.get('mode')
    fan_speed = data.get('fan_speed')
    
    # Clear existing schedule
    schedule.clear()
    
    # Schedule start
    schedule.every().day.at(start_time).do(
        lambda: control({"mode": mode, "fan_speed": fan_speed})
    )
    
    # Schedule stop
    schedule.every().day.at(end_time).do(
        lambda: control({"mode": "off"})
    )
    
    return jsonify({"status": "success", "message": f"Schedule set: {start_time} to {end_time}"})

def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(60)

# Start schedule thread
schedule_thread = threading.Thread(target=run_schedule)
schedule_thread.daemon = True
schedule_thread.start()

if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5000, debug=True)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ac.safe_shutdown()
