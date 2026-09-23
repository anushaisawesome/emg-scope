// EMG software scope — ESP32 internal ADC version (no MCP3208 needed)
// Reads GPIO34 at SAMPLE_RATE, streams the same 2-byte format plot.py expects.
//
// Wiring: signal → GPIO34 (input-only pin, top row on most dev boards).
// That's it. Grounds already shared via the rails.
//
// Sanity check: row X (the 1.1V divider) → GPIO34 = flat line at ~1.1V.
// Finger on GPIO34's row = 50Hz hum.

const int PIN_ADC = 34;
const uint32_t SAMPLE_RATE = 4000;  // Hz — plenty for EMG band
uint32_t samplePeriodUs;
uint32_t nextSampleUs;

void setup() {
  Serial.begin(115200);  // CH340 clones corrupt data at 921600 on macOS
  analogReadResolution(12);                       // 0..4095
  analogSetPinAttenuation(PIN_ADC, ADC_11db);     // full ~0-3.3V range
  samplePeriodUs = 1000000UL / SAMPLE_RATE;
  nextSampleUs = micros();
}

void loop() {
  uint32_t now = micros();
  if ((int32_t)(now - nextSampleUs) >= 0) {
    nextSampleUs += samplePeriodUs;
    uint16_t s = analogRead(PIN_ADC);
    uint8_t buf[2] = { (uint8_t)(0xF0 | (s >> 8)), (uint8_t)(s & 0xFF) };
    Serial.write(buf, 2);
  }
}
