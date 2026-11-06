import time
import network
import urequests
from machine import Pin, PWM, SoftI2C
from i2c_lcd import I2cLcd

print("==========================================")
print("KHOI DONG SMART DOOR LOCK")
print("==========================================")

# ==============================
# 1. CAU HINH WIFI & THINGSPEAK
# ==============================
WIFI_SSID = "Wokwi-GUEST"
WIFI_PASS = ""
THINGSPEAK_API_KEY = "24XESH4SN7P1YRBU"

# ==============================
# 2. CAU HINH PHAN CUNG
# ==============================
PIN_CODE = "1234"

SERVO_PIN = 13
BUZZER_PIN = 27

ROW_PINS = [19, 18, 5, 17]
COL_PINS = [16, 4, 2, 15]

KEY_MAP = [
    ['1', '2', '3', 'A'],
    ['4', '5', '6', 'B'],
    ['7', '8', '9', 'C'],
    ['*', '0', '#', 'D']
]

# ==============================
# 3. KHOI TAO THIET BI
# ==============================
print("-> Khoi tao Keypad...")

rows = [Pin(p, Pin.OUT, value=1) for p in ROW_PINS]
cols = [Pin(p, Pin.IN, Pin.PULL_UP) for p in COL_PINS]

buzzer = PWM(Pin(BUZZER_PIN), freq=2000) # Đặt tần số âm thanh 2kHz
buzzer.duty(0) # Ban đầu tắt âm thanh (duty = 0)
servo_pwm = PWM(Pin(SERVO_PIN), freq=50)

print("-> Khoi tao I2C va LCD...")

i2c = SoftI2C(
    scl=Pin(22),
    sda=Pin(21),
    freq=100000
)

lcd_addr = 0x27
print("-> Su dung dia chi LCD co dinh:", hex(lcd_addr))

try:
    lcd = I2cLcd(i2c, lcd_addr, 2, 16)
    lcd.backlight()
    lcd.clear()
    lcd.move_to(0, 0)
    lcd.putstr("SMART DOOR LOCK")
    lcd.move_to(0, 1)
    lcd.putstr("SYSTEM INIT...")
    print("-> LCD khoi tao thanh cong")
except Exception as e:
    print("-> Loi khoi tao LCD:", e)

# ==============================
# 4. DIEU KHIEN SERVO
# ==============================
def set_servo_angle(angle):
    angle = max(0, min(180, angle))
    duty_ns = int(500000 + (angle / 180.0) * 1900000)
    servo_pwm.duty_ns(duty_ns)
    print("-> Servo:", angle, "do")

# ==============================
# 5. DIEU KHIEN BUZZER
# ==============================
def beep(duration=0.1):
    buzzer.duty(512) # Bật âm thanh (50% duty cycle)
    time.sleep(duration)
    buzzer.duty(0)   # Tắt âm thanh
# ==============================
# 6. KET NOI WIFI
# ==============================
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if not wlan.isconnected():
        print("-> Dang ket noi Wi-Fi...")
        lcd.clear()
        lcd.move_to(0, 0)
        lcd.putstr("CONNECTING WIFI")

        try:
            wlan.connect(WIFI_SSID, WIFI_PASS)
            for _ in range(20):
                if wlan.isconnected():
                    break
                time.sleep(0.5)
        except Exception as e:
            print("-> Loi Wi-Fi:", e)

    if wlan.isconnected():
        print("-> Wi-Fi OK:", wlan.ifconfig()[0])
        lcd.clear()
        lcd.move_to(0, 0)
        lcd.putstr("WIFI CONNECTED")
    else:
        print("-> Wi-Fi that bai, chay Offline")
        lcd.clear()
        lcd.move_to(0, 0)
        lcd.putstr("OFFLINE MODE")

    time.sleep(1)

