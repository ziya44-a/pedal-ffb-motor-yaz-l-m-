// Pedal Haptic - Arduino Uno + L293D Motor Shield (Adafruit Motor Shield V1 / AFMotor)
// Komutlar (satir sonu ile):
//   M<motor>,<siddet 0-255>,<darbe Hz 0-60>   ornek: M1,200,0  M2,255,20
//   P  -> Arduino "P" cevabi verir (gecikme olcumu icin)
// Motor 1 = FREN, Motor 2 = GAZ. 150 ms komut gelmezse motorlar durur.

#include <AFMotor.h>

AF_DCMotor motors[2] = { AF_DCMotor(1, MOTOR12_1KHZ), AF_DCMotor(2, MOTOR12_1KHZ) };

uint8_t intensity[2] = {0, 0};
uint8_t pulseHz[2]   = {0, 0};
uint8_t lastSpeed[2] = {0, 0};
bool outputOn[2]     = {false, false};
unsigned long lastToggle[2] = {0, 0};
unsigned long lastCommand = 0;

char buf[24];
uint8_t len = 0;

void applyMotor(uint8_t m) {
  uint8_t sp = outputOn[m] ? intensity[m] : 0;
  if (sp != lastSpeed[m]) {
    lastSpeed[m] = sp;
    motors[m].setSpeed(sp);
  }
}

void parseLine() {
  buf[len] = 0;
  if (buf[0] == 'P') { Serial.println('P'); return; }
  if (buf[0] != 'M') return;
  int m = buf[1] - '1';
  if (m < 0 || m > 1) return;
  char* p = strchr(buf, ',');
  if (!p) return;
  int s = atoi(p + 1);
  p = strchr(p + 1, ',');
  if (!p) return;
  int h = atoi(p + 1);
  intensity[m] = constrain(s, 0, 255);
  pulseHz[m]   = constrain(h, 0, 60);
  lastCommand  = millis();
}

void setup() {
  Serial.begin(115200);
  for (uint8_t i = 0; i < 2; i++) {
    motors[i].setSpeed(0);
    motors[i].run(FORWARD);
  }
  lastCommand = millis();
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') { parseLine(); len = 0; }
    else if (c != '\r' && len < sizeof(buf) - 1) buf[len++] = c;
  }

  unsigned long now = millis();
  if (now - lastCommand > 150) { intensity[0] = 0; intensity[1] = 0; }

  for (uint8_t i = 0; i < 2; i++) {
    if (intensity[i] == 0) {
      outputOn[i] = false;
    } else if (pulseHz[i] == 0) {
      outputOn[i] = true;
    } else {
      unsigned long half = 500UL / pulseHz[i];
      if (now - lastToggle[i] >= half) {
        lastToggle[i] = now;
        outputOn[i] = !outputOn[i];
      }
    }
    applyMotor(i);
  }
}
