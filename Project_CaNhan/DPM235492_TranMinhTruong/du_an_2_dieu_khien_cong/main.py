
# DU AN 2 - NUT QUET THE GIA LAP VA DIEU KHIEN BARIE
# ESP32 + 2 nut nhan + 2 servo + 2 LED
# MQTT Adafruit IO

import time
import network
from machine import Pin, PWM
from umqtt.simple import MQTTClient

# =========================
# 1. CAU HINH WIFI
# =========================
WIFI_SSID = "Wokwi-GUEST"
WIFI_PASS = ""

# =========================
# 2. CAU HINH ADAFRUIT IO
# =========================
AIO_HOST = "io.adafruit.com"
AIO_PORT = 1883

AIO_USER = "trgtran"
AIO_KEY = "aio_jRge90vZu2oNPw8vlMOceF3NvXi1"

FEED_CHO = AIO_USER + "/feeds/bai-do-xe"
FEED_VAO = AIO_USER + "/feeds/cong-vao"
FEED_RA = AIO_USER + "/feeds/cong-ra"

# =========================
# 3. KHAI BAO CHAN
# =========================
nut_vao = Pin(25, Pin.IN, Pin.PULL_UP)
nut_ra = Pin(26, Pin.IN, Pin.PULL_UP)

LED_XANH = Pin(2, Pin.OUT)
LED_DO = Pin(4, Pin.OUT)

servo_vao = PWM(Pin(18), freq=50)
servo_ra = PWM(Pin(19), freq=50)

# =========================
# 4. THONG SO BARIE
# =========================
A_DONG = 40
A_MO = 115
THOI_GIAN_MO_MS = 4000

client = None
cho_trong = None

servo_vao_dong_luc = 0
servo_ra_dong_luc = 0

vao_cu = 1
ra_cu = 1
vao_debounce = 0
ra_debounce = 0

# =========================
# 5. DIEU KHIEN SERVO
# =========================
def dat_goc(servo, goc):
    duty = int(25 + (goc / 180) * 100)
    servo.duty(duty)

def dong_vao():
    global servo_vao_dong_luc
    dat_goc(servo_vao, A_DONG)
    servo_vao_dong_luc = 0

def dong_ra():
    global servo_ra_dong_luc
    dat_goc(servo_ra, A_DONG)
    servo_ra_dong_luc = 0

# =========================
# 6. CAP NHAT LED
# =========================
def cap_nhat_led():
    if cho_trong is None:
        LED_XANH.value(0)
        LED_DO.value(0)
    elif cho_trong > 0:
        LED_XANH.value(1)
        LED_DO.value(0)
    else:
        LED_XANH.value(0)
        LED_DO.value(1)

# =========================
# 7. NHAN DU LIEU MQTT
# =========================
def khi_co_tin(topic, msg):
    global cho_trong

    payload = msg.decode().strip()

    if payload.startswith("CHO:"):
        bits = payload[4:]

        if len(bits) == 4 and all(c in "01" for c in bits):
            cho_trong = bits.count("0")

            print(
                "Cam bien:", bits,
                "| So cho trong:", cho_trong
            )

            cap_nhat_led()

# =========================
# 8. KET NOI WIFI
# =========================
def wifi_connect():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        print("WiFi da ket noi:", wlan.ifconfig()[0])
        return True

    try:
        wlan.connect(WIFI_SSID, WIFI_PASS)

        for _ in range(40):
            if wlan.isconnected():
                print("WiFi OK:", wlan.ifconfig()[0])
                return True

            time.sleep_ms(500)

    except Exception as e:
        print("Loi WiFi:", repr(e))

    print("Khong ket noi duoc WiFi")
    return False

