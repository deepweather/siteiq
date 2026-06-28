// SiteIQ reference ESP32 sensor firmware.
//
// An ESP32-class node can do WiFi + MQTT but should NOT hold a SiteIQ device
// token or talk to the cloud directly — it publishes a tiny reading to the
// on-site gateway's MQTT broker on topic `siteiq/sensors/<NODE_ID>`. The
// gateway's mqtt_bridge.py maps it to a ledger event and forwards it to the
// agent. Arduino/AVR + LoRa nodes that can't do WiFi talk serial/LoRa to the
// gateway instead and never run anything like this.
//
// Libraries: WiFi.h (built-in), PubSubClient, ArduinoJson.

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

const char* WIFI_SSID = "site-wifi";
const char* WIFI_PASS = "change-me";
const char* MQTT_HOST = "192.168.1.10";  // the on-site gateway
const int   MQTT_PORT = 1883;            // use 8883 + WiFiClientSecure for TLS
const char* NODE_ID   = "gate-north";

const int SENSOR_PIN = 13;  // e.g. a magnetic contact

WiFiClient net;
PubSubClient mqtt(net);

void ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) { delay(500); }
}

void ensureMqtt() {
  while (!mqtt.connected()) {
    String clientId = String("siteiq-") + NODE_ID;
    if (!mqtt.connect(clientId.c_str())) delay(1000);
  }
}

void publishReading(bool open) {
  StaticJsonDocument<128> doc;
  doc["state"] = open ? "open" : "closed";
  doc["value"] = open ? 1 : 0;
  char buf[128];
  size_t n = serializeJson(doc, buf);
  String topic = String("siteiq/sensors/") + NODE_ID;
  mqtt.publish(topic.c_str(), buf, n);
}

bool lastState = false;

void setup() {
  pinMode(SENSOR_PIN, INPUT_PULLUP);
  ensureWifi();
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
}

void loop() {
  ensureWifi();
  ensureMqtt();
  mqtt.loop();

  bool open = digitalRead(SENSOR_PIN) == HIGH;
  if (open != lastState) {  // publish only on state change (discrete events)
    publishReading(open);
    lastState = open;
  }
  delay(200);
}
