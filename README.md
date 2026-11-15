# AERO-OPS 121: Airport Operations Control Centre (PS-121)

A responsive, full-featured **Airport Operations Control Centre (AOCC)** simulation dashboard and resource optimization engine. It automates flight rotation linking, runway 15-minute slot management, gate/stand allocation, ground turnaround task scheduling, real-time disruption handling, and aeronautical billing calculations.

---

## 🚀 Quick Start: Launch the Dashboard

Launch the interactive web dashboard with zero external dependencies (built on Python standard library):

```bash
python3 app.py
```
*(By default runs on port `8000`. You can specify a custom port, e.g., `python3 app.py 8080`)*

Then open your browser to:
👉 **`http://localhost:8000`**

---

## 🖥️ Dashboard Features & Capabilities

The dashboard provides 8 specialized operational modules:

1. **📊 Command Center (Overview)**
   - Live KPI cards: Total Flights, Active Movements, Delays, Cancellations, Gate Occupancy %, Runway Peak Load, and Accrued Revenue.
   - 15-Minute Runway Capacity bar chart (movements vs 12 capacity limit).
   - Airline charge distribution donut chart.
   - Operations event stream ticker.

2. **✈️ Flight Operations Board**
   - Filterable & searchable schedule of all 120+ flights.
   - Filter by Arrival/Departure, Airline, Status (On-time, Delayed, Cancelled, Diverted).
   - Interactive **Flight Dossier Modal** with aircraft specs, assigned stand, runway slot, and fee details.

3. **🛫 Runway Slots (15-Minute Bins)**
   - Visual capacity grid for all 96 daily 15-minute intervals.
   - Color-coded saturation levels (Normal, High, Saturated/Full).
   - Prioritization enforcement: Delayed departures (>30m) receive Priority 0; arrivals pushed before departures.

4. **🚪 Gates & Stand Matrix**
   - Stand status across Pier DOM_A (G01–G08), Pier DOM_B (G09–G12), Pier INTL (G13–G18), and Remote Stands (R01–R06).
   - Occupancy timeline with -5m arrival buffer and +25m departure buffer.
   - Visual badges for aircraft size compatibility (C vs E), aerobridge availability, swing gates, and walking distances.

5. **⏱️ Turnaround Task Scheduler**
   - Turnaround workflow viewer for all 60 rotations (`ROT-001` to `ROT-060`).
   - Sequence of ground operations: Deboarding → Cleaning, Fuelling, Catering, Security → Boarding.
   - Roster of 10 specialized Ground Handling Service Teams (`TEAM-01` to `TEAM-10`).

6. **⚡ Operations Simulator & Disruption Injector**
   - Step through or auto-run the 98 chronological operational commands from `data/commands.txt`.
   - **Custom Event Trigger**: Inject custom delays, early arrivals, cancellations, gauge swaps, or emergency diversions-in with live re-calculation.

7. **💰 Billing & What-If Sandbox**
   - Airline fee summaries for Kaveri Air (KV), Deccan Wings (DW), SkyBridge (SB), and Nilgiri Express (NX).
   - **Interactive What-If Calculator**: Test hypothetical ground stay times, stand types (Contact vs Remote), aircraft gauge (C vs E), and calculate exact parking, aerobridge, peak surcharge, and delay penalties.

8. **🧪 Custom Flight Slot & Stand Planner**
   - Input hypothetical flight specs (aircraft type, schedule, airline, international sector).
   - Evaluates runway slot availability, recommends optimal gate, schedules turnaround tasks, and projects charges.

---

## 📁 Repository Structure

```
.
├── app.py                     # One-click dashboard launcher
├── README.md                  # Project documentation
├── requirements.txt           # Test requirements (pytest)
├── data/                      # Airport master CSV data & commands
│   ├── aircraft_types.csv     # Aircraft gauge and seat capacity
│   ├── airlines.csv           # Airline profiles & preferred gates
│   ├── charge_rates.csv       # Parking, aerobridge, and peak tariff rules
│   ├── commands.txt           # 98 sequential operations day events
│   ├── flights.csv            # Flight schedules & rotation pairings
│   ├── gate_adjacency.csv     # Gate conflict & adjacency matrix
│   ├── runway_capacity.csv    # 96 15-minute runway capacity slots
│   ├── service_teams.csv      # 10 ground handling service teams
│   ├── stands.csv             # 24 contact and remote stands
│   └── task_durations.csv     # Ground turnaround task definitions
├── src/
│   ├── gate_manager.py        # Gate & stand allocation engine
│   ├── main.py                # Command-line simulation runner
│   ├── outputs.py             # Command parser and CSV export
│   ├── parser.py              # CSV ingestion utility
│   ├── runway.py              # Runway capacity & priority slot allocator
│   ├── server.py              # Threaded Python REST API & web server
│   ├── simulation_engine.py   # Integrated simulation & calculation engine
│   └── task_scheduler.py      # Ground handling DAG task scheduler
└── web/
    └── index.html             # Responsive HTML5/Tailwind/Chart.js dashboard
```

---

## 💻 Running the Command-Line Engine

To execute the baseline pipeline without the web interface:

```bash
python3 src/main.py
```
