import paho.mqtt.client as mqtt
import json
import logging

class MQTTClient:
    def __init__(self, config, event_loop=None):
        self.config = config 
        self.client = mqtt.Client()
        if self.config.get("username") and self.config.get("password"):
            self.client.username_pw_set(self.config["username"], self.config["password"])
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.command_callback = None
        self.event_loop = event_loop
        self.client.connect(self.config["broker"], self.config["port"])
        self.client.loop_start()

    def set_command_callback(self, callback):
        self.command_callback = callback

    def subscribe_control_topics(self, device_id):
        for topic in [
            f"suspend_{device_id}/set",
            f"unlock_cable_{device_id}/press",
            f"current_limit_{device_id}/set",
            f"availability_{device_id}/set"
        ]:
            self.client.subscribe(f"ocpp/{topic}")

    def on_message(self, client, userdata, msg):
        if self.command_callback:
            topic = msg.topic.replace(f"ocpp/", "")
            payload = msg.payload.decode()
            self.command_callback(topic, payload)

    def on_connect(self, client, userdata, flags, rc):
        logging.info(f"Connected to MQTT broker with result code {rc}")

    def on_disconnect(self, client, userdata, rc):
        logging.warning("Disconnected from MQTT broker")

    def publish(self, topic, payload):
        logging.debug(f"Publishing {payload} to {topic}")
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload)
        self.client.publish(topic, payload, retain=True)
