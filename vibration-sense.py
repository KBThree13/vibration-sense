import asyncio
from bleak import BleakClient, BleakScanner, BleakError
from losantmqtt import Device
import logging
from dotenv import load_dotenv
import os
import struct
import collections
import statistics

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv(override=True)

# Losant credentials
LOSANT_DEVICE_ID = os.getenv('LOSANT_DEVICE_ID')
LOSANT_ACCESS_KEY = os.getenv('LOSANT_ACCESS_KEY')
LOSANT_ACCESS_SECRET = os.getenv('LOSANT_ACCESS_SECRET')

# UUIDs for the service and characteristic
VIBRATION_SERVICE_UUID = "180D"
VIBRATION_CHARACTERISTIC_UUID = "2A40"

# Global variable to store the Losant device
losant_device = None
losant_device = Device(LOSANT_DEVICE_ID, LOSANT_ACCESS_KEY, LOSANT_ACCESS_SECRET)

#initialize vibration queue
vibration_data = collections.deque(maxlen=10)

#vibrations latch
vibrations_detected = False

def on_command(device, command):
    print("Command received.")
    print(command["name"])
    print(command["payload"])

losant_device.add_event_observer('command', on_command)

async def notification_handler(sender, data):
    """Handles incoming BLE notifications from the Arduino."""
    # Data is a bytearray
    vibration_mag_float = struct.unpack('<f', data)[0]
    vibration_data.append(vibration_mag_float)

    global vibrations_detected

    if len(vibration_data) > 9:
        vib_stdev = statistics.stdev(vibration_data)
        print(vib_stdev)

        if not vibrations_detected and vib_stdev > 0.002:
            vibrations_detected = True
            print("Vibrations are occurring!")
            if losant_device.is_connected():
                losant_device.send_state({'vibrationDetected': True, 'vibrationMagnitude': vibration_mag_float})
            else:
                print('Losant not connected...Status 1')
        if vibrations_detected and vib_stdev < 0.002:
            vibrations_detected = False
            print("No Vibrations or Vibrations Stopped!")
            if losant_device.is_connected():
                losant_device.send_state({'vibrationDetected': False, 'vibrationMagnitude': vibration_mag_float })
            else:
                print('Losant not connected...Status 0')

async def scan():
    return await BleakScanner.find_device_by_name("Nano33BLE_Vibration")

async def connect(device):
    async with BleakClient(device) as client:
        await client.start_notify(VIBRATION_CHARACTERISTIC_UUID.lower(), notification_handler)
        print('Notifications Started')
        while True:
            losant_device.loop()
            await asyncio.sleep(1)
    
#one async main function that does everything.
async def main():
    device = await scan()
    print('Device Found')
    if not device:
        print("Device not found")
        return
    
    losant_device.connect(blocking=False)
    
    await connect(device)

asyncio.run(main())
