// Allocate 90KB for the buffer
const int MAX_SAMPLES = 30000;
uint8_t dataBuffer[MAX_SAMPLES * 3];

void setup() {
  // Initialize Native USB
  SerialUSB.begin(2000000); 
  
  // Set DAQ resolution to 8-bit
  analogReadResolution(8); 
}

void loop() {
  if (SerialUSB.available() > 0) {
    char cmd = SerialUSB.read();
    
    if (cmd == 'C') { // Commands. Virmen Style
      collectData();
    } 
    else if (cmd == 'S') {
      sendData();
    }
  }
}

void collectData() {
  // Collect data. Choose Delay suitably
  for (int i = 0; i < MAX_SAMPLES; i++) {
    int idx = i * 3;
    dataBuffer[idx]     = analogRead(A0); // X-axis (~60Hz)
    dataBuffer[idx + 1] = analogRead(A1); // Y-axis (~1Hz)
    dataBuffer[idx + 2] = analogRead(A2); // Z-axis (Intensity)
    delayMicroseconds(50);
  }
}

void sendData() {
  // Dump memory block directly over Native USB
  SerialUSB.write(dataBuffer, MAX_SAMPLES * 3);
}
