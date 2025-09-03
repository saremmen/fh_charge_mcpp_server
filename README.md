# FH_CHARGE-OCPP-server

A Python-based OCPP 1.6 server for managing and monitoring Futurehome EV charger, with MQTT integration for Home Assistant.
FUTUREHOMW CHARGE <--> OCCP SERVER <--> HA MQTT integration(ex MOSQUITTO) <--> (autodiscover) HA Object

## Features
- OCPP 1.6 WebSocket server for EV charger communication
- MQTT integration for control and monitoring
- Home Assistant MQTT Discovery support
- Configurable logging to file and console
- Modular handler for charger logic (`evcharger_handler.py`)


## Requirements
- Python 3.12+
- MQTT broker (e.g., Mosquitto)


## Setup
1. Clone repository into docker environment, create container and run 


#Config.json
{
  "ocpp": {
    "host": "0.0.0.0",        // The IP address to bind the OCPP server (0.0.0.0 = all interfaces)
    "port": 9000,             // The port for the OCPP WebSocket server
    "charge_point_id": "FH_CHARGE" // Unique ID for the charge point -name appearing in HA
  },
  "mqtt": {
    "broker": "192.168.200.200", // MQTT broker address
    "port": 1883,               // MQTT broker port
    "username": "mqttuser",       // MQTT username
    "password": "********"      // MQTT password
  },
  "logging": {
    "level": "WARNING",         // Log level for file logging (e.g., INFO, WARNING, ERROR)
    "file": "logs/ocpp_server.log", // Log file path
    "to_console_level": "WARNING"   // Log level for console output
  },
  "ev": {
    "min_current": 6            // Minimum charging current ev (Amps)
  },
  "allow_writeback": true       // Allow control commands from MQTT (set to false for read-only)
}
## File Structure
- `server.py` — Main entry point, starts the OCPP server and MQTT client
- `evcharger_handler.py` — Handles charger logic and OCPP message routing
- `mqtt_client.py` — MQTT client integration
- `config/config.json` — Configuration file
- `logs/ocpp_server.log` — Log output
- `requirements.txt` — Python dependencies
- `Dockerfile` — (Optional) Containerization support

## Home Assistant Integration
- The server publishes MQTT discovery topics for sensors and controls.
- You can control charging (suspend), unlock cable, set current limit (restarts charging with current!= 0), and monitor status via Home Assistant.

## Troubleshooting
- Ensure your MQTT broker is running and reachable.
- Check `logs/ocpp_server.log` for errors.
- If `.gitignore` is not working, make sure to untrack files already added to git.

## License
MIT License

---
For more details, see the code and comments in each file.

<img width="1079" height="1098" alt="image" src="https://github.com/user-attachments/assets/9a24159c-6444-474a-8e01-5724eb83bc70" />

