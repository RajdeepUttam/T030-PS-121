import csv
from parser import load_csv
from runway import RunwayManager
from gate_manager import GateManager
from task_scheduler import TaskScheduler


def to_bool(value):
    """Convert CSV boolean values into Python booleans."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes")


def main():
    print("Loading CSV files...")
    flights = load_csv("data/flights.csv")
    stands = load_csv("data/stands.csv")
    aircraft_types = load_csv("data/aircraft_types.csv")

    # 1. Map aircraft_type to size_code (e.g., A320 -> C)
    size_map = {row["aircraft_type"].strip(): row["size_code"].strip() for row in aircraft_types}
    
    # 2. Clean up flights and separate arrivals/departures
    arrivals = []
    departures = []
    
    for f in flights:
        f["international"] = to_bool(f["international"])
        f["aircraft_size"] = size_map.get(f["aircraft_type"].strip(), "C")
        f["rotation_id"] = f["rotation_id"].strip()
        
        if f["direction"].strip() == "ARR":
            arrivals.append(f)
        else:
            departures.append(f)
            
    # 3. Link Arrivals and Departures into Rotations for the Gate Manager
    rotation_map = {}
    for d in departures:
        rotation_map[d["rotation_id"]] = d
        
    gate_flights = []
    for a in arrivals:
        dep = rotation_map.get(a["rotation_id"])
        if dep:
            combined = {
                "flight_id": a["flight_id"],
                "rotation_id": a["rotation_id"],
                "airline_code": a["airline_code"].strip(),
                "international": a["international"],
                "aircraft_type": a["aircraft_size"],
                "scheduled_ts": a["scheduled_ts"],
                "departure_ts": dep["scheduled_ts"]
            }
            gate_flights.append(combined)

    # 4. Runway Allocation (Processes ALL 120 movements)
    print("Allocating Runway Slots...")
    runway_mgr = RunwayManager()
    
    for f in flights:
        f["is_delayed_over_30"] = to_bool(f.get("is_delayed_over_30", False))
        
    runway_results = runway_mgr.allocate_batch(flights)

    # 5. Gate Allocation (Processes the 60 linked rotations)
    print("Allocating Gates...")
    adjacency_list = []
    with open("data/gate_adjacency.csv", "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            adjacency_list.append((row["gate_id"].strip(), row["adjacent_gate_id"].strip()))

    gate_mgr = GateManager(adjacency_list)
    gate_results = gate_mgr.assign_gates(gate_flights, stands)

    # 6. Task Scheduler (BR-06)
    print("Running Task Scheduler...")
    teams = load_csv("data/service_teams.csv")
    task_durations = load_csv("data/task_durations.csv")
    
    scheduler = TaskScheduler(teams, task_durations)
    scheduled_tasks = scheduler.schedule_tasks(gate_flights)
    print(f"Task scheduling completed. Generated {len(scheduled_tasks)} tasks.")

    # 7. Print the first 5 results to verify
    print("\nFIRST 5 FLIGHT ALLOCATIONS")
    print("-" * 75)
    for i in range(5):
        if i < len(runway_results) and i < len(gate_results):
            r = runway_results[i]
            g = gate_results[i]
            print(f"Flight ID: {r['flight_id']} | Direction: {r['direction']} | Allocated Bin: {r.get('allocated_bin')} | Assigned Stand: {g.get('assigned_stand')}")
    print("-" * 75)

if __name__ == "__main__":
    main()