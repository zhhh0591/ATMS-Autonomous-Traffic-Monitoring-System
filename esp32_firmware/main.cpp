#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

#define WIFI_SSID        "UB_Devices"
#define WIFI_PASSWORD    "goubbulls"
#define MQTT_BROKER_IP   "broker.emqx.io" 
#define MQTT_BROKER_PORT 1883
#define MQTT_TOPIC       "traffic/node/cam_node_01/state"

#define PIN_LED_GREEN  21
#define PIN_LED_YELLOW 19
#define PIN_LED_RED    18

WiFiClient   wifiClient;
PubSubClient mqttClient(wifiClient);

void allOff() {
  digitalWrite(PIN_LED_GREEN,  LOW);
  digitalWrite(PIN_LED_YELLOW, LOW);
  digitalWrite(PIN_LED_RED,    LOW);
}

void onMessage(char* topic, byte* payload, unsigned int length) {
  char buf[256];
  memcpy(buf, payload, length);
  buf[length] = '\0';
  Serial.printf("[MQTT] Received: %s\n", buf);

  StaticJsonDocument<256> doc;
  if (deserializeJson(doc, buf)) return;

  const char* state = doc["flow_state"] | "CLEAR";

  allOff();
  if (strcmp(state, "CLEAR") == 0) {
    digitalWrite(PIN_LED_GREEN, HIGH);
  } else if (strcmp(state, "MODERATE") == 0) {
    digitalWrite(PIN_LED_YELLOW, HIGH);
  } else if (strcmp(state, "CONGESTED") == 0) {
    digitalWrite(PIN_LED_RED,    HIGH);
    digitalWrite(PIN_LED_YELLOW, HIGH);
  } else if (strcmp(state, "STOPPED") == 0) {
    digitalWrite(PIN_LED_RED, HIGH);
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_LED_GREEN,  OUTPUT);
  pinMode(PIN_LED_YELLOW, OUTPUT);
  pinMode(PIN_LED_RED,    OUTPUT);
  allOff();

  WiFi.mode(WIFI_STA);
  WiFi.disconnect(true, true);
  delay(2000);
  
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) { delay(500); }
  
  mqttClient.setServer(MQTT_BROKER_IP, MQTT_BROKER_PORT);
  mqttClient.setCallback(onMessage);
}

void loop() {
  if (!mqttClient.connected()) {
    if (mqttClient.connect("esp32_traffic")) {
      mqttClient.subscribe(MQTT_TOPIC);
    } else {
      delay(5000);
    }
  }
  mqttClient.loop();
}