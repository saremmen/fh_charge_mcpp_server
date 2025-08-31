import asyncio
import json
import logging
import websockets
from ocpp.routing import on
from ocpp.v16 import ChargePoint as cp
from evcharger_handler import EVChargePoint
from mqtt_client import MQTTClient
# For robust logging encoding
import os
import sys

# Load settings
with open("config.json") as f:
    config = json.load(f)

# Ensure log directory exists
log_file = config["logging"]["file"]
log_dir = os.path.dirname(log_file)
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Setup logging: all logs to file, only warnings and above to console
log_level = getattr(logging, config["logging"]["level"].upper())
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
# Remove all handlers associated with the root logger object.
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)
file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
file_handler.setFormatter(formatter)
file_handler.setLevel(log_level)
console_stream = open(sys.stdout.fileno(), mode='w', encoding='utf-8', errors='replace', buffering=1)
console_handler = logging.StreamHandler(console_stream)
console_handler.setFormatter(formatter)
console_handler.setLevel(getattr(logging, config["logging"]["to_console_level"].upper()))
root_logger = logging.getLogger()
root_logger.setLevel(log_level)
root_logger.handlers = []
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

import asyncio
main_loop = asyncio.get_event_loop()
charge_points = {}
mqtt_client = MQTTClient(config["mqtt"], main_loop)

async def on_connect(websocket):
    """
    Handle new incoming WebSocket connections from EV chargers.
    """
    
    cp_id = config["ocpp"]["charge_point_id"]
    charge_point = EVChargePoint(cp_id, websocket, mqtt_client, config)
    # Store the charge_point instance globally
    charge_points[cp_id] = charge_point

    # Publish MQTT discovery for controls
    charge_point.publish_control_discovery()
    # Publish MQTT discovery for last_charging_start sensor
    charge_point.publish_last_charging_start_sensor()
    # Subscribe to control topics
    mqtt_client.subscribe_control_topics(cp_id)

    main_loop = None  # Will be set in main()

    # Glue: handle incoming MQTT commands
    def handle_command(topic, payload):
        logging.info(f"handle_command called with topic={topic}, payload={payload}")
        import json
        with open("config.json") as f:
            config = json.load(f)
        # Use the correct charge_point instance from the global dict
        cp_id = config["ocpp"]["charge_point_id"]
        cp = charge_points.get(cp_id)
        if cp is None:
            logging.error(f"No charge_point instance found for id {cp_id}")
            return
        try:
            global main_loop
            logging.info(f"Scheduling handle_mqtt_command on main event loop... main_loop={main_loop}, cp={cp}, cp_id={cp_id}")
            def _debug_task():
                logging.info(f"IN main_loop: about to create_task for handle_mqtt_command (cp={cp}, cp_id={cp_id})")
                asyncio.create_task(cp.handle_mqtt_command(topic, payload, config))
            if main_loop is not None:
                main_loop.call_soon_threadsafe(_debug_task)
                logging.info("Scheduled handle_mqtt_command successfully.")
            else:
                logging.error("main_loop is None! Cannot schedule handle_mqtt_command.")
        except Exception as e:
            logging.exception(f"Exception while scheduling handle_mqtt_command: {e}")

    mqtt_client.set_command_callback(handle_command)

    try:
        logging.info(f"New connection from {websocket.remote_address}")
        await charge_point.start()
    except Exception as e:
        logging.exception(f"Connection error: {e}")
    finally:
        logging.info(f"Connection closed for {websocket.remote_address}")

async def main():
    start_server = websockets.serve(
        on_connect,
        config["ocpp"]["host"],
        config["ocpp"]["port"],
        subprotocols=['ocpp1.6']
    )
    server = await start_server
    logging.info(f"OCPP server started on {config['ocpp']['host']}:{config['ocpp']['port']}")
    global main_loop
    main_loop = asyncio.get_running_loop()
    async def loop_alive():
        while True:
            logging.debug("Main event loop is alive.")
            await asyncio.sleep(10)
    asyncio.create_task(loop_alive())
    await server.wait_closed()  # Keep server running

# Windows requires this policy for Python 3.8+
if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())