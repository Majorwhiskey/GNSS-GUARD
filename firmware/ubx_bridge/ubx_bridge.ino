// Configures a u-blox NEO-M8N for UBX binary output and bridges it to USB serial,
// so the PC can log raw .ubx files. Config is RAM-only and re-applied on every boot.
//
// Wiring: GPS TX -> GPIO16, GPS RX -> GPIO17, GND -> GND, VCC -> per your breakout (3V3 or 5V)

const int GPS_RX = 16, GPS_TX = 17;
const uint32_t GPS_BAUD = 460800;
const uint32_t USB_BAUD = 921600;
HardwareSerial& gps = Serial2;

void sendUbx(uint8_t cls, uint8_t id, const uint8_t* payload, uint16_t len) {
  uint8_t hdr[6] = {0xB5, 0x62, cls, id, (uint8_t)(len & 0xFF), (uint8_t)(len >> 8)};
  uint8_t ckA = 0, ckB = 0;
  for (int i = 2; i < 6; i++) { ckA += hdr[i]; ckB += ckA; }
  for (int i = 0; i < len; i++) { ckA += payload[i]; ckB += ckA; }
  gps.write(hdr, 6);
  gps.write(payload, len);
  gps.write(ckA);
  gps.write(ckB);
  gps.flush();
  delay(50);
}

void put32(uint8_t* p, uint32_t v) { for (int i = 0; i < 4; i++) p[i] = v >> (8 * i); }

// UBX-CFG-PRT: UART1, 8N1, UBX+NMEA in, UBX out
void setPort() {
  uint8_t p[20] = {0};
  p[0] = 1;                   // portID = UART1
  put32(p + 4, 0x000008D0);   // mode 8N1
  put32(p + 8, GPS_BAUD);
  p[12] = 0x03;               // inProtoMask: UBX | NMEA
  p[14] = 0x01;               // outProtoMask: UBX only
  sendUbx(0x06, 0x00, p, sizeof(p));
}

void enableMsg(uint8_t cls, uint8_t id, uint8_t rate) {
  uint8_t p[3] = {cls, id, rate};  // rate on the current port
  sendUbx(0x06, 0x01, p, sizeof(p));
}

void setup() {
  Serial.setRxBufferSize(4096);
  Serial.begin(USB_BAUD);

  // The receiver may be at its 9600 default or at a rate left over from earlier, try them all.
  const uint32_t bauds[] = {9600, 38400, 115200, GPS_BAUD};
  for (uint32_t b : bauds) {
    gps.begin(b, SERIAL_8N1, GPS_RX, GPS_TX);
    setPort();
    gps.end();
  }
  gps.setRxBufferSize(8192);
  gps.begin(GPS_BAUD, SERIAL_8N1, GPS_RX, GPS_TX);

  uint8_t rate[6] = {0xE8, 0x03, 0x01, 0x00, 0x01, 0x00};  // 1000 ms meas, 1 cycle, GPS time
  sendUbx(0x06, 0x08, rate, sizeof(rate));

  enableMsg(0x01, 0x07, 1);  // NAV-PVT    position / velocity / accuracy
  enableMsg(0x01, 0x35, 1);  // NAV-SAT    per-satellite C/N0, elevation, residuals
  enableMsg(0x01, 0x03, 1);  // NAV-STATUS includes u-blox spoofDetState (baseline)
  enableMsg(0x01, 0x22, 1);  // NAV-CLOCK  receiver clock bias / drift
  enableMsg(0x0A, 0x09, 1);  // MON-HW     AGC, noise floor, jamInd (baseline)
  enableMsg(0x02, 0x15, 1);  // RXM-RAWX   raw measurements, NAKed if this firmware lacks it
}

void loop() {
  uint8_t buf[512];
  size_t n = gps.available();
  if (n) Serial.write(buf, gps.readBytes(buf, min(n, sizeof(buf))));
  n = Serial.available();  // PC -> GPS passthrough, for extra config commands
  if (n) gps.write(buf, Serial.readBytes(buf, min(n, sizeof(buf))));
}
