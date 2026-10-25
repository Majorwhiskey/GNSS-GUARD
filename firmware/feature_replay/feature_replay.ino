// Replays UBX bytes sent from the PC over USB through the feature library and prints one
// CSV row per epoch, so tools/device_parity.py can compare the ESP32's output with
// tools/features.py on the same log. A bench tool, not field firmware.
//
// Build: arduino-cli compile --fqbn esp32:esp32:esp32 --library firmware/lib/gnss_features firmware/feature_replay

#include <gnss_features.h>

const uint32_t USB_BAUD = 921600;
const uint32_t IDLE_MS = 500;  // no bytes for this long: the replay is over

static gnss::UbxParser parser;
static gnss::FeatureExtractor fx;
static uint32_t lastByte = 0;
static bool replaying = false;

void printRow(const gnss::FeatureRow& r) {
  char num[32];
  for (int i = 0; i < gnss::kNumColumns; i++) {
    if (i) Serial.print(',');
    double v = gnss::column(r, i);
    if (!isnan(v)) {
      snprintf(num, sizeof(num), "%.17g", v);
      Serial.print(num);
    }
  }
  Serial.print('\n');
}

void setup() {
  Serial.setRxBufferSize(16384);
  Serial.begin(USB_BAUD);
}

void loop() {
  while (Serial.available()) {
    if (!replaying) {
      for (int i = 0; i < gnss::kNumColumns; i++) {
        if (i) Serial.print(',');
        Serial.print(gnss::kColumns[i].name);
      }
      Serial.print('\n');
      replaying = true;
    }
    lastByte = millis();
    if (parser.feed(Serial.read()) && fx.onMessage(parser.cls(), parser.id(), parser.payload(), parser.length()))
      printRow(fx.row());
  }
  if (replaying && millis() - lastByte > IDLE_MS) {
    if (fx.flush()) printRow(fx.row());
    Serial.print("END\n");
    // Fresh state for the next replay.
    parser = gnss::UbxParser();
    fx = gnss::FeatureExtractor();
    replaying = false;
  }
}
