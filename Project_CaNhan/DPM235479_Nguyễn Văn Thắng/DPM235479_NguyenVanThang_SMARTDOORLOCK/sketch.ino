#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <Keypad.h>
#include <Servo.h>
#include <EEPROM.h>

// ---------- Chân (theo Table I) ----------
#define PIN_SERVO       12
#define PIN_BUZZER      13
#define BTN_REG_PIN     A0
#define BTN_REG_FINGER  A1
#define BTN_REG_ADMIN   A2
#define PIN_IR          A3      // FC-51: LOW = có vật cản
#define SIM_FINGER_OK   10      // giả lập vân tay hợp lệ
#define SIM_FINGER_BAD  11      // giả lập vân tay lạ

// ---------- Tham số ----------
const int           MAX_FAILED = 5;
const unsigned long LOCKOUT_MS = 30000UL;
const unsigned long OPEN_MS    = 5000UL;

// ---------- Địa chỉ EEPROM ----------
#define EE_MAGIC   0
#define EE_USERPIN 1    // 9 byte
#define EE_ADMPIN  10   // 9 byte
#define EE_FINGERS 20

LiquidCrystal_I2C lcd(0x27, 16, 2);
Servo servo;

const byte ROWS = 4, COLS = 4;
char keys[ROWS][COLS] = {
  {'1','2','3','A'},
  {'4','5','6','B'},
  {'7','8','9','C'},
  {'*','0','#','D'}
};
byte rowPins[ROWS] = {2, 3, 4, 5};
byte colPins[COLS] = {6, 7, 8, 9};
Keypad keypad = Keypad(makeKeymap(keys), rowPins, colPins, ROWS, COLS);

String userPin, adminPin;
byte fingerCount = 0;
int  failedAttempts = 0;
bool locked = false;
unsigned long lockEnd = 0;
bool physicalEnabled = true;
byte pendingReg = 0;            // 1 = PIN, 2 = Finger (lệnh từ Blynk)

// ---------- EEPROM ----------
void writePin(int addr, const String &p) {
  for (int i = 0; i < 8; i++) EEPROM.update(addr + i, i < (int)p.length() ? p[i] : 0);
  EEPROM.update(addr + 8, 0);
}
String readPin(int addr) {
  String s = "";
  for (int i = 0; i < 8; i++) {
    char c = EEPROM.read(addr + i);
    if (c == 0) break;
    s += c;
  }
  return s;
}

// ---------- Tiện ích ----------
void beep(int ms) { tone(PIN_BUZZER, 1500, ms); }

void logEvent(const char *method, bool ok) {
  Serial.print(F("ESPLOG|"));
  Serial.print(method);
  Serial.print('|');
  Serial.println(ok ? F("Success") : F("Failed"));
}

void showIdle() {
  lcd.clear();
  lcd.print(F("PIN / Finger..."));
  lcd.setCursor(0, 1);
  lcd.print(F("Fail: "));
  lcd.print(failedAttempts);
  lcd.print('/');
  lcd.print(MAX_FAILED);
}

void msg(const char *l1, const char *l2, int waitMs) {
  lcd.clear();
  lcd.print(l1);
  lcd.setCursor(0, 1);
  lcd.print(l2);
  delay(waitMs);
}

void waitRelease(int pin) {
  delay(50);
  while (digitalRead(pin) == LOW) delay(10);
}

// Nhập PIN: # xác nhận, * xóa lùi, D hủy. Trả false nếu hủy/timeout
bool inputPin(const char *title, String &out, char first = 0) {
  out = "";
  unsigned long t = millis();
  lcd.clear();
  lcd.print(title);
  if (first) out += first;
  while (millis() - t < 15000UL) {
    lcd.setCursor(0, 1);
    lcd.print(F("                "));
    lcd.setCursor(0, 1);
    for (unsigned i = 0; i < out.length(); i++) lcd.print('*');

    char k = keypad.getKey();
    if (!k) continue;
    t = millis();
    if (k >= '0' && k <= '9') {
      if (out.length() < 8) out += k;
    } else if (k == '*') {
      if (out.length()) out.remove(out.length() - 1);
    } else if (k == 'D') {
      return false;
    } else if (k == '#') {
      if (out.length() >= 4) return true;
      msg("Min 4 digits", "", 800);
      lcd.clear();
      lcd.print(title);
    }
  }
  return false;
}

// ---------- Mở cửa thông minh ----------
void unlockDoor() {
  lcd.clear();
  lcd.print(F("Access Granted"));
  servo.write(90);
  delay(OPEN_MS);
  while (digitalRead(PIN_IR) == LOW) {          // có vật cản -> giữ cửa
    lcd.setCursor(0, 1);
    lcd.print(F("Waiting clear..."));
    delay(100);
  }
  servo.write(0);
  msg("Door Locked", "", 1000);
}

void handleAuth(const char *method, bool ok) {
  logEvent(method, ok);
  if (ok) {
    failedAttempts = 0;
    unlockDoor();
  } else {
    failedAttempts++;
    lcd.clear();
    lcd.print(F("Access Denied"));
    lcd.setCursor(0, 1);
    lcd.print(F("Fail "));
    lcd.print(failedAttempts);
    lcd.print('/');
    lcd.print(MAX_FAILED);
    beep(300);
    delay(1500);
    if (failedAttempts >= MAX_FAILED) {
      locked = true;
      lockEnd = millis() + LOCKOUT_MS;
    }
  }
  if (!locked) showIdle();
}

// ---------- Đăng ký ----------
bool adminAuth() {
  String p;
  if (!inputPin("Admin PIN:", p)) return false;
  if (p == adminPin) return true;
  msg("Wrong admin PIN", "", 1500);
  beep(300);
  return false;
}

