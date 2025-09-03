import logging
import json
from datetime import datetime
from ocpp.v16 import ChargePoint as cp
from ocpp.v16 import call_result
from ocpp.v16 import call
from ocpp.messages import Call
import uuid
from ocpp.routing import on
import traceback
from datetime import datetime, timezone
import asyncio



class EVChargePoint(cp):


    def __init__(self, id, websocket, mqtt_client, config):
        super().__init__(id, websocket)
        self.mqtt_client = mqtt_client
        self.status = "init"  # Default initial status
        self.idTag = "it's ok"
        self.current_transaction_id = None
        self.config = config
        self.minimum_current_ev = config["ev"]["min_current"]
        self.maximum_current_charger = 32  # Assuming a max current of 32A for the charger
        self.maximum_current_now = 16  # Default selected max current, set by HA 
        self.last_charging_start = None
        
    def publish_last_charging_start_sensor(self):
        """
        Publish Home Assistant MQTT discovery and state for last_charging_start as a sensor.
        """
        device_id = self.id
        unique_id = f"{device_id}_last_charging_start"
        config_topic = f"homeassistant/sensor/{unique_id}/config"
        state_topic = f"ocpp/last_charging_start_{device_id}"
        config_payload = {
            "name": f"{device_id} Last Charging Start",
            "state_topic": state_topic,
            "unique_id": unique_id,
            "device": {
                "identifiers": [device_id],
                "name": device_id,
                "manufacturer": "OCPP Charger"
            },
            "icon": "mdi:clock-start",
            "device_class": "timestamp"
        }
        self.mqtt_client.publish(config_topic, json.dumps(config_payload))
        # Publish initial state if available
        if self.last_charging_start:
            self.mqtt_client.publish(state_topic, self.last_charging_start)
    def publish_control_discovery(self):

        """
        Publish MQTT discovery configs for control entities: suspend/resume, lock/unlock cable, set current limit.
        """
        device_id = self.id

        # Availability Control (switch)
        availability_config = {
            "name": f"{device_id} Availability",
            "command_topic": f"ocpp/availability_{device_id}/set",
            "state_topic": f"ocpp/availability_{device_id}/state",
            "unique_id": f"availability_{device_id}",
            "device": {
                "identifiers": [device_id],
                "name": device_id,
                "manufacturer": "OCPP Charger"
            },
            "icon": "mdi:power-settings"
        }
        self.mqtt_client.publish(f"homeassistant/switch/availability_{device_id}/config", json.dumps(availability_config))
        self.mqtt_client.publish(f"ocpp/availability_{device_id}/state", "ON")
        # Suspend/Resume Charging (switch)
        suspend_config = {
            "name": f"{device_id} Suspend Charging",
            "command_topic": f"ocpp/suspend_{device_id}/set",
            "state_topic": f"ocpp/suspend_{device_id}/state",
            "unique_id": f"suspend_{device_id}",
            "device": {
                "identifiers": [device_id],
                "name": device_id,
                "manufacturer": "OCPP Charger"
            },
            "icon": "mdi:power"
        }
        # Discovery topic uses homeassistant prefix
        self.mqtt_client.publish(f"homeassistant/switch/suspend_{device_id}/config", json.dumps(suspend_config))
        # State topic uses ocpp prefix
        self.mqtt_client.publish(f"ocpp/suspend_{device_id}/state", False)

        # Unlock Cable (button)
        unlock_button_config = {
            "name": f"{device_id} Unlock Cable",
            "command_topic": f"ocpp/unlock_cable_{device_id}/press",
            "unique_id": f"unlock_cable_{device_id}",
            "device": {
                "identifiers": [device_id],
                "name": device_id,
                "manufacturer": "OCPP Charger"
            },
            "icon": "mdi:lock-open"
        }
        # Discovery topic uses homeassistant/button for a stateless button
        self.mqtt_client.publish(f"homeassistant/button/unlock_cable_{device_id}/config", json.dumps(unlock_button_config))

        # Set Current Limit (number)
        current_config = {
            "name": f"{device_id} Set Current Limit",
            "command_topic": f"ocpp/current_limit_{device_id}/set",
            "state_topic": f"ocpp/current_limit_{device_id}/state",
            "unique_id": f"current_limit_{device_id}",
            "device": {
                "identifiers": [device_id],
                "name": device_id,
                "manufacturer": "OCPP Charger"
            },
            "min": 6,
            "max": 32,
            "step": 1,
            "mode": "box",
            "unit_of_measurement": "A",
            "icon": "mdi:current-ac"
        }
        self.mqtt_client.publish(f"homeassistant/number/current_limit_{device_id}/config", json.dumps(current_config))
        # State topic uses ocpp prefix
        self.mqtt_client.publish(f"ocpp/current_limit_{device_id}/state", 16)
    async def route_message(self, msg):
        try:
            return await super().route_message(msg)
        except NotImplementedError as e:
            # Log the action that was not handled
            import json
            try:
                action = json.loads(msg)[2]
            except Exception:
                action = "Unknown"
            logging.warning(f"{self.id}: No handler registered for OCPP action: {action}")
            raise
    async def handle_mqtt_command(self, topic, payload, config):
        logging.info(f"ENTER handle_mqtt_command: topic={topic}, payload={payload}")
        try:
            device_id = self.id
            writeback = config.get("allow_writeback", False)
            if topic == f"suspend_{device_id}/set":
                if writeback:
                    if payload == "ON":
                        await self.suspend_charging()
                    else:
                        await self.resume_charging()
                else:
                    logging.info("Writeback disabled: suspend charging command ignored.")
            elif topic == f"resume_{device_id}/set":
                if writeback:
                    await self.resume_charging()
                else:
                    logging.info("Writeback disabled: resume charging command ignored.")
            elif topic == f"unlock_cable_{device_id}/press":
                # Button press for unlock cable
                if writeback:
                    await self.unlock_cable()
                else:
                    logging.info("Writeback disabled: unlock cable button command ignored.")
            elif topic == f"availability_{device_id}/set":
                # Toggle availability: ON = Operative, OFF = Inoperative
                if writeback:
                    if payload == "ON":
                        await self.change_availability("Operative")
                        self.mqtt_client.publish(f"ocpp/availability_{device_id}/state", "ON")
                    else:
                        await self.change_availability("Inoperative")
                        self.mqtt_client.publish(f"ocpp/availability_{device_id}/state", "OFF")
                else:
                    logging.info("Writeback disabled: availability command ignored.")
            elif topic == f"current_limit_{device_id}/set":
                value = int(payload)
                await self.set_current_limit(value)
        except Exception as e:
            logging.exception(f"Exception in handle_mqtt_command: {e}")

    # OCPP command stubs (implement real OCPP calls as needed)
    async def RemoteStopTransaction(self, override_check=False):
        logging.info(f"{self.id}: Suspending charging")
        if (self.status in ["Charging", "SuspendedEV", "init"] and self.current_transaction_id is not None) or override_check:
            # Send OCPP command to suspend charging (RemoteStopTransaction requires transactionId)
            if hasattr(self, "current_transaction_id"):
                msg = Call(
                    unique_id=str(uuid.uuid4()),
                    action="RemoteStopTransaction",
                    payload={"transactionId": self.current_transaction_id}
                )
                await self._send(msg.to_json())
                logging.info(f"{self.id}: Suspend charging OCPP message sent (transactionId={self.current_transaction_id})")
            else:
                logging.error(f"{self.id}: No current_transaction_id set, cannot send RemoteStopTransaction!")

        else:
            logging.info(f"{self.id}: Suspend charging command ignored (status={self.status}, current_transaction_id={self.current_transaction_id})")

    # Suspend charging by applying charging profile
    async def suspend_charging(self):
        # Function that will pause the charging
        logging.info(f"{self.id}: Suspending charging")
        await self.set_charging_profile(0)

    async def resume_charging(self):
        logging.info(f"{self.id}: Resuming charging")
        await self.set_charging_profile(self.maximum_current_now)



    async def unlock_cable(self,test = False):
        #"only allow if status is one not charging"
        if self.status not in ["Charging","SuspendedEV"]:
            logging.info(f"{self.id}: Unlocking cable (sending OCPP UnlockConnector command)")
            msg = Call(
                unique_id=str(uuid.uuid4()),
                action="UnlockConnector",
                payload={"connectorId": 1}
        )
        await self._send(msg.to_json())
        logging.info(f"{self.id}: Unlock cable OCPP message sent")

    async def change_availability(self, AvailabilityType):
        logging.info(f"{self.id}: Changing availability (sending OCPP ChangeAvailability command)")
        msg = Call(
            unique_id=str(uuid.uuid4()),
            action="ChangeAvailability",
            payload={"connectorId": 0, "type": AvailabilityType}
        )
        response = await self._send(msg.to_json())
        logging.info(f"{self.id}: ChangeAvailability response: {response}")
        # Optionally, check if response is an error and log it
        if isinstance(response, dict) and response.get("errorCode"):
            logging.error(f"{self.id}: ChangeAvailability error: {response}")

    async def get_configuration(self):
        logging.info(f"{self.id}: Getting configuration (sending OCPP GetConfiguration command)")
        msg = Call(
            unique_id=str(uuid.uuid4()),
            action="GetConfiguration",
            payload={}
        )
        response = await self._send(msg.to_json())
        logging.info(f"{self.id}: GetConfiguration response: {response}")

    def create_schedule(self, currentLimit):
        # Function that will create a one-item schedule to limit charging current or pause charging
        logging.info(f"{self.id}: Creating charging schedule")
        #make sure currentLimit is within boundaries
        if currentLimit < 0 or currentLimit > self.maximum_current_charger:
            logging.error(f"{self.id}: Invalid current limit {currentLimit}, must be between 0 and {self.maximum_current_charger}")
            currentLimit = self.maximum_current_now
        
        #Check if current is larger than 0 and less than ev min current
        if currentLimit > 0 and currentLimit < self.minimum_current_ev:
            currentLimit = self.minimum_current_ev

        # Create a schedule with the adjusted current limit
        schedule = [
            {"startPeriod": 0, "limit": currentLimit},
            {"startPeriod": 86400, "limit": self.maximum_current_now}
        ]
        
        

        return schedule

    async def set_charging_profile(self, current_limit):
        logging.info(f"{self.id}: Setting charging profile (sending OCPP SetChargingProfile command)")
        # Simple test: pause for 5 minutes, then allow full current
        schedule = self.create_schedule(current_limit)
        # Build a schedule starting at midnight UTC for 24 hours
        start_of_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat().replace('+00:00', 'Z')
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
        test_profile = {
            "chargingProfileId": 1,
            "stackLevel": 1000,
            "chargingProfilePurpose": "TxProfile",  # applies to current transaction
            "chargingProfileKind": "Absolute",
            "chargingSchedule": {
                "startSchedule": now,
                "chargingRateUnit": "A",
                "chargingSchedulePeriod": schedule
            }
        }
        msg = Call(
            unique_id=str(uuid.uuid4()),
            action="SetChargingProfile",
            payload={
                "connectorId": 1,  # must match your actual connector
                "csChargingProfiles": test_profile
            }
        )
        response = await self._send(msg.to_json())
        logging.info(f"{self.id}: SetChargingProfile response: {response}")


   
    async def set_current_limit(self, value):
        logging.info(f"{self.id}: Setting current limit to {value}A ")
        self.maximum_current_now = value
        
        # Update the charging profile with the new current limit
        if self.status == "Charging":
            await self.set_charging_profile(self.maximum_current_now)

        
        # Publish updated state to HA
        device_id = self.id
        self.mqtt_client.publish(f"ocpp/current_limit_{device_id}/state", value)        


    def zero_metrics(self):
        # When charging is in state SuspendedEV
        device_id = self.id
        # Zero out only the exact topics required by user
        zero_topics = [
            f"ocpp/meter_{device_id}_voltage_l1_outlet",
            f"ocpp/meter_{device_id}_voltage_l2_outlet",
            f"ocpp/meter_{device_id}_voltage_l3_outlet",
            f"ocpp/meter_{device_id}_current_import_l1_outlet",
            f"ocpp/meter_{device_id}_current_import_l2_outlet",
            f"ocpp/meter_{device_id}_current_import_l3_outlet",
            f"ocpp/meter_{device_id}_power_active_import_outlet",
            f"ocpp/meter_{device_id}_current_offered_outlet"
        ]
        for topic in zero_topics:
            self.mqtt_client.publish(topic, 0)
        logging.info(f"{self.id}: Published 0 for all required meter topics due to suspend.")


    @on('StartTransaction')
    # charging session is started
    async def on_start_transaction(self, connector_id, id_tag, meter_start, timestamp, **kwargs):
        logging.info(f"{self.id}: StartTransaction received: connector_id={connector_id}, id_tag={id_tag}, meter_start={meter_start}, timestamp={timestamp}, extra={kwargs}")
        # Generate a unique transaction id per session
        self.current_transaction_id = int(datetime.now(timezone.utc).timestamp())
        # record last charging start time in HA friendly format
        self.last_charging_start = datetime.now(timezone.utc).isoformat()
        # Publish to MQTT sensor
        self.mqtt_client.publish(f"ocpp/last_charging_start_{self.id}", self.last_charging_start)
        # Persist the transaction ID
        self.persist_transaction_id()
        response = call_result.StartTransaction(
            transaction_id=self.current_transaction_id,
            # always accepted
            id_tag_info={
                "status": "Accepted"
            }
        )
        logging.info(f"{self.id}: StartTransaction response: {response}")

        #sleep 5 seconds and set charging profile
        await asyncio.sleep(5)
        await self.set_charging_profile(self.maximum_current_now)   
        return response

    @on("StopTransaction")
    async def on_stop_transaction(self, transaction_id, meter_stop, timestamp, **kwargs):
        logging.info(f"{self.id}: StopTransaction received: transaction_id={transaction_id}, meter_stop={meter_stop}, timestamp={timestamp}, extra={kwargs}")

        # Persist the transaction ID
        self.persist_transaction_id()

        response = call_result.StopTransaction(
            id_tag_info={
                "status": "Accepted"
            }
        )
        logging.info(f"{self.id}: StopTransaction response: {response}")
        return response

    async def send_status(self, status):
        """
        Publish charging status to MQTT and Home Assistant discovery.
        """
        #update status
        self.status = status
        device_id = self.id
        state_topic = f"ocpp/status_{device_id}"
        unique_id = f"{device_id}_status"
        config_topic = f"homeassistant/sensor/{unique_id}/config"
        config_payload = {
            "name": f"{device_id} Status",
            "state_topic": state_topic,
            "unique_id": unique_id,
            "device": {
                "identifiers": [device_id],
                "name": device_id,
                "manufacturer": "OCPP Charger"
            },
            "icon": "mdi:ev-station",
            "force_update": True
        }
        self.mqtt_client.publish(config_topic, json.dumps(config_payload))
        self.mqtt_client.publish(state_topic, status)
        logging.debug(f"Published MQTT status: {status} to {state_topic} (discovery: {config_topic})")

    #persisting transactionID
    def persist_transaction_id(self):
        with open("persist.json", "w") as f:
            json.dump({"current_transaction_id": self.current_transaction_id}, f)

    def load_persisted_transaction_id(self):
        try:
            with open("persist.json", "r") as f:
                data = json.load(f)
                self.current_transaction_id = data.get("current_transaction_id", None)
        except FileNotFoundError:
            self.current_transaction_id = None
        except json.JSONDecodeError:
            self.current_transaction_id = None

    # ----------------------------
    # OCPP Handlers
    # ----------------------------




    @on("BootNotification")
    async def on_boot_notification(self, charge_point_vendor, charge_point_model, **kwargs):
        logging.info(
            f"{self.id}: BootNotification received "
            f"(vendor={charge_point_vendor}, model={charge_point_model}, payload={kwargs})"
        )

        try:
            await self.send_status("Booted")

            response = call_result.BootNotification(
                current_time=datetime.now(timezone.utc).isoformat(),
                interval=30,
                status="Accepted"
            )
            logging.info(f"{self.id}: BootNotification response: {response}")



            return response

        except Exception as e:
            logging.exception(f"Exception in on_boot_notification: {e}")
            raise


    @on("Heartbeat")
    async def on_heartbeat(self):
        now = datetime.now(timezone.utc).isoformat()
        logging.debug(f"{self.id}: Heartbeat received")
        # Home Assistant MQTT Discovery for heartbeat
        device_id = self.id
        sensor_name = "heartbeat"
        state_topic = f"ocpp/heartbeat_{device_id}"
        unique_id = f"{device_id}_heartbeat"
        config_topic = f"homeassistant/sensor/{unique_id}/config"
        config_payload = {
            "name": f"{device_id} Heartbeat",
            "state_topic": state_topic,
            "unique_id": unique_id,
            "device": {
                "identifiers": [device_id],
                "name": device_id,
                "manufacturer": "OCPP Charger"
            },
            "icon": "mdi:heart-pulse",
            "force_update": True
        }
        self.mqtt_client.publish(config_topic, json.dumps(config_payload))
        # Publish heartbeat value to the correct state topic
        self.mqtt_client.publish(state_topic, now)
        logging.debug(f"Published MQTT heartbeat: heartbeat {now}")
        response = call_result.Heartbeat(current_time=now)
        logging.debug(f"{self.id}: Heartbeat response: {response}")
        return response

    @on("MeterValues")
    async def on_meter_values(self, connector_id, meter_value, **kwargs):
        logging.info(f"{self.id}: MeterValues received: connector_id={connector_id}, meter_value={meter_value}, extra={kwargs}")

        #if metrics is received, charging is ongoing. Check if transactionID is None, in that case read from file
        if not self.current_transaction_id:
            self.load_persisted_transaction_id()
        #set status to Charging
        self.status = "Charging"

        try:
            # Home Assistant MQTT Discovery and value publishing
            device_id = self.id
            for entry in meter_value:
                timestamp = entry.get("timestamp")
                for sv in entry.get("sampled_value", []):
                    measurand = sv.get("measurand", "unknown").lower().replace(".", "_").replace(" ", "_")
                    phase = sv.get("phase")
                    location = sv.get("location")
                    unit = sv.get("unit", "")
                    value = sv.get("value")
                    # Build a unique sensor name
                    sensor_name = f"{measurand}"
                    if phase:
                        sensor_name += f"_{phase.lower()}"
                    if location:
                        sensor_name += f"_{location.lower()}"
                    sensor_name = sensor_name.replace(" ", "_")
                    state_topic = f"ocpp/meter_{device_id}_{sensor_name}"
                    # Publish discovery config
                    unique_id = f"{device_id}_{sensor_name}"
                    config_topic = f"homeassistant/sensor/{unique_id}/config"
                    config_payload = {
                        "name": f"{device_id} {sensor_name}",
                        "state_topic": state_topic,
                        "unique_id": unique_id,
                        "device": {
                            "identifiers": [device_id],
                            "name": device_id,
                            "manufacturer": "OCPP Charger"
                        },
                        "unit_of_measurement": unit,
                        "device_class": self._guess_device_class(measurand),
                        "state_class": self._guess_state_class(measurand),
                        "force_update": True
                    }
                    self.mqtt_client.publish(config_topic, json.dumps(config_payload))
                    # Publish value
                    self.mqtt_client.publish(state_topic, value)
                    logging.debug(f"Published {sensor_name}: {value} to {state_topic} (discovery: {config_topic})")
            response = call_result.MeterValues()
            logging.info(f"{self.id}: MeterValues response: {response}")
            return response
        except Exception as e:
            logging.exception(f"Exception in on_meter_values: {e}")
            raise

    def _guess_device_class(self, measurand):
        # Map OCPP measurands to Home Assistant device classes
        mapping = {
            "voltage": "voltage",
            "current_import": "current",
            "current_offered": "current",
            "power_active_import": "power",
            "energy_active_import_register": "energy",
            "frequency": "frequency",
            "temperature": "temperature",
            "soc": "battery",
        }
        return mapping.get(measurand.lower(), None)

    def _guess_state_class(self, measurand):
        # Map OCPP measurands to Home Assistant state classes
        if "energy" in measurand.lower():
            return "total_increasing"
        if "power" in measurand.lower():
            return "measurement"
        if "voltage" in measurand.lower():
            return "measurement"
        if "current" in measurand.lower():
            return "measurement"
        return None

    @on('StatusNotification')
    async def on_status_notification(self, connector_id, status, error_code, **kwargs):
        logging.info(f"{self.id}: StatusNotification received: connector={connector_id}, status={status}, error_code={error_code}, extra={kwargs}")
        try:
            if status in ["SuspendedEV","SuspendedEVSE","Inoperative", "Finishing","Available"]:
                self.zero_metrics()

            await self.send_status(status)
            response = call_result.StatusNotification()
            logging.info(f"{self.id}: StatusNotification response: {response}")
            return response
        except Exception as e:
            logging.exception(f"Exception in on_status_notification: {e}")
            raise