# ==============================
# 7. GUI DU LIEU THINGSPEAK
# ==============================
def send_thingspeak(door_status, alert_status, wrong_count):
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
        print("-> Bo qua ThingSpeak: chua co Wi-Fi")
        return

    url = (
        "http://api.thingspeak.com/update"
        "?api_key=" + THINGSPEAK_API_KEY
        + "&field1=" + str(door_status)
        + "&field2=" + str(alert_status)
        + "&field3=" + str(wrong_count)
    )

    response = None
    try:
        response = urequests.get(url)
        result = response.text.strip()
        if result == "0":
            print("-> ThingSpeak chua nhan du lieu")
        else:
            print("-> ThingSpeak da cap nhat:", result)
    except Exception as e:
        print("-> Loi ThingSpeak:", e)
    finally:
        if response is not None:
            response.close()
# ==============================
# 7.1. GUI THONG BAO TELEGRAM (Da sua loi 400)
# ==============================
def send_telegram_alert(message):
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
        print("-> Bo qua Telegram: chua co Wi-Fi")
        return

    TELEGRAM_BOT_TOKEN = "8945702797:AAHw8XdGGjrItLIGrk_Me6DX77rmZI3SayI"
    TELEGRAM_CHAT_ID = "8639112484"  # Dãy số ID lấy từ @userinfobot

    # Mã hóa khoảng trắng trong thông báo thành %20 để tránh lỗi URL
    message_encoded = message.replace(" ", "%20")

    url = (
        "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN
        + "/sendMessage?chat_id=" + TELEGRAM_CHAT_ID
        + "&text=" + message_encoded
    )

    response = None
    try:
        response = urequests.get(url)
        print("-> Phan hoi tu Telegram:", response.text)
    except Exception as e:
        print("-> Loi gui Telegram chi tiet:", e)
    finally:
        if response is not None:
            response.close()
# ==============================
# 8. DOC BAN PHIM 4x4 (Sua lai chuan)
# ==============================
def scan_keypad():
    for r_idx, row in enumerate(rows):
        row.value(0)  # Kéo hàng xuống mức thấp (Active Low)
        for c_idx, col in enumerate(cols):
            if col.value() == 0:  # Đọc được mức thấp nghĩa là phím được nhấn
                key = KEY_MAP[r_idx][c_idx]
                # Chờ nhả phím
                while col.value() == 0:
                    time.sleep_ms(10)
                row.value(1)
                print("-> Phim duoc nhan:", key)
                return key
        row.value(1)
    return None
# ==============================
# 9. HIEN THI MAN HINH CHO NHAP PIN
# ==============================
def show_home():
    lcd.clear()
    lcd.move_to(0, 0)
    lcd.putstr("SMART DOOR LOCK")
    lcd.move_to(0, 1)
    lcd.putstr("PIN: ")

# ==============================
# 10. CHUONG TRINH CHINH
# ==============================
set_servo_angle(0)
buzzer.duty(0)

connect_wifi()

input_code = ""
failed_attempts = 0

show_home()

print("==========================================")
print("HE THONG SAN SANG")
print("PIN mac dinh: 1234")
print("Nhap PIN, sau do nhan #")
print("Nhan * de xoa PIN")
print("Nhan A de doi PIN")
print("==========================================")

