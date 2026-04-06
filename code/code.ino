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

// Data buffer: 128 * 128 * 3 bytes = 49,152 bytes. 
// The Arduino Due has 96KB of RAM, so this easily fits.
uint8_t imageData[TOTAL_PIXELS][3];

void setup() {
  // Use the highest native baud rate for the programming port, 
  // or use 'SerialUSB' if using the Native USB port.
  Serial.begin(115200); 
  
  // Set ADC and DAC to 12-bit resolution (0-4095)
  analogReadResolution(12);
  analogWriteResolution(12);
  
  // Initialize mirrors to 0 position
  analogWrite(DAC_X, 2048);
  analogWrite(DAC_Y, 2048);
}

void loop() {
  // 1. Check for incoming commands
  if (Serial.available() > 0) {
    char cmd = Serial.read();
    
    if (cmd == 'C') {
      currentState = 'I'; // Pause demo if running
      collectData();
    } 
    else if (cmd == 'S') {
      currentState = 'I'; 
      transferData();
    }
    else if (cmd == 'X' || cmd == 'Y' || cmd == 'B') {
      currentState = cmd; // Enter a continuous demo state
    }
    else if (cmd == 'H') {
      // Halt demo and return to center
      currentState = 'I';
      analogWrite(DAC_X, 2048);
      analogWrite(DAC_Y, 2048);
    }
  }

  // 2. Execute active demo state (if any)
  if (currentState == 'X') {
    demoScanX();
  } 
  else if (currentState == 'Y') {
    demoScanY();
  } 
  else if (currentState == 'B') {
    demoScanXY();
  }
}

// --- Data Acquisition Methods ---

void collectData() {
  int pixelIndex = 0;
  
  for (int y = 0; y < PIXELS; y++) {
    int dac_y_val = map(y, 0, PIXELS - 1, 0, 4095);
    analogWrite(DAC_Y, dac_y_val);
    
    for (int x = 0; x < PIXELS; x++) {
      int dac_x_val = map(x, 0, PIXELS - 1, 0, 4095);
      analogWrite(DAC_X, dac_x_val);
      
      // Settling time for galvo mirror
      delayMicroseconds(DELAY_US);
      
      // Read intensity
      int z_val = analogRead(ADC_Z);
      
      // Store in buffer
      imageData[pixelIndex][0] = (uint8_t)x;
      imageData[pixelIndex][1] = (uint8_t)y;
      imageData[pixelIndex][2] = (uint8_t)(z_val >> 4); 
      
      pixelIndex++;
    }
  }
  
  // Return to origin safely after scan
  analogWrite(DAC_X, 2048);
  analogWrite(DAC_Y, 2048);
}

void transferData() {
  Serial.write((uint8_t*)imageData, TOTAL_PIXELS * 3);
}

// --- Demo Methods (No Data Acquisition) ---

void demoScanX() {
  analogWrite(DAC_Y, 2048); // Keep Y centered
  for (int x = 0; x < PIXELS; x++) {
    if (Serial.available() > 0) return; // Exit immediately if a new command arrives
    
    int dac_x_val = map(x, 0, PIXELS - 1, 0, 4095);
    analogWrite(DAC_X, dac_x_val);
    delayMicroseconds(DELAY_US);
  }
}

void demoScanY() {
  analogWrite(DAC_X, 2048); // Keep X centered
  for (int y = 0; y < PIXELS; y++) {
    if (Serial.available() > 0) return; // Exit immediately if a new command arrives
    
    int dac_y_val = map(y, 0, PIXELS - 1, 0, 4095);
    analogWrite(DAC_Y, dac_y_val);
    // Y naturally sweeps slower than X in a raster, 
    // so we scale the delay to make the mirror motion visible/safe.
    delayMicroseconds(DELAY_US*2); 
  }
}

void demoScanXY() {
  // Exact same raster motion as Collect, but without reading the ADC
  for (int y = 0; y < PIXELS; y++) {
    int dac_y_val = map(y, 0, PIXELS - 1, 0, 4095);
    analogWrite(DAC_Y, dac_y_val);
    
    for (int x = 0; x < PIXELS; x++) {
      if (Serial.available() > 0) return; // Break inner loop if stopped
      
      int dac_x_val = map(x, 0, PIXELS - 1, 0, 4095);
      analogWrite(DAC_X, dac_x_val);
      delayMicroseconds(DELAY_US);
    }
  }
}
