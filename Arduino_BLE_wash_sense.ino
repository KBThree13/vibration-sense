#include <Arduino_LSM9DS1.h>
#include <ArduinoBLE.h>

// Constants
#define SAMPLING_RATE_HZ 10     // How many samples per second
#define CALIBRATION_SAMPLES 50  // Number of samples to collect for calibration
#define LED_GREEN 23
#define LED_RED 22
#define LED_BLUE 24             // Also available on Nano 33 BLE

// BLE Service and Characteristics
BLEService vibrationService("180D");  
BLEFloatCharacteristic vibrationX("2A37", BLERead | BLENotify);
BLEFloatCharacteristic vibrationY("2A38", BLERead | BLENotify);
BLEFloatCharacteristic vibrationZ("2A39", BLERead | BLENotify);
BLEFloatCharacteristic vibrationMag("2A40", BLERead | BLENotify);

// Global variables
float offsetX = 0.0;
float offsetY = 0.0;
float offsetZ = 0.0;
unsigned long previousMillis = 0;
const long interval = 1000 / SAMPLING_RATE_HZ;  // Interval in milliseconds
bool connectionActive = false;

void setup() {
    Serial.begin(115200);
    
    // Don't wait for Serial in production code
    // This allows the device to function without a USB connection
    // while (!Serial);
    
    // Initialize LEDs
    pinMode(LED_GREEN, OUTPUT);
    pinMode(LED_RED, OUTPUT);
    pinMode(LED_BLUE, OUTPUT);
    
    // All LEDs off initially (they are active LOW)
    digitalWrite(LED_GREEN, HIGH);
    digitalWrite(LED_RED, HIGH);
    digitalWrite(LED_BLUE, HIGH);
    
    // Initialize IMU
    if (!IMU.begin()) {
        Serial.println("Failed to initialize IMU!");
        showError();
    }
    Serial.println("IMU initialized.");
    
    // Calibrate the accelerometer
    calibrateAccelerometer();
    
    // Initialize BLE
    if (!BLE.begin()) {
        Serial.println("Starting BLE failed!");
        showError();
    }
    Serial.println("BLE initialized.");
    
    // BLE Setup
    BLE.setLocalName("Nano33BLE_Vibration");
    BLE.setAdvertisedService(vibrationService);
    
    vibrationService.addCharacteristic(vibrationX);
    vibrationService.addCharacteristic(vibrationY);
    vibrationService.addCharacteristic(vibrationZ);
    vibrationService.addCharacteristic(vibrationMag);
    
    BLE.addService(vibrationService);
    BLE.advertise();
    Serial.println("BLE Advertising...");
    
    // Initial values
    vibrationX.writeValue(0.0);
    vibrationY.writeValue(0.0);
    vibrationZ.writeValue(0.0);
    vibrationMag.writeValue(0.0);
}

void loop() {
    // Check for BLE central device
    BLEDevice central = BLE.central();
    
    if (central && !connectionActive) {
        connectionActive = true;
        Serial.print("Connected to: ");
        Serial.println(central.address());
        digitalWrite(LED_BLUE, LOW);  // Blue LED on when connected
    }
    
    // Check if we've disconnected
    if (!central && connectionActive) {
        connectionActive = false;
        Serial.println("Disconnected from BLE device.");
        digitalWrite(LED_BLUE, HIGH);  // Blue LED off when disconnected
    }
    
    // Only process data if connected
    if (connectionActive) {
        unsigned long currentMillis = millis();
        
        // Check if it's time to read the sensor
        if (currentMillis - previousMillis >= interval) {
            previousMillis = currentMillis;
            readAndSendSensorData();
        }
    } else {
        // When not connected, just poll for connections
        delay(100);
    }
    
    // Always keep the BLE stack running
    BLE.poll();
}

void readAndSendSensorData() {
    float x, y, z;
    
    // Read accelerometer data
    if (IMU.accelerationAvailable()) {
        IMU.readAcceleration(x, y, z);
        
        // Apply calibration offsets
        x -= offsetX;
        y -= offsetY;
        z -= offsetZ;
        
        // Calculate magnitude (Euclidean norm)
        float vibrationMagnitude = sqrt(x*x + y*y + z*z);
        
        // Log data for debugging
        Serial.print("X: "); Serial.print(x, 6);
        Serial.print(" Y: "); Serial.print(y, 6);
        Serial.print(" Z: "); Serial.print(z, 6);
        Serial.print(" Mag: "); Serial.println(vibrationMagnitude, 6);
        
        // Send vibration data via BLE
        vibrationX.writeValue(x);
        vibrationY.writeValue(y);
        vibrationZ.writeValue(z);
        vibrationMag.writeValue(vibrationMagnitude);
        
        // Blink LED to indicate successful operation
        blinkLED();
    }
}

void calibrateAccelerometer() {
    Serial.println("Calibrating accelerometer...");
    digitalWrite(LED_BLUE, LOW);  // Blue LED on during calibration
    
    float sumX = 0, sumY = 0, sumZ = 0;
    int samples = 0;
    
    while (samples < CALIBRATION_SAMPLES) {
        if (IMU.accelerationAvailable()) {
            float x, y, z;
            IMU.readAcceleration(x, y, z);
            
            sumX += x;
            sumY += y;
            sumZ += z;
            samples++;
            
            // Blink green LED to show progress
            if (samples % 10 == 0) {
                blinkLED();
            }
            
            delay(20);  // Small delay between readings
        }
    }
    
    // Calculate average offsets
    offsetX = sumX / CALIBRATION_SAMPLES;
    offsetY = sumY / CALIBRATION_SAMPLES;
    offsetZ = sumZ / CALIBRATION_SAMPLES;
    
    // Adjust Z to keep gravity (should be close to 1G)
    offsetZ = offsetZ - 1.0;
    
    Serial.println("Calibration complete!");
    Serial.print("Offsets - X: "); Serial.print(offsetX, 6);
    Serial.print(" Y: "); Serial.print(offsetY, 6);
    Serial.print(" Z: "); Serial.println(offsetZ, 6);
    
    digitalWrite(LED_BLUE, HIGH);  // Blue LED off after calibration
}

// Blink Green LED to indicate normal operation
void blinkLED() {
    digitalWrite(LED_GREEN, LOW);
    delay(10);  // Shorter blink to avoid blocking
    digitalWrite(LED_GREEN, HIGH);
}

// Show error state with Solid Red LED
void showError() {
    digitalWrite(LED_RED, LOW);  // Red LED on
    
    // Blink the blue LED in error state to distinguish from normal operation
    while (1) {
        digitalWrite(LED_BLUE, LOW);
        delay(300);
        digitalWrite(LED_BLUE, HIGH);
        delay(300);
    }
}
