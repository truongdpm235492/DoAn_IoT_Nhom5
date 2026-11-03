import gc
import json
import time
import network
import ssd1306
from machine import Pin, I2C, PWM
from umqtt.simple import MQTTClient
try:
    import urequests as requests
except ImportError:
    import requests
from config import (WIFI_SSID, WIFI_PASS, AIO_SERVER, AIO_PORT, AIO_USER, AIO_KEY, GROUP,
                    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)

# ============ PROJECT 4: CONTROL ROOM (BỘ NÃO QUYẾT ĐỊNH) ============
# Đọc temp/smoke từ Adafruit, quyết định kịch bản, ghi vào emergency_status cho P2/P3.
#   SAFE  : khói & nhiệt thường                 -> tất cả tắt
#   HOT   : chỉ nhiệt vượt ngưỡng, khói thường  -> quạt + cửa gió (làm mát, không còi/bơm) + Telegram "nhiệt độ cao"
#   SMOKE : chỉ khói vượt ngưỡng               -> quạt + cửa gió + cửa ra vào + còi (bơm tắt) + Telegram "khói bất thường"
#   FIRE  : khói VÀ nhiệt cùng vượt ngưỡng      -> bật tất cả + Telegram "hỏa hoạn"
#   TEST  : công tắc test (GPIO19) hoặc nút web -> bật tất cả + Telegram "test" (không phải cháy thật)
#   manual-vent : công tắc cửa thông gió (GPIO18) hoặc nút web -> CHỈ cửa thông gió


def topic(name):
    return "{}/f/{}.{}".format(AIO_USER, GROUP, name)


T_TEMP = topic("temp")
T_SMOKE = topic("smoke")
T_EMERGENCY = topic("emergency_status")
T_MANUAL = topic("manual-vent")
T_VENT_CMD = topic("vent-cmd")    # lệnh từ dashboard web
T_TEST_CMD = topic("test-cmd")    # lệnh từ dashboard web

TEMP_ALERT = 45.0
TEMP_CLEAR = 43.0
SMOKE_ALERT = 60.0
SMOKE_CLEAR = 50.0

i2c = I2C(0, scl=Pin(22), sda=Pin(21))
oled = ssd1306.SSD1306_I2C(128, 64, i2c)
buzzer = PWM(Pin(25), freq=2000, duty_u16=0)

switch_test = Pin(19, Pin.IN, Pin.PULL_UP)   # kéo xuống GND = bật test
btn_vent = Pin(18, Pin.IN, Pin.PULL_UP)      # kéo xuống GND = mở cửa thông gió

curr_temp = 0.0
curr_smoke = 0.0
temp_high = False
smoke_high = False
vent_cmd = False
test_cmd = False
status = "SAFE"
manual_vent = False
pub_status = None
pub_manual = None
prev_msg_status = "SAFE"
pending_msg = None
cloud_ok = False
buz_on = False
wlan = network.WLAN(network.STA_IF)


def send_telegram(text):
    """Gửi đồng bộ (không dùng thread: TLS trong thread dễ tràn stack trên ESP32)."""
    if (not TELEGRAM_TOKEN) or ("DAN_" in TELEGRAM_TOKEN):
        print("[P4 - TELEGRAM] Chưa cấu hình token -> bỏ qua")
        return
    res = None
    try:
        gc.collect()
        print("[P4 - TELEGRAM] Đang gửi:", text)
        url = "https://api.telegram.org/bot{}/sendMessage".format(TELEGRAM_TOKEN)
        # Phải encode ra bytes: Content-Length tính theo byte, nếu truyền str có dấu tiếng Việt
        # thì độ dài bị sai -> Telegram trả HTTP 400.
        body = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": text}).encode("utf-8")
        res = requests.post(url, data=body, headers={"Content-Type": "application/json"})
        print("[P4 - TELEGRAM] HTTP", res.status_code)
    except Exception as e:
        print("[P4 - TELEGRAM] Lỗi:", e)
    finally:
        if res is not None:
            try:
                res.close()
            except Exception:
                pass


def build_message(st):
    t = "{:.1f}".format(curr_temp)
    s = "{:.1f}".format(curr_smoke)
    if st == "SMOKE":
        return ("⚠️ KHÓI NHIỀU BẤT THƯỜNG tại xưởng!\nKhói: {}% | Nhiệt độ: {}°C (vẫn bình thường).\n"
                "Đã bật quạt hút, cửa thông gió, cửa ra vào và còi.").format(s, t)
    if st == "FIRE":
        return ("🔥🚨 CẢNH BÁO HỎA HOẠN tại xưởng!\nKhói: {}% và nhiệt độ: {}°C đều vượt ngưỡng.\n"
                "Đã kích hoạt toàn bộ: quạt, cửa thông gió, cửa ra vào, còi và bơm nước.").format(s, t)
    if st == "HOT":
        return ("🌡️ NHIỆT ĐỘ CAO BẤT THƯỜNG tại xưởng!\nNhiệt độ: {}°C (vượt ngưỡng {:.0f}°C), khói: {}% vẫn bình thường.\n"
                "Đã bật quạt hút và cửa thông gió để làm mát.").format(t, TEMP_ALERT, s)
    if st == "TEST":
        return "🧪 [TEST] Đang kiểm tra hệ thống cảnh báo (bật tất cả thiết bị). Đây KHÔNG phải hỏa hoạn thật."
    return "✅ AN TOÀN: các thông số đã trở lại bình thường.\nKhói: {}% | Nhiệt độ: {}°C".format(s, t)


def hyst(state, value, alert, clear):
    if value >= alert:
        return True
    if value < clear:
        return False
    return state


