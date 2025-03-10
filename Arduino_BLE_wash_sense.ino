#include <Arduino_LSM9DS1.h>
#include <ArduinoBLE.h>

// BLE Service and Characteristics
BLEService vibrationService("180D");  
BLEFloatCharacteristic vibrationX("2A37", BLERead | BLENotify);
BLEFloatCharacteristic vibrationY("2A38", BLERead | BLENotify);
BLEFloatCharacteristic vibrationZ("2A39", BLERead | BLENotify);
BLEFloatCharacteristic vibrationMag("2A40", BLERead | BLENotify);

// LED Pins (Built-in RGB LED on Nano 33 BLE)
#define LED_GREEN 23
#define LED_RED 22

void setup() {
    Serial.begin(115200);
    while (!Serial);

    // Initialize LEDs
    pinMode(LED_GREEN, OUTPUT);
    pinMode(LED_RED, OUTPUT);
    digitalWrite(LED_GREEN, HIGH);
    digitalWrite(LED_RED, HIGH);

    // Initialize IMU
    if (!IMU.begin()) {
        Serial.println("Failed to initialize IMU!");
        showError();
    }

    Serial.println("IMU initialized.");

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
}

void loop() {
    BLEDevice central = BLE.central();

    if (central) {
        Serial.print("Connected to: ");
        Serial.println(central.address());

        while (central.connected()) {
            float x, y, z;

            // Read accelerometer data
            if (IMU.accelerationAvailable()) {
                IMU.readAcceleration(x, y, z);

                Serial.print("X: "); Serial.print(x - 1, 6);
                Serial.print(" Y: "); Serial.print(y, 6);
                Serial.print(" Z: "); Serial.print(z, 6);
                float vibrationMagnetude = sqrt((x-1)*(x-1) + (y*y) + (z*z));
                Serial.print(" Mag: "); Serial.println(vibrationMagnetude, 6);

                // Send raw X, Y, Z vibration data via BLE
                vibrationX.writeValue(x - 1);
                vibrationY.writeValue(y);
                vibrationZ.writeValue(z);
                vibrationMag.writeValue(vibrationMagnetude);

                // Blink LED to indicate successful operation
                blinkLED();
            }

            delay(1000);  // Faster updates (every 1000ms)
        }

        Serial.println("Disconnected from BLE device.");
    }
}

// Blink Green LED to indicate normal operation
void blinkLED() {
    digitalWrite(LED_GREEN, LOW);
    delay(100);
    digitalWrite(LED_GREEN, HIGH);
}

// Show error state with Solid Red LED
void showError() {
    digitalWrite(LED_RED, LOW);
    while (1);  // Halt execution
}