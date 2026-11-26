#!/usr/bin/env python3
"""
Launcher for Airport Operations Control Centre (PS-121) Dashboard.
Run:
    python3 app.py [port]
"""

import sys
import os

# Add src to sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from server import run_server

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    run_server(port)
