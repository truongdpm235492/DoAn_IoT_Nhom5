import time
import network
from machine import Pin, PWM
from umqtt.simple import MQTTClient
from config import WIFI_SSID, WIFI_PASS, AIO_SERVER, AIO_PORT, AIO_USER, AIO_KEY, GROUP

# ============ PROJECT 3: NODE CỬA RA VÀO (CỬA SƠ TÁN) ============
# emergency_status = HOT / SMOKE / FIRE / TEST  -> MỞ cửa ra vào
# emergency_status = SAFE                       -> đóng cửa
# manual-vent KHÔNG ảnh hưởng cửa ra vào (nút cửa thông gió chỉ mở cửa thông gió).
# Nút bấm tại chỗ (GPIO4): mở cửa 5 giây khi không có báo động.
# LED đỏ: nhấp nháy khi báo động (nhanh = cháy/test, chậm = khói). LED xanh: đang mở cửa bằng nút.


def topic(name):
    return "{}/f/{}.{}".format(AIO_USER, GROUP, name)


T_EMERGENCY = topic("emergency_status")
T_DOOR = topic("door-state")

LOCAL_OPEN_MS = 5000

servo = PWM(Pin(18), freq=50)
btn_door = Pin(4, Pin.IN)          # có điện trở kéo xuống ngoài, nhấn = 1
led_red = Pin(12, Pin.OUT)
led_green = Pin(13, Pin.OUT)

mode = "SAFE"
local_active = False
local_t0 = 0
door_open = None
last_btn = 0
pub_door = None


def parse_mode(value):
    v = value.strip().upper()
    if v in ("FIRE", "ON", "1", "TRUE"):
        return "FIRE"
    if v == "TEST":
        return "TEST"
    if v == "SMOKE":
        return "SMOKE"
    if v == "HOT":
        return "HOT"
    return "SAFE"


def set_servo_angle(angle):
    pulse_us = 500 + angle * 2000 // 180
    servo.duty_u16(pulse_us * 65535 // 20000)


def mqtt_callback(tpc, msg):
    global mode
    t = tpc.decode("utf-8") if isinstance(tpc, bytes) else str(tpc)
    v = msg.decode("utf-8") if isinstance(msg, bytes) else str(msg)
    print("[P3 - RECV MQTT]", t, "->", v)
    if t == T_EMERGENCY:
        mode = parse_mode(v)


def update(now):
    """Cập nhật cửa + LED theo mode và nút bấm. Gọi liên tục trong vòng lặp."""
    global local_active, local_t0, door_open, last_btn
    emergency = mode in ("HOT", "SMOKE", "FIRE", "TEST")

    b = btn_door.value()
    if b == 1 and last_btn == 0 and not emergency:
        print("👉 [P3 - NÚT BẤM] Mở cửa thủ công 5 giây")
        local_active = True
        local_t0 = now
    last_btn = b

    if local_active and time.ticks_diff(now, local_t0) >= LOCAL_OPEN_MS:
        local_active = False
        print("⏱️ [P3 - NÚT BẤM] Hết 5s -> đóng cửa")

    want_open = emergency or local_active
    if want_open != door_open:
        door_open = want_open
        set_servo_angle(90 if want_open else 0)
        print("🚪 [P3] {} cửa ra vào (mode={})".format("MỞ" if want_open else "ĐÓNG", mode))

    if mode in ("FIRE", "TEST"):
        led_red.value((now // 300) % 2)
        led_green.value(0)
    elif mode == "SMOKE":
        led_red.value((now // 700) % 2)
        led_green.value(0)
    elif mode == "HOT":                 # nhiệt cao: LED đỏ sáng cố định để cảnh báo
        led_red.value(1)
        led_green.value(0)
    else:
        led_red.value(0)
        led_green.value(1 if local_active else 0)


wlan = network.WLAN(network.STA_IF)


def connect_wifi():
    if wlan.isconnected():
        return
    wlan.active(True)
    print("[P3 - WiFi] Đang kết nối WiFi...")
    wlan.connect(WIFI_SSID, WIFI_PASS)
    t0 = time.ticks_ms()
    while not wlan.isconnected():
        if time.ticks_diff(time.ticks_ms(), t0) > 20000:
            raise OSError("WiFi timeout")
        time.sleep_ms(300)
    print("[P3 - WiFi] Thành công! IP:", wlan.ifconfig()[0])


def main():
    global pub_door
    print("==========================================")
    print("=== PROJECT 3: NODE CỬA RA VÀO (START) ===")
    print("==========================================")
    set_servo_angle(0)
    client = None
    last_ping = time.ticks_ms()
    last_sync = time.ticks_ms()

    while True:
        try:
            connect_wifi()
            if client is None:
                print("[P3 - MQTT] Đang kết nối Adafruit IO...")
                client = MQTTClient("esp32-p3-{}".format(time.ticks_ms()), AIO_SERVER, port=AIO_PORT,
                                    user=AIO_USER, password=AIO_KEY, keepalive=60)
                client.set_callback(mqtt_callback)
                client.connect()
                client.subscribe(T_EMERGENCY)
                client.publish(T_EMERGENCY + "/get", b"")   # lấy trạng thái mới nhất từ cloud
                pub_door = None                              # gửi lại trạng thái cửa
                last_ping = time.ticks_ms()
                last_sync = last_ping
                print("[P3 - MQTT] Đã hoàn thành đăng ký!")

            client.check_msg()
            now = time.ticks_ms()
            update(now)

            #if door_open is not None and door_open != pub_door:
                #client.publish(T_DOOR, "ON" if door_open else "OFF")
                #pub_door = door_open

            if time.ticks_diff(now, last_sync) >= 30000:
                # Xin lại lệnh mới nhất mỗi 30s: nếu lỡ mất một tin (Adafruit giới hạn tốc độ) thì cửa vẫn đúng trạng thái
                client.publish(T_EMERGENCY + "/get", b"")
                last_sync = now
            if time.ticks_diff(now, last_ping) >= 30000:
                client.ping()
                last_ping = now
            time.sleep_ms(20)
        except Exception as e:
            print("[P3 - RECONNECT] Lỗi: {} -> tự kết nối lại sau 2s...".format(e))
            try:
                client.disconnect()
            except Exception:
                pass
            client = None
            time.sleep(2)


if __name__ == "__main__":
    main()