while True:
    key = scan_keypad()

    if key is not None:
        beep(0.05)

        if key == '*':
            input_code = ""
            show_home()
            print("-> Da xoa PIN")
        # --------------------------
        # DOI MAT KHAU (Phim 'A')
        # --------------------------
        elif key == 'A':
            lcd.clear()
            lcd.move_to(0, 0)
            lcd.putstr("CHANGE PIN MODE")
            lcd.move_to(0, 1)
            lcd.putstr("Old PIN: ")
            
            old_pin = ""
            # Vòng lặp nhỏ để nhập mã PIN cũ
            while True:
                k = scan_keypad()
                if k is not None:
                    beep(0.05)
                    if k == '*':
                        old_pin = ""
                        lcd.move_to(9, 1)
                        lcd.putstr("    ")
                        lcd.move_to(9, 1)
                    elif k == '#':
                        break
                    elif k.isdigit() and len(old_pin) < 4:
                        old_pin += k
                        lcd.putstr("*")
                time.sleep_ms(20)

            # Kiểm tra mật khẩu cũ
            if old_pin == PIN_CODE:
                lcd.clear()
                lcd.move_to(0, 0)
                lcd.putstr("Enter New PIN:")
                lcd.move_to(0, 1)
                lcd.putstr("PIN: ")
                
                new_pin = ""
                # Vòng lặp nhỏ để nhập mã PIN mới
                while True:
                    k = scan_keypad()
                    if k is not None:
                        beep(0.05)
                        if k == '*':
                            new_pin = ""
                            lcd.move_to(5, 1)
                            lcd.putstr("    ")
                            lcd.move_to(5, 1)
                        elif k == '#':
                            if len(new_pin) == 4:
                                break
                            else:
                                lcd.clear()
                                lcd.putstr("Must be 4 digits")
                                time.sleep(1.5)
                                lcd.clear()
                                lcd.putstr("Enter New PIN:")
                                lcd.move_to(0, 1)
                                lcd.putstr("PIN: ")
                                new_pin = ""
                        elif k.isdigit() and len(new_pin) < 4:
                            new_pin += k
                            lcd.putstr("*")
                    time.sleep_ms(20)
                
                # Cập nhật mật khẩu mới
                PIN_CODE = new_pin
                print("-> Da doi PIN thanh cong:", PIN_CODE)
                
                lcd.clear()
                lcd.move_to(0, 0)
                lcd.putstr("PIN CHANGED!")
                lcd.move_to(0, 1)
                lcd.putstr("SUCCESSFUL")
                
                beep(0.1)
                time.sleep(0.1)
                beep(0.1)
                time.sleep(2)
            else:
                print("-> Sai PIN cu, huy doi PIN")
                lcd.clear()
                lcd.move_to(0, 0)
                lcd.putstr("INCORRECT OLD PIN")
                beep(0.4)
                time.sleep(1.5)
            
            # Trở về màn hình chính
            input_code = ""
            show_home()
        elif key == '#':
            if len(input_code) == 0:
                print("-> Vui long nhap PIN")
                show_home()
                continue

            if input_code == PIN_CODE:
                failed_attempts = 0
                lcd.clear()
                lcd.move_to(0, 0)
                lcd.putstr("ACCESS GRANTED!")
                lcd.move_to(0, 1)
                lcd.putstr("DOOR UNLOCKED")

                print("-> PIN DUNG: MO CUA 5 GIAY")
                set_servo_angle(90)
                send_thingspeak(door_status=1, alert_status=0, wrong_count=0)

                beep(0.1)
                time.sleep(0.1)
                beep(0.1)
                time.sleep(5)

                set_servo_angle(0)
                send_thingspeak(door_status=0, alert_status=0, wrong_count=0)

                input_code = ""
                show_home()

            else:
                failed_attempts += 1
                print("-> PIN SAI:", failed_attempts, "/3")
                send_telegram_alert("Canh bao: Nhap sai ma PIN lan " + str(failed_attempts) + "/3!")
                lcd.clear()
                lcd.move_to(0, 0)
                lcd.putstr("ACCESS DENIED!")
                lcd.move_to(0, 1)
                lcd.putstr("WRONG PIN " + str(failed_attempts) + "/3")

                beep(0.4)
                time.sleep(1.5)

                if failed_attempts >= 3:
                    print("-> CANH BAO: SAI PIN 3 LAN")
                    lcd.clear()
                    lcd.move_to(0, 0)
                    lcd.putstr("SYSTEM LOCKED!")
                    lcd.move_to(0, 1)
                    lcd.putstr("ALERT SENT!")
                    # Gửi cảnh báo khẩn cấp qua Telegram
                    send_telegram_alert("KHAN CAP: He thong da bi khoa do nhap sai PIN 3 lan lien tiep!")
                    send_thingspeak(door_status=0, alert_status=1, wrong_count=failed_attempts)

                    for _ in range(15):
                        beep(0.3)
                        time.sleep(0.2)

                    time.sleep(5)
                    failed_attempts = 0

                input_code = ""
                show_home()

        elif key.isdigit():
            if len(input_code) < 4:
                input_code += key
                lcd.move_to(5 + len(input_code) - 1, 1)
                lcd.putstr("*")
                print("-> So ky tu PIN:", len(input_code))

        else:
            print("-> Phim chuc nang khong duoc ho tro")

    time.sleep_ms(20)