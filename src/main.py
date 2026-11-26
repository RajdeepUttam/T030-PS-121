import csv
from parser import load_csv
from runway import RunwayManager
from gate_manager import GateManager
from task_scheduler import TaskScheduler
from outputs import write_gate_plan, write_task_schedule, write_charges
from charges import calculate_charges


def to_bool(value):
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
        f["aircraft_type"] = size_map.get(f["aircraft_type"].strip(), "C")
        f["rotation_id"] = f["rotation_id"].strip()
        
        if f["direction"].strip() == "ARR":
            arrivals.append(f)
        else:
            departures.append(f)
            
    # 3. Link Arrivals and Departures into Rotations for the Gate Manager
    rotation_map = {d["rotation_id"]: d for d in departures}
        
    gate_flights = []
    for a in arrivals:
        dep = rotation_map.get(a["rotation_id"])
        if dep:
            combined = {
                "flight_id": a["flight_id"],
                "rotation_id": a["rotation_id"],
                "airline_code": a["airline_code"].strip(),
                "international": a["international"],
                "aircraft_type": a["aircraft_type"],
                "scheduled_ts": a["scheduled_ts"],
                "departure_ts": dep["scheduled_ts"]
            }
            gate_flights.append(combined)

    # 4. Runway Allocation
    print("Allocating Runway Slots...")
    runway_mgr = RunwayManager()
    for f in flights:
        f["is_delayed_over_30"] = to_bool(f.get("is_delayed_over_30", False))
    runway_results = runway_mgr.allocate_batch(flights)
    
    # Map runway bins
    allocated_bin_map = {f["flight_id"]: f["allocated_bin"] for f in runway_results}

    # 5. Gate Allocation
    print("Allocating Gates...")
    adjacency_list = []
    with open("data/gate_adjacency.csv", "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            adjacency_list.append((row["gate_id"].strip(), row["adjacent_gate_id"].strip()))

    gate_mgr = GateManager(adjacency_list)
    gate_results = gate_mgr.assign_gates(gate_flights, stands)

    # 6. Task Scheduler
    print("Running Task Scheduler...")
    teams = load_csv("data/service_teams.csv")
    task_durations = load_csv("data/task_durations.csv")
    
    scheduler = TaskScheduler(teams, task_durations)
    scheduled_tasks = scheduler.schedule_tasks(gate_flights)
    print(f"Task scheduling completed. Generated {len(scheduled_tasks)} tasks.")

    # 7. Combine Runway and Gate Results for Output
    # Since gate_results updates gate_flights with assigned_stand and mode, we use that.
    gate_data_map = {f["rotation_id"]: f for f in gate_results}
    
    final_flights = []
    for f in flights:
        result = f.copy()
        # Add runway bin
        result["allocated_bin"] = allocated_bin_map.get(f["flight_id"])
        
        # Add gate data (if it exists for this rotation)
        g_info = gate_data_map.get(f["rotation_id"], {})
        result["assigned_stand"] = g_info.get("assigned_stand", "")
        result["occupancy_start"] = g_info.get("occupancy_start", "")
        result["occupancy_end"] = g_info.get("occupancy_end", "")
        result["buffer_end"] = g_info.get("buffer_end", "")
        result["mode"] = g_info.get("mode", "")
        result["reason"] = g_info.get("reason", "")
        
        final_flights.append(result)

    # Print verify
    print("\nFIRST 5 FLIGHT ALLOCATIONS")
    print("-" * 75)
    for f in final_flights[:5]:
        print(f"Flight ID: {f['flight_id']} | Direction: {f['direction']} | Allocated Bin: {f['allocated_bin']} | Assigned Stand: {f['assigned_stand']}")
    print("-" * 75)


    # =====================================================
    # STEP 7.5: CALCULATE CHARGES
    # =====================================================
    print("Calculating charges...")
    charge_data = calculate_charges(final_flights, stands)


    # 8. Generate Outputs
    print("\nGenerating Output CSVs...")
    write_gate_plan("gate_plan.csv", final_flights)
    write_task_schedule("task_schedule.csv", scheduled_tasks)
    print("CSV files generated successfully! Check your folder.")
    # 3. Charges
    write_charges("charges.csv", charge_data)

if __name__ == "__main__":
    main()