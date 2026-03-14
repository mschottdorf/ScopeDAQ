// Pin definitions
const int DAC_X = DAC0; // Fast axis
const int DAC_Y = DAC1; // Slow axis
const int ADC_Z = A0;   // Photosensor input

// Scanning parameters
const int PIXELS = 128;
const int DELAY_US = 200;
const int TOTAL_PIXELS = PIXELS * PIXELS;

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
  if (Serial.available() > 0) {
    char cmd = Serial.read();
    
    if (cmd == 'C') {
      collectData();
    } 
    else if (cmd == 'S') {
      transferData();
    }
  }
analogWrite(DAC_X, 2048);
analogWrite(DAC_X, 2048);
}

void collectData() {
  int pixelIndex = 0;
  
  for (int y = 0; y < PIXELS; y++) {
    // Map 0-127 row to 0-4095 DAC voltage
    int dac_y_val = map(y, 0, PIXELS - 1, 0, 4095);
    analogWrite(DAC_Y, dac_y_val);
    
    // Calculate approximate Y voltage (assuming 3.3V logic)
    float voltage_y = dac_y_val * (3.3 / 4095.0);
    
    for (int x = 0; x < PIXELS; x++) {
      // Map 0-127 column to 0-4095 DAC voltage
      int dac_x_val = map(x, 0, PIXELS - 1, 0, 4095);
      analogWrite(DAC_X, dac_x_val);
      
      // Calculate approximate X voltage
//      float voltage_x = dac_x_val * (3.3 / 4095.0);
      
//      // --- DEBUG SERIAL OUT ---
//      Serial.print("Pixel (");
//      Serial.print(x);
//      Serial.print(",");
//      Serial.print(y);
//      Serial.print(") | X: ");
//      Serial.print(voltage_x, 2); // Print with 2 decimal places
//      Serial.print("V | Y: ");
//      Serial.print(voltage_y, 2);
//      Serial.println("V");
//      // ------------------------
      
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
  // Send the entire buffer as raw bytes
  // 49,152 bytes at 2Mbps takes ~245 milliseconds
  Serial.write((uint8_t*)imageData, TOTAL_PIXELS * 3);
}
