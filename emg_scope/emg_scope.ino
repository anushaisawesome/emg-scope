// EMG software scope — ESP32 + MCP3208
// Reads MCP3208 channel 0 over SPI at SAMPLE_RATE and streams 12-bit
// samples over USB serial. Pair with plot.py on the Mac.
//
// Wiring (ESP32 dev board VSPI <-> MCP3208 DIP-16):
//   ESP32 3V3  -> MCP3208 pin 16 (VDD)  and pin 15 (VREF)
//   ESP32 GND  -> MCP3208 pin 14 (AGND) and pin 9  (DGND)
//   ESP32 D5   -> MCP3208 pin 10 (CS)
//   ESP32 D18  -> MCP3208 pin 13 (CLK)
//   ESP32 D19  -> MCP3208 pin 12 (DOUT)
//   ESP32 D23  -> MCP3208 pin 11 (DIN)
//   Signal in  -> MCP3208 pin 1  (CH0)
//
// Sanity check: two 10K resistors as a divider between 3V3 and GND,
// midpoint into CH0 -> plot should show a flat line at ~1.65V (~2048).
// Touch CH0 with a finger -> 50Hz mains hum.
//
// Wire format: 2 bytes per sample.
//   byte0 = 0xF0 | (sample >> 8)   high nibble 0xF = sync marker
//   byte1 = sample & 0xFF
// (a 12-bit sample's top bits never exceed 0x0F, so 0xFn only ever
// appears as a first byte — plot.py resyncs on it after any glitch)

#include <SPI.h>

const int PIN_CS = 5;
const uint32_t SAMPLE_RATE = 4000;   // Hz — must fit in 115200 baud (2 bytes/sample)
const int ADC_CHANNEL = 0;           // MCP3208 CH0..CH7

uint32_t samplePeriodUs;
uint32_t nextSampleUs;

uint16_t readMCP3208(uint8_t channel) {
  // single-ended read: start bit, SGL=1, 3 channel bits
  uint8_t cmd = 0b00000110 | (channel >> 2);
  SPI.beginTransaction(SPISettings(100000, MSBFIRST, SPI_MODE0));  // 100kHz: slow but bulletproof for breadboard + suspect chips
  digitalWrite(PIN_CS, LOW);
  SPI.transfer(cmd);
  uint8_t hi = SPI.transfer((channel & 0x03) << 6);
  uint8_t lo = SPI.transfer(0);
  digitalWrite(PIN_CS, HIGH);
  SPI.endTransaction();
  return ((hi & 0x0F) << 8) | lo;
}

void setup() {
  Serial.begin(115200);  // CH340 clones corrupt data at 921600 on macOS — do not raise
  pinMode(PIN_CS, OUTPUT);
  digitalWrite(PIN_CS, HIGH);
  SPI.begin(18, 19, 23, PIN_CS);
  samplePeriodUs = 1000000UL / SAMPLE_RATE;
  nextSampleUs = micros();
}

void loop() {
  uint32_t now = micros();
  if ((int32_t)(now - nextSampleUs) >= 0) {
    nextSampleUs += samplePeriodUs;
    uint16_t s = readMCP3208(ADC_CHANNEL);
    uint8_t buf[2] = { (uint8_t)(0xF0 | (s >> 8)), (uint8_t)(s & 0xFF) };
    Serial.write(buf, 2);
  }
}
