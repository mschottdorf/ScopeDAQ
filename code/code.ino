// Pin definitions
const int DAC_X = DAC0; // Fast axis
const int DAC_Y = DAC1; // Slow axis
const int ADC_Z = A0;   // Photosensor input

// Scanning parameters
const int PIXELS = 128;
const int DELAY_US = 200;
const int TOTAL_PIXELS = PIXELS * PIXELS;

// State Tracking
char currentState = 'I'; // 'I' = Idle
int zoomPercent = 100;   // 1 to 100% scale for amplitude

// Data buffer: 128 * 128 * 3 bytes = 49,152 bytes. 
uint8_t imageData[TOTAL_PIXELS][3];

void setup() {
  Serial.begin(115200); 
  
  // Set ADC and DAC to 12-bit resolution (0-4095)
  analogReadResolution(12);
  analogWriteResolution(12);
  
  // Initialize mirrors to 0 position
  analogWrite(DAC_X, 2048);
  analogWrite(DAC_Y, 2048);
}

// Helper function to calculate scaled DAC value around the center (2048)
int getDacVal(int idx) {
  long raw = map(idx, 0, PIXELS - 1, 0, 4095);
  return 2048 + ((raw - 2048) * zoomPercent) / 100;
}

void loop() {
  // 1. Check for incoming commands
  if (Serial.available() > 0) {
    char cmd = Serial.read();
    
    if (cmd == 'C') {
      currentState = 'I'; 
      collectData();
    } 
    else if (cmd == 'S') {
      currentState = 'I'; 
      transferData();
    }
    else if (cmd == 'X' || cmd == 'Y' || cmd == 'B' || cmd == 'L') {
      currentState = cmd; // Enter continuous state (Demo or Live)
    }
    else if (cmd == 'Z') {
      // Wait for the next byte which contains the zoom level
      while (Serial.available() == 0) {} 
      zoomPercent = Serial.read();
    }
    else if (cmd == 'H') {
      // Halt and return to center
      currentState = 'I';
      analogWrite(DAC_X, 2048);
      analogWrite(DAC_Y, 2048);
    }
  }

  // 2. Execute active state
  if (currentState == 'X') {
    demoScanX();
  } 
  else if (currentState == 'Y') {
    demoScanY();
  } 
  else if (currentState == 'B') {
    demoScanXY();
  }
  else if (currentState == 'L') {
    liveScan();
  }
}

// --- Data Acquisition Methods ---

void collectData() {
  int pixelIndex = 0;
  
  for (int y = 0; y < PIXELS; y++) {
    analogWrite(DAC_Y, getDacVal(y));
    
    for (int x = 0; x < PIXELS; x++) {
      analogWrite(DAC_X, getDacVal(x));
      delayMicroseconds(DELAY_US);
      
      int z_val = analogRead(ADC_Z);
      
      imageData[pixelIndex][0] = (uint8_t)x;
      imageData[pixelIndex][1] = (uint8_t)y;
      imageData[pixelIndex][2] = (uint8_t)(z_val >> 4); 
      
      pixelIndex++;
    }
  }
  
  analogWrite(DAC_X, 2048);
  analogWrite(DAC_Y, 2048);
}

void transferData() {
  Serial.write((uint8_t*)imageData, TOTAL_PIXELS * 3);
}

// --- Live Stream Method ---

void liveScan() {
  // Transmit row-by-row to optimize USB overhead
  for (int y = 0; y < PIXELS; y++) {
    analogWrite(DAC_Y, getDacVal(y));
    uint8_t rowBuf[PIXELS * 3];
    int idx = 0;
    
    for (int x = 0; x < PIXELS; x++) {
      if (Serial.available() > 0) return; // Exit to handle new commands (Stop or Zoom)
      
      analogWrite(DAC_X, getDacVal(x));
      delayMicroseconds(DELAY_US);
      int z_val = analogRead(ADC_Z);
      
      rowBuf[idx++] = (uint8_t)x;
      rowBuf[idx++] = (uint8_t)y;
      rowBuf[idx++] = (uint8_t)(z_val >> 4);
    }
    
    // Blast the entire row over serial
    Serial.write(rowBuf, PIXELS * 3);
  }
}

// --- Demo Methods (No Data Acquisition) ---

void demoScanX() {
  analogWrite(DAC_Y, 2048); 
  for (int x = 0; x < PIXELS; x++) {
    if (Serial.available() > 0) return; 
    analogWrite(DAC_X, getDacVal(x));
    delayMicroseconds(DELAY_US);
  }
}

void demoScanY() {
  analogWrite(DAC_X, 2048); 
  for (int y = 0; y < PIXELS; y++) {
    if (Serial.available() > 0) return; 
    analogWrite(DAC_Y, getDacVal(y));
    delayMicroseconds(DELAY_US * 2); 
  }
}

void demoScanXY() {
  for (int y = 0; y < PIXELS; y++) {
    analogWrite(DAC_Y, getDacVal(y));
    for (int x = 0; x < PIXELS; x++) {
      if (Serial.available() > 0) return; 
      analogWrite(DAC_X, getDacVal(x));
      delayMicroseconds(DELAY_US);
    }
  }
}
