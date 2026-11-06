import sys
import time
import network
import machine
import urequests
import json
from machine import Pin, time_pulse_us, PWM

sys.stdout.write("\n====================================\n")
sys.stdout.write("--> ESP32 SECURITY SYSTEM <--\n")
sys.stdout.write("====================================\n")
if hasattr(sys.stdout, 'flush'):
    sys.stdout.flush()

time.sleep(0.5)

# Cấu hình Adafruit IO
AIO_USERNAME = "pdung144"
AIO_KEY      = "aio_HZot10zdsdveC95Vh70U4cQMzcqC"
AIO_FEED     = "security-system"

# Khai báo chân GPIO
pir = Pin(13, Pin.IN)
trig = Pin(12, Pin.OUT)
echo = Pin(14, Pin.IN)
led = Pin(26, Pin.OUT)

# Khai báo PWM còi hú chân 27
buzzer_pwm = PWM(Pin(27))
buzzer_pwm.duty(0)

system_armed = False
alarm_triggered = False

def sound_alarm():
    buzzer_pwm.freq(2000)
    buzzer_pwm.duty(512)

def mute_alarm():
    buzzer_pwm.duty(0)

def get_distance():
    trig.value(0)
    time.sleep_us(2)
    trig.value(1)
    time.sleep_us(10)
    trig.value(0)
    try:
        pulse_time = time_pulse_us(echo, 1, 30000)
        if pulse_time > 0:
            return round((pulse_time / 2) / 29.1, 1)
    except:
        pass
    return 999.0

# Kết nối WiFi
print("[WIFI] Connecting to Wokwi-GUEST...", end="")
wlan = network.WLAN(network.STA_IF)
wlan.active(False)
time.sleep(0.2)
wlan.active(True)
wlan.connect("Wokwi-GUEST", "")

retry_wifi = 0
while not wlan.isconnected() and retry_wifi < 40:
    print(".", end="")
    time.sleep(0.5)
    retry_wifi += 1

if wlan.isconnected():
    print(f"\n[WIFI OK] IP: {wlan.ifconfig()[0]}")

last_publish = time.ticks_ms()
last_check_cmd = time.ticks_ms()

def send_to_adafruit(payload_dict):
    url = f"https://io.adafruit.com/api/v2/{AIO_USERNAME}/feeds/{AIO_FEED}/data"
    headers = {'X-AIO-Key': AIO_KEY, 'Content-Type': 'application/json'}
    try:
        res = urequests.post(url, json={"value": json.dumps(payload_dict)}, headers=headers)
        res.close()
        print("[HTTP API] Sent JSON successfully!")
    except Exception as e:
        print("[HTTP API ERROR]:", e)

def check_cmd_from_adafruit():
    global system_armed, alarm_triggered
    url = f"https://io.adafruit.com/api/v2/{AIO_USERNAME}/feeds/{AIO_FEED}/data/last"
    headers = {'X-AIO-Key': AIO_KEY}
    try:
        res = urequests.get(url, headers=headers)
        if res.status_code == 200:
            val = res.json().get('value', '')
            if val.upper() in ["ARM", "ON", "1"]:
                if not system_armed:
                    system_armed = True
                    alarm_triggered = False
                    print("-> [CLOUD CMD] MODE: ARMED")
            elif val.upper() in ["DISARM", "OFF", "0"]:
                if system_armed:
                    system_armed = False
                    alarm_triggered = False
                    mute_alarm()
                    led.value(0)
                    print("-> [CLOUD CMD] MODE: DISARMED")
        res.close()
    except Exception as e:
        pass

print("\n--- SYSTEM MONITORING READY ---")

while True:
    current_time = time.ticks_ms()

    # Kiểm tra lệnh 2s/lần
    if time.ticks_diff(current_time, last_check_cmd) >= 2000:
        last_check_cmd = current_time
        check_cmd_from_adafruit()

    # Đọc cảm biến & gửi dữ liệu 3s/lần
    if time.ticks_diff(current_time, last_publish) >= 3000:
        last_publish = current_time
        motion_val = pir.value()
        dist_val = get_distance()
        mode_str = "ARMED" if system_armed else "DISARMED"
        
        print(f"[STATUS] Mode: {mode_str} | PIR: {motion_val} | Dist: {dist_val}cm")
        
        payload = {"mode": mode_str, "pir": motion_val, "dist": dist_val}
        send_to_adafruit(payload)

    # Báo động tại chỗ
    if system_armed:
        motion_val = pir.value()
        dist_val = get_distance()
        if motion_val == 1 or dist_val < 50.0:
            alarm_triggered = True
            sound_alarm()
            led.value(1)
            print("!!! CANH BAO: PHAT HIEN XAM NHAP !!!")
        else:
            if not alarm_triggered:
                mute_alarm()
                led.value(0)
    else:
        mute_alarm()
        led.value(0)

    time.sleep(0.05)