# =========================
# 9. KET NOI MQTT
# =========================
def connect_mqtt():
    global client

    for lan in range(3):
        c = None

        try:
            cid = "esp32_barie_%d" % time.ticks_ms()

            c = MQTTClient(
                cid,
                AIO_HOST,
                port=AIO_PORT,
                user=AIO_USER,
                password=AIO_KEY,
                keepalive=60
            )

            c.set_callback(khi_co_tin)
            c.connect()
            c.subscribe(FEED_CHO)

            client = c

            print("MQTT ket noi thanh cong")
            print("Dang nghe feed:", FEED_CHO)

            return True

        except Exception as e:
            print("MQTT loi:", repr(e))

            try:
                if c is not None:
                    c.disconnect()
            except Exception:
                pass

            time.sleep(10)

    client = None
    print("Khong ket noi duoc MQTT")
    return False

# =========================
# 10. GUI SU KIEN LEN WEB
# =========================
def su_kien_mqtt(feed, payload):
    global client

    if client is None:
        print("Chua co ket noi MQTT, khong gui duoc su kien")
        return

    try:
        client.publish(feed, payload)
        print("Da gui:", feed, payload)

    except Exception as e:
        print("Loi gui MQTT:", repr(e))

# =========================
# 11. MO CONG VAO
# =========================
def mo_cong_vao():
    global servo_vao_dong_luc

    if cho_trong is None:
        print("TU CHOI: chua nhan duoc du lieu cam bien")
        return

    if cho_trong <= 0:
        print("TU CHOI: bai xe da day")
        return

    dat_goc(servo_vao, A_MO)

    servo_vao_dong_luc = time.ticks_add(
        time.ticks_ms(),
        THOI_GIAN_MO_MS
    )

    event_id = time.ticks_ms()

    su_kien_mqtt(
        FEED_VAO,
        "VAO:MO:%d" % event_id
    )

    print("Mo cong vao thanh cong")

# =========================
# 12. MO CONG RA
# =========================
def mo_cong_ra():
    global servo_ra_dong_luc

    dat_goc(servo_ra, A_MO)

    servo_ra_dong_luc = time.ticks_add(
        time.ticks_ms(),
        THOI_GIAN_MO_MS
    )

    event_id = time.ticks_ms()

    su_kien_mqtt(
        FEED_RA,
        "RA:MO:%d" % event_id
    )

    print("Mo cong ra thanh cong")

# =========================
# 13. KHOI DONG HE THONG
# =========================
LED_XANH.value(0)
LED_DO.value(0)

dong_vao()
dong_ra()

if not wifi_connect():
    raise RuntimeError("Khong ket noi duoc WiFi")

if not connect_mqtt():
    raise RuntimeError(
        "MQTT that bai. Kiem tra AIO_USER va AIO_KEY"
    )

cap_nhat_led()

# =========================
# 14. VONG LAP CHINH
# =========================
while True:
    try:
        # Xu ly tin nhan MQTT
        client.check_msg()

        now = time.ticks_ms()

        # Doc nut nhan
        vao_moi = nut_vao.value()
        ra_moi = nut_ra.value()

        # Nut vao: phat hien canh nhan
        if (
            vao_cu == 1
            and vao_moi == 0
            and time.ticks_diff(now, vao_debounce) > 250
        ):
            vao_debounce = now
            mo_cong_vao()

        # Nut ra: phat hien canh nhan
        if (
            ra_cu == 1
            and ra_moi == 0
            and time.ticks_diff(now, ra_debounce) > 250
        ):
            ra_debounce = now
            mo_cong_ra()

        vao_cu = vao_moi
        ra_cu = ra_moi

        # Tu dong dong cong vao sau 4 giay
        if (
            servo_vao_dong_luc
            and time.ticks_diff(now, servo_vao_dong_luc) >= 0
        ):
            dong_vao()
            print("Cong vao da dong")

        # Tu dong dong cong ra sau 4 giay
        if (
            servo_ra_dong_luc
            and time.ticks_diff(now, servo_ra_dong_luc) >= 0
        ):
            dong_ra()
            print("Cong ra da dong")

        time.sleep_ms(30)

    except Exception as e:
        print("Loi vong lap:", repr(e))

        try:
            if client is not None:
                client.disconnect()
        except Exception:
            pass

        client = None
        time.sleep(5)

        if wifi_connect():
            connect_mqtt()
            cap_nhat_led()
