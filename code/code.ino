// Pin definitions - check with custom shield.
const int DAC_X = DAC1; // Fast axis
const int DAC_Y = DAC0; // Slow axis
const int ADC_Z = A0;   // Photosensor input

// Scanning parameters
const int PIXELS = 128;
const int FAST_PIXELS = 50; // High-speed, for Oscilloscope in TV mode. Analog read via scope.
const int DELAY_US = 20; 
const int TOTAL_PIXELS = PIXELS * PIXELS;

// State Tracking
char currentState = 'I'; // 'I' = Idle
int zoomPercent = 100;   // 1 to 100% scale for amplitude

// Data buffer: 128 * 128 * 3 bytes = 49,152 bytes. 
uint8_t imageData[TOTAL_PIXELS][3];

void setup() {
  SerialUSB.begin(115200); 
  
  // Set ADC and DAC to 12-bit resolution (0-4095)
  analogReadResolution(12);
  analogWriteResolution(12);
  
  // Initialize mirrors to center position
  analogWrite(DAC_X, 2048);
  analogWrite(DAC_Y, 2048);
}

// Helper function to calculate scaled DAC value around the center (2048)
int getDacVal(int idx, int max_pixels) {
  long raw = map(idx, 0, max_pixels - 1, 0, 4095);
  return 2048 + ((raw - 2048) * zoomPercent) / 100;
}

void loop() {
  // 1. Check for incoming commands over Native USB
  if (SerialUSB.available() > 0) {
    char cmd = SerialUSB.read();
    
    if (cmd == 'C') {
      currentState = 'I'; 
      collectData();
    } 
    else if (cmd == 'S') {
      currentState = 'I'; 
      transferData();
    }
    else if (cmd == 'X' || cmd == 'Y' || cmd == 'B' || cmd == 'L' || cmd == 'F') {
      currentState = cmd; // Enter continuous state
    }
    else if (cmd == 'Z') {
      // Wait for the next byte which contains the zoom level
      while (SerialUSB.available() == 0) {} 
      zoomPercent = SerialUSB.read();
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
  else if (currentState == 'F') {
    demoFastScanXY();
  }
  else if (currentState == 'L') {
    liveScan();
  }
}

// --- Data Acquisition Methods ---

void collectData() {
  int pixelIndex = 0;
  
  for (int y = 0; y < PIXELS; y++) {
    analogWrite(DAC_Y, getDacVal(y, PIXELS));
    
    analogWrite(DAC_X, getDacVal(0, PIXELS)); // Snap mirror back to start
    delay(2); // Wait 2ms for mirror to physically settle
    
    for (int x = 0; x < PIXELS; x++) {
      analogWrite(DAC_X, getDacVal(x, PIXELS));
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
  SerialUSB.write((uint8_t*)imageData, TOTAL_PIXELS * 3);
}

// --- Live Stream Method ---

void liveScan() {
  for (int y = 0; y < PIXELS; y++) {
    analogWrite(DAC_Y, getDacVal(y, PIXELS));
    
    analogWrite(DAC_X, getDacVal(0, PIXELS)); 
    delay(2); // Flyback
    
    uint8_t rowBuf[PIXELS]; 
    
    for (int x = 0; x < PIXELS; x++) {
      if (SerialUSB.available() > 0) return; 
      
      analogWrite(DAC_X, getDacVal(x, PIXELS));
      delayMicroseconds(DELAY_US);
      int z_val = analogRead(ADC_Z);
      
      rowBuf[x] = (uint8_t)(z_val >> 4); 
    }
    SerialUSB.write(rowBuf, PIXELS); 
  }
}

// --- Demo Methods (No Data Acquisition) ---

void demoScanX() {
  analogWrite(DAC_Y, 2048); 
  for (int x = 0; x < PIXELS; x++) {
    if (SerialUSB.available() > 0) return; 
    analogWrite(DAC_X, getDacVal(x, PIXELS));
    delayMicroseconds(DELAY_US);
  }
}

void demoScanY() {
  analogWrite(DAC_X, 2048); 
  for (int y = 0; y < PIXELS; y++) {
    if (SerialUSB.available() > 0) return; 
    analogWrite(DAC_Y, getDacVal(y, PIXELS));
    delayMicroseconds(100*DELAY_US); 
  }
}

void demoScanXY() {
  for (int y = 0; y < PIXELS; y++) {
    analogWrite(DAC_Y, getDacVal(y, PIXELS));
    for (int x = 0; x < PIXELS; x++) {
      if (SerialUSB.available() > 0) return; 
      analogWrite(DAC_X, getDacVal(x, PIXELS));
      delayMicroseconds(DELAY_US);
    }
  }
}

// High-Speed Scan for oscilloscope. Zig-zag pattern and LUT optimization.
void demoFastScanXY() {
  // 1. Create a Look-Up Table (LUT) for the DAC values.
  // Gemini advise: This prevents doing heavy math (map, multiply, divide) inside the fast inner loop.
  int dacLut[FAST_PIXELS];
  for (int i = 0; i < FAST_PIXELS; i++) {
    dacLut[i] = getDacVal(i, FAST_PIXELS);
  }

  // Then execute the Zig-Zag Scan
  for (int y = 0; y < FAST_PIXELS; y++) {
    analogWrite(DAC_Y, dacLut[y]); // Step the slow axis
    
    // Check if the row is even or odd to determine scan direction
    if (y % 2 == 0) {
      // Even row: Scan Left to Right
      for (int x = 0; x < FAST_PIXELS; x++) {
        if (SerialUSB.available() > 0) return; 
        analogWrite(DAC_X, dacLut[x]);
        delayMicroseconds(5);
      }
    } else {
      // Odd row: Scan Right to Left (Zig-Zag)
      for (int x = FAST_PIXELS - 1; x >= 0; x--) {
        if (SerialUSB.available() > 0) return; 
        analogWrite(DAC_X, dacLut[x]);
        delayMicroseconds(5);
      }
    }
  }
}
