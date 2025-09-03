# FH_CHARGE-OCPP-server

A Python-based OCPP 1.6 server for managing and monitoring Futurehome EV charger, with MQTT integration for Home Assistant.

## Features
- OCPP 1.6 WebSocket server for EV charger communication
- MQTT integration for control and monitoring
- Home Assistant MQTT Discovery support
- Configurable logging to file and console
- Modular handler for charger logic (`evcharger_handler.py`)
- Graceful error handling and robust startup

## Requirements
- Python 3.12+
- MQTT broker (e.g., Mosquitto)


## Setup
1. **Clone the repository:**
   ```sh
   git clone <your-repo-url>
   cd FH_CHARGE-OCPP-server
   ```
2. **Create and activate a virtual environment:**
   ```sh
   python -m venv venv
   venv\Scripts\activate  # On Windows
   # or
   source venv/bin/activate  # On Linux/Mac
   ```
3. **Install dependencies:**
   ```sh
   pip install -r requirements.txt
   ```
4. **Configure the server:**
   - Edit `config/config.json` to match your environment (MQTT, OCPP, logging, etc).

## Usage
Start the server with:
```sh
python server.py
```

- The server will listen for OCPP 1.6 WebSocket connections from EV chargers.
- MQTT topics will be published for Home Assistant discovery and control.
- Logs are written to the file specified in `config/config.json`.

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
- You can control charging, unlock cable, set current limit, and monitor status via Home Assistant.

## Troubleshooting
- Ensure your MQTT broker is running and reachable.
- Check `logs/ocpp_server.log` for errors.
- If `.gitignore` is not working, make sure to untrack files already added to git.

## License
MIT License

---
For more details, see the code and comments in each file.
