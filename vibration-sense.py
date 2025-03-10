import asyncio
from bleak import BleakClient, BleakScanner, BleakError
from losantmqtt import Device
import logging
from dotenv import load_dotenv
import os
import struct
import collections
import statistics
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv(override=True)

# Constants
VIBRATION_SERVICE_UUID = "180D"
VIBRATION_CHARACTERISTIC_UUID = "2A40"
DEVICE_NAME = "Nano33BLE_Vibration"

# Vibration thresholds and timers
VIBRATION_HIGH_THRESHOLD = 0.002
VIBRATION_LOW_THRESHOLD = 0.001
VIBRATION_RESET_TIME = 120  # seconds
VIBRATION_SAMPLE_SIZE = 10
RECONNECT_DELAY = 5  # seconds
MAX_RECONNECT_ATTEMPTS = 5

class VibrationMonitor:
    def __init__(self):
        # Losant credentials
        self.losant_device_id = os.getenv('LOSANT_DEVICE_ID')
        self.losant_access_key = os.getenv('LOSANT_ACCESS_KEY')
        self.losant_access_secret = os.getenv('LOSANT_ACCESS_SECRET')
        
        # Initialize Losant device
        self.losant_device = Device(
            self.losant_device_id, 
            self.losant_access_key, 
            self.losant_access_secret
        )
        self.losant_device.add_event_observer('command', self.on_command)
        
        # Vibration monitoring
        self.vibration_data = collections.deque(maxlen=VIBRATION_SAMPLE_SIZE)
        self.vibration_timer = VIBRATION_RESET_TIME
        self.vibrations_detected = False
        
        # BLE client
        self.client = None
        self.device = None
        self.connected = False

    def on_command(self, device, command):
        """Handle commands from Losant."""
        logger.info(f"Command received: {command['name']} with payload: {command['payload']}")

    async def notification_handler(self, sender, data):
        """Handle incoming BLE notifications from the Arduino."""
        try:
            # Unpack the float from the bytearray
            vibration_mag_float = struct.unpack('<f', data)[0]
            self.vibration_data.append(vibration_mag_float)
            
            # Only proceed with analysis if we have enough data
            if len(self.vibration_data) >= VIBRATION_SAMPLE_SIZE:
                await self.analyze_vibration(vibration_mag_float)
        except Exception as e:
            logger.error(f"Error processing notification: {e}")

    async def analyze_vibration(self, current_magnitude):
        """Analyze vibration data and update state if necessary."""
        vib_stdev = statistics.stdev(self.vibration_data)
        logger.debug(f"Vibration standard deviation: {vib_stdev}")
        
        # Check for vibration start
        if not self.vibrations_detected and vib_stdev > VIBRATION_HIGH_THRESHOLD:
            self.vibrations_detected = True
            logger.info("Vibrations detected!")
            await self.send_state(True, current_magnitude)
        
        # Check for vibration stop
        elif self.vibrations_detected and vib_stdev < VIBRATION_LOW_THRESHOLD:
            self.vibration_timer -= 1
            logger.debug(f"Vibration timer: {self.vibration_timer}")
            
            if self.vibration_timer <= 0:
                self.vibrations_detected = False
                logger.info("Vibrations stopped!")
                await self.send_state(False, current_magnitude)
                self.vibration_timer = VIBRATION_RESET_TIME
        
        # Reset timer if vibrations resume
        elif self.vibrations_detected and vib_stdev > VIBRATION_LOW_THRESHOLD and self.vibration_timer < VIBRATION_RESET_TIME:
            self.vibration_timer = VIBRATION_RESET_TIME
            logger.debug("Vibration timer reset")

    async def send_state(self, vibration_detected, magnitude):
        """Send state update to Losant."""
        if self.losant_device.is_connected():
            self.losant_device.send_state({
                'vibrationDetected': vibration_detected, 
                'vibrationMagnitude': magnitude
            })
            logger.info(f"State sent to Losant: vibration={'detected' if vibration_detected else 'not detected'}, magnitude={magnitude}")
        else:
            logger.warning(f"Losant not connected when trying to send vibration state: {vibration_detected}")
            # Try to reconnect to Losant
            self.connect_losant()

    def connect_losant(self):
        """Connect to Losant MQTT broker."""
        try:
            self.losant_device.connect(blocking=False)
            logger.info("Connected to Losant MQTT broker")
        except Exception as e:
            logger.error(f"Failed to connect to Losant: {e}")

    async def scan_for_device(self):
        """Scan for the BLE device."""
        logger.info(f"Scanning for device: {DEVICE_NAME}")
        device = await BleakScanner.find_device_by_name(DEVICE_NAME)
        if device:
            logger.info(f"Device found: {device.name} ({device.address})")
            return device
        logger.warning(f"Device {DEVICE_NAME} not found")
        return None

    async def connect_ble(self):
        """Connect to the BLE device and start notifications."""
        if not self.device:
            self.device = await self.scan_for_device()
            if not self.device:
                return False
        
        try:
            logger.info(f"Connecting to {self.device.name}...")
            self.client = BleakClient(self.device)
            await self.client.connect()
            logger.info(f"Connected to {self.device.name}")
            
            # Start notifications
            await self.client.start_notify(
                VIBRATION_CHARACTERISTIC_UUID.lower(), 
                self.notification_handler
            )
            logger.info("BLE notifications started")
            self.connected = True
            return True
        except BleakError as e:
            logger.error(f"BLE connection error: {e}")
            self.connected = False
            return False
        except Exception as e:
            logger.error(f"Unexpected error connecting to BLE device: {e}")
            self.connected = False
            return False

    async def disconnect_ble(self):
        """Disconnect from the BLE device."""
        if self.client and self.client.is_connected:
            try:
                await self.client.stop_notify(VIBRATION_CHARACTERISTIC_UUID.lower())
                await self.client.disconnect()
                logger.info("Disconnected from BLE device")
            except Exception as e:
                logger.error(f"Error disconnecting from BLE device: {e}")
            finally:
                self.connected = False
                self.client = None

    async def run_losant_loop(self):
        """Run the Losant loop periodically."""
        while True:
            try:
                self.losant_device.loop()
                await asyncio.sleep(1)  # Run Losant loop more frequently
            except Exception as e:
                logger.error(f"Error in Losant loop: {e}")
                # Try to reconnect
                self.connect_losant()
                await asyncio.sleep(1)

    async def run(self):
        """Main run method."""
        # Connect to Losant
        self.connect_losant()
        
        # Start Losant loop as a separate task
        losant_task = asyncio.create_task(self.run_losant_loop())
        
        # Main BLE connection and monitoring loop
        reconnect_attempts = 0
        while True:
            try:
                if not self.connected:
                    if reconnect_attempts >= MAX_RECONNECT_ATTEMPTS:
                        logger.warning(f"Max reconnect attempts ({MAX_RECONNECT_ATTEMPTS}) reached, rescanning for device...")
                        self.device = None
                        reconnect_attempts = 0
                    
                    connected = await self.connect_ble()
                    if not connected:
                        reconnect_attempts += 1
                        logger.info(f"Reconnect attempt {reconnect_attempts}/{MAX_RECONNECT_ATTEMPTS}")
                        await asyncio.sleep(RECONNECT_DELAY)
                        continue
                    reconnect_attempts = 0
                
                # Check if still connected
                if self.client and not self.client.is_connected:
                    logger.warning("BLE connection lost")
                    self.connected = False
                    await asyncio.sleep(RECONNECT_DELAY)
                    continue
                
                # Everything is good, just sleep
                await asyncio.sleep(1)
                
            except asyncio.CancelledError:
                logger.info("Task cancelled, cleaning up...")
                await self.disconnect_ble()
                losant_task.cancel()
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                await self.disconnect_ble()
                await asyncio.sleep(RECONNECT_DELAY)

async def main():
    """Main entry point."""
    monitor = VibrationMonitor()
    try:
        await monitor.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
    except Exception as e:
        logger.error(f"Unhandled exception in main: {e}")
    finally:
        # Ensure we disconnect properly
        await monitor.disconnect_ble()
        logger.info("Application shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())