import json
import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs

# Ensure src/ is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(BASE_DIR, "src")
WEB_DIR = os.path.join(BASE_DIR, "web")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from simulation_engine import AirportSimulationEngine

# Global singleton simulation engine
ENGINE = AirportSimulationEngine(data_dir=os.path.join(BASE_DIR, "data"))


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class AirportDashboardHandler(SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def _send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/overview":
            self._send_json(ENGINE.get_overview_kpis())
        elif path == "/api/flights":
            self._send_json(ENGINE.flights)
        elif path == "/api/runway":
            self._send_json(ENGINE.get_runway_data())
        elif path == "/api/gates":
            self._send_json(ENGINE.get_gate_timeline_data())
        elif path == "/api/rotations":
            self._send_json(ENGINE.rotations)
        elif path == "/api/commands":
            self._send_json({
                "commands": ENGINE.commands,
                "current_index": ENGINE.command_index
            })
        elif path == "/api/charges":
            self._send_json({
                "summary": ENGINE.airline_charges,
                "rotations": [
                    {
                        "rotation_id": r["rotation_id"],
                        "airline_code": r["airline_code"],
                        "aircraft_type": r["aircraft_type"],
                        "size_code": r["size_code"],
                        "stand_id": r.get("stand_id"),
                        "charges": r.get("charges", {})
                    }
                    for r in ENGINE.rotations
                ]
            })
        elif path == "/api/log":
            self._send_json(ENGINE.execution_log)
        elif path == "/api/surveillance":
            self._send_json(ENGINE.get_surveillance_telemetry())
        else:
            # Fall back to serving static files from web/
            if path == "/":
                self.path = "/index.html"
            return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Read JSON body
        length = int(self.headers.get("Content-Length", 0))
        body = {}
        if length > 0:
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception:
                body = {}

        if path == "/api/step":
            res = ENGINE.step_next_command()
            self._send_json(res)
        elif path == "/api/step-all":
            logs = ENGINE.execute_all_commands()
            self._send_json({"done": True, "executed_logs": logs})
        elif path == "/api/reset":
            ENGINE.reset()
            self._send_json({"status": "RESET_SUCCESS", "overview": ENGINE.get_overview_kpis()})
        elif path == "/api/custom-event":
            # body: {"action": "DELAY", "args": ["FLT-0017", "2026-10-14 09:00:00", "AIRLINE"]}
            action = body.get("action")
            args = body.get("args", [])
            if not action:
                self._send_json({"error": "Missing action"}, status=400)
                return
            log_res = ENGINE.execute_command({"action": action, "args": args})
            self._send_json({"status": "EVENT_EXECUTED", "log": log_res, "overview": ENGINE.get_overview_kpis()})
        elif path == "/api/calculate-custom":
            res = ENGINE.simulate_custom_flight(body)
            self._send_json(res)
        else:
            self.send_error(404, "Endpoint not found")


def run_server(port=8000):
    os.makedirs(WEB_DIR, exist_ok=True)
    server_address = ("", port)
    httpd = ThreadedHTTPServer(server_address, AirportDashboardHandler)
    print(f"============================================================")
    print(f"✈️  Airport Operations Control Dashboard running at:")
    print(f"    http://localhost:{port}")
    print(f"============================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    run_server(port)
