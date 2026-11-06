#define BLYNK_TEMPLATE_ID   "TMPL6cSNe-wUm"
#define BLYNK_TEMPLATE_NAME "IoT Smart Door Lock"
#define BLYNK_AUTH_TOKEN    "ceQM2nYXFVlZFctoYoSwZuhI6a4xDD-o"

// Tăng thời gian chờ lên 60 giây để không bị báo Offline khi đang gửi Google Sheets
#define BLYNK_HEARTBEAT 60
#define BLYNK_PRINT Serial

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <BlynkSimpleEsp32.h>

const char *ssid = "Wokwi-GUEST";
const char *pass = "";
const String scriptUrl = "https://script.google.com/macros/s/AKfycbzz3gTcbx-CHXSAm2AWDKNxVvCPb4_LbPuzIfSoWN-aArQmK0suPceMXrzMlZpW1iPABQ/exec";

#define UNO Serial

unsigned long lastReconnectAttempt = 0;

BLYNK_WRITE(V0) { if (param.asInt() == 1) UNO.println("CMD-REG-PIN"); }
BLYNK_WRITE(V1) { if (param.asInt() == 1) UNO.println("CMD-REG-FINGER"); }
BLYNK_WRITE(V2) { UNO.println(param.asInt() == 1 ? "CMD-DISABLE" : "CMD-ENABLE"); }

void sendLog(String method, String result) {
  Serial.printf("-> Dang gui log: Method=%s, Result=%s...\n", method.c_str(), result.c_str());
  
  // Giữ nhịp Blynk trước khi thực hiện tác vụ nặng
  Blynk.run();

  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient http;
  http.setTimeout(8000); // Giới hạn thời gian chờ tối đa 8s
  
  String url = scriptUrl + "?method=" + method + "&result=" + result;
  http.begin(client, url);
  http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
  
  int code = http.GET();
  Serial.printf("[HTTP] Ma phan hoi: %d\n", code);
  http.end();

  // Đồng bộ lại ngay với Blynk sau khi gửi xong
  if (!Blynk.connected()) {
    Blynk.connect(2000);
  }
  Blynk.run();
}

void handleLine(String line) {
  line.trim();
  if (line.length() == 0) return;

  Serial.println("[Da nhan lenh]: " + line);

  if (line.startsWith("ESPLOG|")) {
    int p1 = line.indexOf('|');
    int p2 = line.indexOf('|', p1 + 1);
    if (p2 > 0) {
      sendLog(line.substring(p1 + 1, p2), line.substring(p2 + 1));
    }
  } else if (line == "BLYNK_OFF") {
    if (!Blynk.connected()) Blynk.connect(2000);
    Blynk.virtualWrite(V0, 0);
    Blynk.virtualWrite(V1, 0);
    Blynk.run();
    Serial.println("-> Da tat cong tac V0, V1 tren Blynk ve OFF!");
  }
}

void setup() {
  Serial.begin(115200);
  UNO.setTimeout(50);
  
  Serial.print("Dang ket noi WiFi");
  WiFi.begin(ssid, pass, 6);
  while (WiFi.status() != WL_CONNECTED) {
    delay(200);
    Serial.print(".");
  }
  Serial.println("\nDa ket noi WiFi! Dang ket noi Blynk...");

  Blynk.config(BLYNK_AUTH_TOKEN, "sgp1.blynk.cloud", 80);
  Blynk.connect(3000);
}

void loop() {
  // Nếu chẳng may mất kết nối thì cứ 5 giây tự kết nối lại nhẹ nhàng (không làm treo máy)
  if (!Blynk.connected()) {
    if (millis() - lastReconnectAttempt > 5000) {
      lastReconnectAttempt = millis();
      Serial.println("Dang khoi phuc ket noi Blynk...");
      if (WiFi.status() != WL_CONNECTED) {
        WiFi.begin(ssid, pass, 6);
      } else {
        Blynk.connect(1500);
      }
    }
  } else {
    Blynk.run();
  }

  if (UNO.available()) {
    String line = UNO.readStringUntil('\n');
    handleLine(line);
  }
}