def decide(temp_hi, smoke_hi, test_on):
    if test_on:
        return "TEST"
    if temp_hi and smoke_hi:
        return "FIRE"
    if smoke_hi:
        return "SMOKE"
    if temp_hi:
        return "HOT"
    return "SAFE"


def process_logic(client):
    global temp_high, smoke_high, status, manual_vent
    global pub_status, pub_manual, prev_msg_status, pending_msg

    test_on = (switch_test.value() == 0) or test_cmd
    manual_vent = (btn_vent.value() == 0) or vent_cmd
    temp_high = hyst(temp_high, curr_temp, TEMP_ALERT, TEMP_CLEAR)
    smoke_high = hyst(smoke_high, curr_smoke, SMOKE_ALERT, SMOKE_CLEAR)
    status = decide(temp_high, smoke_high, test_on)

    # Gửi lệnh trước (khẩn cấp), Telegram sau
    if status != pub_status:
        print("[P4 - LOGIC] Trạng thái ->", status)
        client.publish(T_EMERGENCY, status)
        pub_status = status
    if manual_vent != pub_manual:
        print("[P4 - LOGIC] Mở cửa thông gió thủ công ->", manual_vent)
        client.publish(T_MANUAL, "ON" if manual_vent else "OFF")
        pub_manual = manual_vent

    if status != prev_msg_status:
        pending_msg = build_message(status)
        prev_msg_status = status


def update_buzzer(now):
    global buz_on
    if status in ("FIRE", "TEST"):
        on = (now % 400) < 200       # cháy/test: bíp nhanh
    elif status == "SMOKE":
        on = (now % 1000) < 200      # khói: bíp chậm
    else:
        on = False
    if on != buz_on:
        buz_on = on
        buzzer.duty_u16(32768 if on else 0)


def update_oled():
    oled.fill(0)
    oled.text("CONTROL ROOM", 16, 0)
    oled.text("Temp : {:.1f} C".format(curr_temp), 0, 14)
    oled.text("Smoke: {:.1f} %".format(curr_smoke), 0, 26)
    label = {"SAFE": "SAFE  OK", "HOT": "HOT !!", "SMOKE": "SMOKE !!", "FIRE": "FIRE !!!", "TEST": "TEST"}[status]
    if status == "SAFE" and manual_vent:
        label = "VENT ON"
    oled.text("STATUS: " + label, 0, 40)
    oled.text("Cloud: " + ("OK" if cloud_ok else "LOST"), 0, 54)
    oled.show()


def mqtt_callback(tpc, msg):
    global curr_temp, curr_smoke, vent_cmd, test_cmd
    t = tpc.decode("utf-8")
    m = msg.decode("utf-8").strip()
    if t == T_VENT_CMD:
        vent_cmd = m.upper() in ("ON", "1", "TRUE")
        return
    if t == T_TEST_CMD:
        test_cmd = m.upper() in ("ON", "1", "TRUE")
        return
    try:
        val = float(m)
    except ValueError:
        return
    if t == T_TEMP:
        curr_temp = val
    elif t == T_SMOKE:
        curr_smoke = val


def connect_wifi():
    if wlan.isconnected():
        return
    wlan.active(True)
    print("[P4 - WiFi] Đang kết nối...")
    wlan.connect(WIFI_SSID, WIFI_PASS)
    t0 = time.ticks_ms()
    while not wlan.isconnected():
        if time.ticks_diff(time.ticks_ms(), t0) > 20000:
            raise OSError("WiFi timeout")
        time.sleep_ms(300)
    print("[P4 - WiFi] Đã kết nối, IP:", wlan.ifconfig()[0])


def connect_mqtt():
    global vent_cmd, test_cmd, pub_status, pub_manual
    client = MQTTClient("esp32-node4-{}".format(time.ticks_ms()), AIO_SERVER, port=AIO_PORT,
                        user=AIO_USER, password=AIO_KEY, keepalive=60)
    client.set_callback(mqtt_callback)
    client.connect()
    for t in (T_TEMP, T_SMOKE, T_VENT_CMD, T_TEST_CMD):
        client.subscribe(t)
    vent_cmd = False
    test_cmd = False
    client.publish(T_VENT_CMD, "OFF")           # đặt lại lệnh web
    client.publish(T_TEST_CMD, "OFF")
    client.publish(T_TEMP + "/get", b"")        # lấy ngay giá trị mới nhất của cảm biến
    client.publish(T_SMOKE + "/get", b"")
    pub_status = None                           # gửi lại trạng thái sau khi nối lại
    pub_manual = None
    return client


def main():
    global cloud_ok, pending_msg
    print("=== PROJECT 4: CONTROL ROOM NODE (START) ===")
    client = None
    last_ping = time.ticks_ms()
    last_oled = 0
    update_oled()
    while True:
        try:
            connect_wifi()
            if client is None:
                client = connect_mqtt()
                cloud_ok = True
                last_ping = time.ticks_ms()
                print("[P4 - MQTT] Đã kết nối Adafruit IO")

            client.check_msg()
            now = time.ticks_ms()
            process_logic(client)
            update_buzzer(now)

            if time.ticks_diff(now, last_oled) >= 500:
                update_oled()
                last_oled = now

            if pending_msg:
                msg = pending_msg
                pending_msg = None
                send_telegram(msg)

            if time.ticks_diff(now, last_ping) >= 30000:
                client.ping()
                last_ping = now
            time.sleep_ms(10)
        except Exception as e:
            print("[P4 - ERROR] {} -> tự kết nối lại sau 2s...".format(e))
            cloud_ok = False
            try:
                client.disconnect()
            except Exception:
                pass
            client = None
            time.sleep(2)


if __name__ == "__main__":
    main()