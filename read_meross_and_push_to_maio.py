import asyncio
import os
import ssl
import argparse
from dotenv import load_dotenv
import paho.mqtt.client as mqtt
from meross_iot.http_api import MerossHttpClient
from meross_iot.manager import MerossManager
from meross_iot.model.enums import OnlineStatus

# Load environment variables from .env file
load_dotenv()

# MQTT configuration from environment variables
MQTT_BROKER_URL = os.getenv('MQTT_BROKER_URL')
MQTT_BROKER_PORT = int(os.getenv('MQTT_BROKER_PORT'))
MQTT_TOPIC = os.getenv('MQTT_TOPIC')

# Meross configuration from environment variables
EMAIL = os.getenv('MEROSS_EMAIL')
PASSWORD = os.getenv('MEROSS_PASSWORD')

# MQTT SSL context
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# MQTT client setup
mqtt_client = mqtt.Client()
mqtt_client.tls_set_context(ssl_context)

def on_connect(client, userdata, flags, rc):
    print(f"Connected to MQTT broker with result code {rc}")

mqtt_client.on_connect = on_connect
mqtt_client.connect(MQTT_BROKER_URL, MQTT_BROKER_PORT, 60)
mqtt_client.loop_start()

async def retrieve_power_data(publish):
    # Setup the HTTP client API from user-password
    http_api_client = await MerossHttpClient.async_from_user_password(api_base_url='https://iotx-eu.meross.com',
                                                                      email=EMAIL,
                                                                      password=PASSWORD)

    # Setup and start the device manager
    manager = MerossManager(http_client=http_api_client)
    await manager.async_init()

    # Retrieve all devices that are registered on this account
    await manager.async_device_discovery()
    plugs = manager.find_devices(device_type="mss310")

    if len(plugs) < 1:
        print("No Meross plugs found...")
    else:
        for dev in plugs:
            await dev.async_update()
            if dev.online_status == OnlineStatus.ONLINE:
                # Read the electricity power/voltage/current
                power = await dev.async_get_instant_metrics()
                if power is not None:
                    if publish:
                        mqtt_client.publish(MQTT_TOPIC, f"{dev.name}: {power} W")
                        print(f"Published power data: {dev.name}: {power} W")
                    else:
                        print(f"Retrieved power data: {dev.name}: {power} W")
                else:
                    print(f"Device {dev.name} does not support power measurement.")
            else:
                print(f"Device {dev.name} is offline.")

    # Close the manager and logout from http_api
    manager.close()
    await http_api_client.async_logout()

async def main(publish):
    if publish:
        while True:
            await retrieve_power_data(publish)
            await asyncio.sleep(3600)  # Sleep for one hour
    else:
        await retrieve_power_data(publish)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Retrieve and publish Meross plug power data")
    parser.add_argument('--once', action='store_true', help="Retrieve and print data only once without publishing to MQTT")
    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main(not args.once))
    finally:
        loop.stop()
        mqtt_client.loop_stop()