void regPin() {
  String n;
  if (adminAuth() && inputPin("New PIN (4-8):", n)) {
    userPin = n;
    writePin(EE_USERPIN, n);
    logEvent("Reg_PIN", true);
    msg("PIN saved!", "", 1500);
  } else {
    logEvent("Reg_PIN", false);
    msg("Reg PIN failed", "", 1500);
  }
  Serial.println(F("BLYNK_OFF"));
  showIdle();
}

void regFinger() {
  bool ok = false;
  if (adminAuth()) {
    lcd.clear();
    lcd.print(F("Place finger..."));
    lcd.setCursor(0, 1);
    lcd.print(F("(btn Finger OK)"));
    unsigned long t = millis();
    while (millis() - t < 10000UL) {
      if (digitalRead(SIM_FINGER_OK) == LOW) {
        waitRelease(SIM_FINGER_OK);
        if (fingerCount < 10) {
          fingerCount++;
          EEPROM.update(EE_FINGERS, fingerCount);
        }
        ok = true;
        break;
      }
    }
  }
  logEvent("Reg_Finger", ok);
  msg(ok ? "Finger saved!" : "Reg Finger fail", "", 1500);
  Serial.println(F("BLYNK_OFF"));
  showIdle();
}

void changeAdmin() {
  String n;
  bool ok = adminAuth() && inputPin("New Admin PIN:", n);
  if (ok) {
    adminPin = n;
    writePin(EE_ADMPIN, n);
  }
  logEvent("Reg_Admin", ok);
  msg(ok ? "Admin PIN saved" : "Cancelled", "", 1500);
  showIdle();
}

// ---------- Nhận lệnh từ ESP ----------
void handleSerial() {
  static String buf;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      buf.trim();
      if      (buf == "CMD-REG-PIN")    pendingReg = 1;
      else if (buf == "CMD-REG-FINGER") pendingReg = 2;
      else if (buf == "CMD-DISABLE")    physicalEnabled = false;
      else if (buf == "CMD-ENABLE")     physicalEnabled = true;
      buf = "";
    } else if (buf.length() < 32) {
      buf += c;
    }
  }
}

// ---------- setup / loop ----------
void setup() {
  Serial.begin(9600);
  pinMode(BTN_REG_PIN, INPUT_PULLUP);
  pinMode(BTN_REG_FINGER, INPUT_PULLUP);
  pinMode(BTN_REG_ADMIN, INPUT_PULLUP);
  pinMode(PIN_IR, INPUT_PULLUP);
  pinMode(SIM_FINGER_OK, INPUT_PULLUP);
  pinMode(SIM_FINGER_BAD, INPUT_PULLUP);
  pinMode(PIN_BUZZER, OUTPUT);

  lcd.init();
  lcd.backlight();
  servo.attach(PIN_SERVO);
  servo.write(0);

  if (EEPROM.read(EE_MAGIC) != 0xA5) {          // lần chạy đầu
    writePin(EE_USERPIN, "1234");
    writePin(EE_ADMPIN, "0000");
    EEPROM.update(EE_FINGERS, 0);
    EEPROM.update(EE_MAGIC, 0xA5);
  }
  userPin = readPin(EE_USERPIN);
  adminPin = readPin(EE_ADMPIN);
  fingerCount = EEPROM.read(EE_FINGERS);

  showIdle();
}

void loop() {
  handleSerial();

  // --- Đang bị khóa ---
  if (locked) {
    static unsigned long lastBeep = 0;
    if (millis() >= lockEnd) {
      locked = false;
      failedAttempts = 0;
      showIdle();
    } else if (millis() - lastBeep > 1000) {
      lastBeep = millis();
      beep(100);
      lcd.clear();
      lcd.print(F("SYSTEM LOCKED"));
      lcd.setCursor(0, 1);
      lcd.print((lockEnd - millis()) / 1000 + 1);
      lcd.print(F(" s left"));
    }
    return;
  }

  // --- Lệnh đăng ký từ xa (Blynk) ---
  if (pendingReg == 1) { pendingReg = 0; regPin();    return; }
  if (pendingReg == 2) { pendingReg = 0; regFinger(); return; }

  // --- Nút vật lý ---
  if (physicalEnabled) {
    if (digitalRead(BTN_REG_PIN) == LOW)    { waitRelease(BTN_REG_PIN);    regPin();      return; }
    if (digitalRead(BTN_REG_FINGER) == LOW) { waitRelease(BTN_REG_FINGER); regFinger();   return; }
    if (digitalRead(BTN_REG_ADMIN) == LOW)  { waitRelease(BTN_REG_ADMIN);  changeAdmin(); return; }
  }

  // --- Vân tay (giả lập) ---
  if (digitalRead(SIM_FINGER_OK) == LOW) {
    waitRelease(SIM_FINGER_OK);
    if (fingerCount > 0) handleAuth("Fingerprint", true);
    else { msg("No finger saved", "", 1200); handleAuth("Fingerprint", false); }
    return;
  }
  if (digitalRead(SIM_FINGER_BAD) == LOW) {
    waitRelease(SIM_FINGER_BAD);
    handleAuth("Fingerprint", false);
    return;
  }

  // --- Keypad: bấm số bất kỳ để bắt đầu nhập PIN ---
  char k = keypad.getKey();
  if (k >= '0' && k <= '9') {
    String pin;
    if (inputPin("Enter PIN:", pin, k)) handleAuth("Keypad", pin == userPin);
    else showIdle();
  }
}