import csv
import math
import os
from datetime import datetime, timedelta

from parser import load_csv
from runway import RunwayManager
from gate_manager import GateManager
from task_scheduler import TaskScheduler

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

def to_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes")

def parse_dt(val):
    if isinstance(val, datetime):
        return val
    return datetime.strptime(str(val), TIMESTAMP_FORMAT)

def format_dt(dt):
    return dt.strftime(TIMESTAMP_FORMAT)


class AirportSimulationEngine:
    """
    Complete Airport Operations Simulation Engine.
    Handles master data, runway slots, gate allocations, ground turnaround tasks,
    dynamic command executions (delays, diversions, cancellations, swaps),
    and aeronautical charges calculation.
    """

    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
        self.reset()

    def reset(self):
        """Reload all data from scratch and initialize the plan."""
        self.raw_flights = load_csv(os.path.join(self.data_dir, "flights.csv"))
        self.raw_stands = load_csv(os.path.join(self.data_dir, "stands.csv"))
        self.raw_aircraft_types = load_csv(os.path.join(self.data_dir, "aircraft_types.csv"))
        self.raw_airlines = load_csv(os.path.join(self.data_dir, "airlines.csv"))
        self.raw_charge_rates = load_csv(os.path.join(self.data_dir, "charge_rates.csv"))
        self.raw_gate_adjacency = load_csv(os.path.join(self.data_dir, "gate_adjacency.csv"))
        self.raw_runway_capacity = load_csv(os.path.join(self.data_dir, "runway_capacity.csv"))
        self.raw_service_teams = load_csv(os.path.join(self.data_dir, "service_teams.csv"))
        self.raw_task_durations = load_csv(os.path.join(self.data_dir, "task_durations.csv"))

        # Lookups
        self.aircraft_size_map = {
            a["aircraft_type"]: a["size_code"] for a in self.raw_aircraft_types
        }
        self.airlines_map = {
            a["airline_code"]: a for a in self.raw_airlines
        }
        self.charge_rates = {
            c["charge_code"]: float(c["rate"]) for c in self.raw_charge_rates
        }

        # Format stands
        self.stands = []
        for s in self.raw_stands:
            stand = s.copy()
            stand["swing_gate"] = to_bool(stand.get("swing_gate", False))
            stand["aerobridge"] = to_bool(stand.get("aerobridge", False))
            stand["walking_distance_m"] = int(stand.get("walking_distance_m", 0))
            self.stands.append(stand)
        self.stands_map = {s["stand_id"]: s for s in self.stands}

        # Format flights
        self.flights = []
        for f in self.raw_flights:
            flt = f.copy()
            flt["size_code"] = self.aircraft_size_map.get(flt["aircraft_type"], "C")
            flt["aircraft_type_original"] = flt["aircraft_type"]
            flt["international"] = to_bool(flt.get("international", False))
            flt["is_delayed_over_30"] = to_bool(flt.get("is_delayed_over_30", False))
            flt["status"] = "SCHEDULED"
            flt["delay_minutes"] = 0
            flt["delay_reason"] = None
            flt["original_scheduled_ts"] = flt["scheduled_ts"]
            self.flights.append(flt)

        # Parse commands from commands.txt
        self.commands = self._load_commands()
        self.command_index = 0
        self.execution_log = []

        # Run initial allocation
        self.build_plan()

    def _load_commands(self):
        filepath = os.path.join(self.data_dir, "commands.txt")
        cmds = []
        if not os.path.exists(filepath):
            return cmds
        with open(filepath, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("|")
                cmds.append({
                    "id": idx + 1,
                    "raw": line,
                    "action": parts[0],
                    "args": parts[1:]
                })
        return cmds

    def build_plan(self):
        """Execute Runway, Gate, and Task Scheduling."""
        active_flights = [f for f in self.flights if f.get("status") != "CANCELLED"]

        # 1. Runway Allocation
        runway_mgr = RunwayManager()
        # Runway manager requires aircraft_type to be size_code for priority or direction
        for f in active_flights:
            f["aircraft_type"] = f["size_code"]

        allocated = runway_mgr.allocate_batch([f.copy() for f in active_flights])
        bin_lookup = {f["flight_id"]: f["allocated_bin"] for f in allocated}

        for f in self.flights:
            if f.get("status") != "CANCELLED":
                f["allocated_bin"] = bin_lookup.get(f["flight_id"], f["scheduled_ts"])
            else:
                f["allocated_bin"] = None

        # 2. Gate Allocation
        # Link arrival & departures by rotation
        dep_map = {}
        for f in self.flights:
            if f["direction"] == "DEP" and f.get("status") != "CANCELLED":
                dep_map[f["rotation_id"]] = f

        gate_flights = []
        for f in self.flights:
            if f["direction"] == "ARR" and f.get("status") != "CANCELLED":
                rot_id = f["rotation_id"]
                dep = dep_map.get(rot_id)
                linked = f.copy()
                if dep:
                    linked["departure_ts"] = dep["scheduled_ts"]
                else:
                    # If single arrival or diverted in, assume 2 hours turnaround
                    arr_dt = parse_dt(f["scheduled_ts"])
                    linked["departure_ts"] = format_dt(arr_dt + timedelta(hours=2))
                gate_flights.append(linked)

        gate_mgr = GateManager()
        assigned_gate_flights = gate_mgr.assign_gates(gate_flights, self.stands)
        stand_lookup = {f["rotation_id"]: f.get("assigned_stand") for f in assigned_gate_flights}

        for f in self.flights:
            f["assigned_stand"] = stand_lookup.get(f["rotation_id"])

        # Restore original aircraft type representation
        for f in self.flights:
            f["aircraft_type"] = f["aircraft_type_original"]

        # 3. Ground Turnaround Scheduling for all rotations
        self.rotations = self._build_rotations(assigned_gate_flights)
        self._schedule_ground_tasks()

        # 4. Compute Charges
        self.calculate_charges()

    def _build_rotations(self, assigned_gate_flights):
        rot_dict = {}
        for f in self.flights:
            rot_id = f["rotation_id"]
            if rot_id not in rot_dict:
                rot_dict[rot_id] = {
                    "rotation_id": rot_id,
                    "airline_code": f["airline_code"],
                    "airline_name": self.airlines_map.get(f["airline_code"], {}).get("airline_name", f["airline_code"]),
                    "aircraft_type": f["aircraft_type"],
                    "size_code": f["size_code"],
                    "aircraft_reg": f.get("aircraft_reg", "TBD"),
                    "arrival": None,
                    "departure": None,
                    "stand_id": None,
                    "tasks": [],
                    "charges": {}
                }
            if f["direction"] == "ARR":
                rot_dict[rot_id]["arrival"] = f
            elif f["direction"] == "DEP":
                rot_dict[rot_id]["departure"] = f

        for rot_id, rot in rot_dict.items():
            if rot["arrival"]:
                rot["stand_id"] = rot["arrival"].get("assigned_stand")
            elif rot["departure"]:
                rot["stand_id"] = rot["departure"].get("assigned_stand")
        return list(rot_dict.values())

    def _schedule_ground_tasks(self):
        # Prepare task durations
        # Note: Normalize SECURITY_CHECK -> security for TaskScheduler compatibility
        teams = [s.copy() for s in self.raw_service_teams]
        task_durations = []
        for t in self.raw_task_durations:
            t_copy = t.copy()
            if t_copy["task"].strip().upper() == "SECURITY_CHECK":
                t_copy["task"] = "security"
            t_copy["predecessors"] = t_copy.get("predecessors", "").replace("SECURITY_CHECK", "security")
            task_durations.append(t_copy)

        scheduler = TaskScheduler(teams, task_durations)

        # Flights input for TaskScheduler
        sched_input = []
        for rot in self.rotations:
            arr = rot["arrival"]
            if arr and arr.get("status") != "CANCELLED":
                sched_input.append({
                    "rotation_id": rot["rotation_id"],
                    "scheduled_ts": arr["scheduled_ts"],
                    "international": arr["international"]
                })

        try:
            scheduled_tasks = scheduler.schedule_tasks(sched_input)
            task_by_rot = {}
            for t in scheduled_tasks:
                task_by_rot.setdefault(t["rotation_id"], []).append(t)
            for rot in self.rotations:
                rot["tasks"] = task_by_rot.get(rot["rotation_id"], [])
        except Exception as e:
            for rot in self.rotations:
                rot["tasks"] = []

    def calculate_charges(self):
        """
        Calculate parking & aeronautical charges for each rotation and airline.
        Rate specs from charge_rates.csv:
          PARKING_C: 400.00 / 15 min after free period
          PARKING_E: 900.00 / 15 min after free period
          FREE_CONTACT_MIN: 120
          FREE_REMOTE_MIN: 240
          AEROBRIDGE: 2500 per use
          TOW: 6000
          PEAK_SURCHARGE_PCT: 25% (06:00-09:00 & 18:00-21:00)
          DELAY_PENALTY: 10000 / 15 min
        """
        rate_c = self.charge_rates.get("PARKING_C", 400.0)
        rate_e = self.charge_rates.get("PARKING_E", 900.0)
        free_contact = int(self.charge_rates.get("FREE_CONTACT_MIN", 120))
        free_remote = int(self.charge_rates.get("FREE_REMOTE_MIN", 240))
        aerobridge_rate = self.charge_rates.get("AEROBRIDGE", 2500.0)
        delay_penalty_rate = self.charge_rates.get("DELAY_PENALTY", 10000.0)
        peak_pct = self.charge_rates.get("PEAK_SURCHARGE_PCT", 25.0) / 100.0

        airline_summary = {}

        for rot in self.rotations:
            arr = rot["arrival"]
            dep = rot["departure"]
            stand_id = rot.get("stand_id")
            stand = self.stands_map.get(stand_id)
            airline_code = rot["airline_code"]

            if airline_code not in airline_summary:
                airline_summary[airline_code] = {
                    "airline_code": airline_code,
                    "airline_name": self.airlines_map.get(airline_code, {}).get("airline_name", airline_code),
                    "total_rotations": 0,
                    "parking_charges": 0.0,
                    "aerobridge_charges": 0.0,
                    "peak_surcharges": 0.0,
                    "delay_penalties": 0.0,
                    "total_charges": 0.0
                }

            if not arr or not dep or arr.get("status") == "CANCELLED" or dep.get("status") == "CANCELLED":
                rot["charges"] = {"total": 0.0, "details": "Flight cancelled or incomplete"}
                continue

            arr_dt = parse_dt(arr["scheduled_ts"])
            dep_dt = parse_dt(dep["scheduled_ts"])
            duration_min = max(0, int((dep_dt - arr_dt).total_seconds() / 60))

            stand_type = stand["stand_type"] if stand else "CONTACT"
            free_min = free_remote if stand_type == "REMOTE" else free_contact
            billable_min = max(0, duration_min - free_min)
            blocks_15m = math.ceil(billable_min / 15.0) if billable_min > 0 else 0

            rate = rate_e if rot["size_code"] == "E" else rate_c
            parking_fee = blocks_15m * rate

            # Peak Surcharge if arrival or departure in peak hours (06:00-09:00, 18:00-21:00)
            is_peak = (
                (6 <= arr_dt.hour < 9) or (18 <= arr_dt.hour < 21) or
                (6 <= dep_dt.hour < 9) or (18 <= dep_dt.hour < 21)
            )
            peak_fee = (parking_fee * peak_pct) if is_peak else 0.0

            # Aerobridge fee
            aerobridge_fee = aerobridge_rate if (stand and stand.get("aerobridge")) else 0.0

            # Delay penalty if delayed by AIRLINE
            delay_penalty = 0.0
            if dep.get("delay_reason") == "AIRLINE" and dep.get("delay_minutes", 0) > 0:
                delay_blocks = math.ceil(dep["delay_minutes"] / 15.0)
                delay_penalty = delay_blocks * delay_penalty_rate

            total_rot_charge = parking_fee + peak_fee + aerobridge_fee + delay_penalty

            rot["charges"] = {
                "duration_min": duration_min,
                "free_min": free_min,
                "billable_min": billable_min,
                "blocks_15m": blocks_15m,
                "rate_per_block": rate,
                "parking_fee": parking_fee,
                "is_peak": is_peak,
                "peak_fee": peak_fee,
                "aerobridge_fee": aerobridge_fee,
                "delay_penalty": delay_penalty,
                "total": total_rot_charge
            }

            s = airline_summary[airline_code]
            s["total_rotations"] += 1
            s["parking_charges"] += parking_fee
            s["aerobridge_charges"] += aerobridge_fee
            s["peak_surcharges"] += peak_fee
            s["delay_penalties"] += delay_penalty
            s["total_charges"] += total_rot_charge

        self.airline_charges = list(airline_summary.values())

    def execute_command(self, cmd):
        """Execute a single command dictionary and update state."""
        action = cmd["action"]
        args = cmd["args"]
        log_entry = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "action": action,
            "args": args,
            "result": "OK",
            "message": ""
        }

        if action == "BUILD_PLAN":
            self.build_plan()
            log_entry["message"] = f"Full day plan built for {args[0] if args else 'current date'}"

        elif action == "CANCEL":
            # CANCEL|flight_id|timestamp
            flight_id = args[0]
            for f in self.flights:
                if f["flight_id"] == flight_id:
                    f["status"] = "CANCELLED"
                    log_entry["message"] = f"Flight {flight_id} cancelled at {args[1] if len(args) > 1 else 'now'}"
                    break
            self.build_plan()

        elif action == "DELAY":
            # DELAY|flight_id|new_timestamp|reason
            flight_id = args[0]
            new_ts = args[1]
            reason = args[2] if len(args) > 2 else "AIRLINE"
            for f in self.flights:
                if f["flight_id"] == flight_id:
                    orig_dt = parse_dt(f["original_scheduled_ts"])
                    new_dt = parse_dt(new_ts)
                    delay_min = int((new_dt - orig_dt).total_seconds() / 60)
                    f["scheduled_ts"] = new_ts
                    f["delay_minutes"] = max(0, delay_min)
                    f["delay_reason"] = reason
                    f["is_delayed_over_30"] = delay_min > 30
                    f["status"] = "DELAYED"
                    log_entry["message"] = f"Flight {flight_id} delayed by {delay_min}m ({reason}) to {new_ts}"
                    break
            self.build_plan()

        elif action == "EARLY":
            # EARLY|flight_id|new_timestamp
            flight_id = args[0]
            new_ts = args[1]
            for f in self.flights:
                if f["flight_id"] == flight_id:
                    orig_dt = parse_dt(f["original_scheduled_ts"])
                    new_dt = parse_dt(new_ts)
                    early_min = int((orig_dt - new_dt).total_seconds() / 60)
                    f["scheduled_ts"] = new_ts
                    f["status"] = "EARLY"
                    log_entry["message"] = f"Flight {flight_id} arriving {early_min}m early at {new_ts}"
                    break
            self.build_plan()

        elif action == "SWAP":
            # SWAP|rotation_id|new_tail|new_aircraft_type|timestamp
            rot_id = args[0]
            new_tail = args[1]
            new_type = args[2]
            new_size = self.aircraft_size_map.get(new_type, "C")
            for f in self.flights:
                if f["rotation_id"] == rot_id:
                    f["aircraft_reg"] = new_tail
                    f["aircraft_type"] = new_type
                    f["aircraft_type_original"] = new_type
                    f["size_code"] = new_size
            log_entry["message"] = f"Rotation {rot_id} aircraft swapped to {new_tail} ({new_type}, Size {new_size})"
            self.build_plan()

        elif action == "DIVERSION_IN":
            # DIVERSION_IN|div_id|airline|type|tail|timestamp|international
            div_id = args[0]
            airline = args[1]
            ac_type = args[2]
            tail = args[3]
            ts = args[4]
            intl = to_bool(args[5]) if len(args) > 5 else False
            new_flight = {
                "flight_id": f"DIV-{div_id}",
                "rotation_id": f"ROT-DIV-{div_id}",
                "airline_code": airline,
                "flight_no": f"{airline} DVI",
                "direction": "ARR",
                "scheduled_ts": ts,
                "origin_or_destination": "DIVERTED_IN",
                "international": intl,
                "aircraft_reg": tail,
                "aircraft_type": ac_type,
                "aircraft_type_original": ac_type,
                "size_code": self.aircraft_size_map.get(ac_type, "C"),
                "is_delayed_over_30": False,
                "status": "DIVERTED_IN",
                "delay_minutes": 0,
                "delay_reason": "DIVERSION",
                "original_scheduled_ts": ts
            }
            self.flights.append(new_flight)
            log_entry["message"] = f"Unscheduled flight {new_flight['flight_id']} diverted in ({ac_type}, {tail}) at {ts}"
            self.build_plan()

        elif action == "DIVERT_OUT":
            # DIVERT_OUT|flight_id|timestamp
            flight_id = args[0]
            for f in self.flights:
                if f["flight_id"] == flight_id:
                    f["status"] = "DIVERTED_OUT"
                    log_entry["message"] = f"Flight {flight_id} diverted out to alternate airport"
                    break
            self.build_plan()

        elif action.startswith("PRINT_"):
            log_entry["message"] = f"Report generated: {action} {' '.join(args)}"

        self.execution_log.append(log_entry)
        return log_entry

    def step_next_command(self):
        """Execute next command from command list."""
        if self.command_index < len(self.commands):
            cmd = self.commands[self.command_index]
            self.command_index += 1
            entry = self.execute_command(cmd)
            return {"done": False, "index": self.command_index, "total": len(self.commands), "command": cmd, "log": entry}
        return {"done": True, "index": self.command_index, "total": len(self.commands)}

    def execute_all_commands(self):
        """Run all remaining commands."""
        executed = []
        while self.command_index < len(self.commands):
            res = self.step_next_command()
            executed.append(res.get("log"))
        return executed

    def get_overview_kpis(self):
        """Compute top-level operational statistics."""
        total_flts = len(self.flights)
        active_flts = [f for f in self.flights if f.get("status") != "CANCELLED"]
        delayed_flts = [f for f in self.flights if f.get("status") == "DELAYED" or f.get("is_delayed_over_30")]
        cancelled_flts = [f for f in self.flights if f.get("status") == "CANCELLED"]
        diverted_flts = [f for f in self.flights if "DIVERT" in str(f.get("status"))]

        # Gate occupancy
        occupied_stands = set(f.get("assigned_stand") for f in active_flts if f.get("assigned_stand"))
        total_stands = len(self.stands)
        gate_occupancy_pct = round((len(occupied_stands) / total_stands) * 100, 1) if total_stands else 0

        # Runway bins utilization
        bin_counts = {}
        for f in active_flts:
            b = f.get("allocated_bin")
            if b:
                bin_counts[b] = bin_counts.get(b, 0) + 1
        peak_movements = max(bin_counts.values()) if bin_counts else 0
        saturated_bins = sum(1 for c in bin_counts.values() if c >= 12)

        # Revenue
        total_rev = sum(s.get("total_charges", 0.0) for s in self.airline_charges)

        return {
            "total_flights": total_flts,
            "active_movements": len(active_flts),
            "delayed_flights": len(delayed_flts),
            "cancelled_flights": len(cancelled_flts),
            "diverted_flights": len(diverted_flts),
            "active_stands_count": len(occupied_stands),
            "total_stands_count": total_stands,
            "gate_occupancy_pct": gate_occupancy_pct,
            "peak_runway_movements": peak_movements,
            "saturated_runway_bins": saturated_bins,
            "total_revenue": total_rev,
            "command_progress": {
                "current": self.command_index,
                "total": len(self.commands)
            }
        }

    def get_runway_data(self):
        """Return all 15-minute runway bins with allocated flights and capacity status."""
        bins_dict = {}
        for r in self.raw_runway_capacity:
            b_start = r["bin_start"]
            bins_dict[b_start] = {
                "bin_start": b_start,
                "bin_end": r["bin_end"],
                "capacity": int(r["capacity"]),
                "flights": [],
                "arrivals": 0,
                "departures": 0,
                "delayed_priority": 0
            }

        for f in self.flights:
            if f.get("status") == "CANCELLED":
                continue
            b = f.get("allocated_bin")
            if b in bins_dict:
                bins_dict[b]["flights"].append({
                    "flight_id": f["flight_id"],
                    "airline_code": f["airline_code"],
                    "direction": f["direction"],
                    "size_code": f["size_code"],
                    "is_delayed": f.get("is_delayed_over_30", False)
                })
                if f["direction"] == "ARR":
                    bins_dict[b]["arrivals"] += 1
                else:
                    bins_dict[b]["departures"] += 1
                if f.get("is_delayed_over_30"):
                    bins_dict[b]["delayed_priority"] += 1

        res = list(bins_dict.values())
        res.sort(key=lambda x: x["bin_start"])
        return res

    def get_gate_timeline_data(self):
        """Return stand information with assigned flight timelines."""
        stands_res = []
        for s in self.stands:
            stand_id = s["stand_id"]
            assigned_rotations = [
                rot for rot in self.rotations if rot.get("stand_id") == stand_id
            ]
            timeline = []
            for rot in assigned_rotations:
                arr = rot["arrival"]
                dep = rot["departure"]
                if arr and dep and arr.get("status") != "CANCELLED" and dep.get("status") != "CANCELLED":
                    arr_dt = parse_dt(arr["scheduled_ts"])
                    dep_dt = parse_dt(dep["scheduled_ts"])
                    occ_start = arr_dt - timedelta(minutes=5)
                    occ_end = dep_dt + timedelta(minutes=25)
                    timeline.append({
                        "rotation_id": rot["rotation_id"],
                        "airline_code": rot["airline_code"],
                        "aircraft_type": rot["aircraft_type"],
                        "size_code": rot["size_code"],
                        "arr_flight": arr["flight_id"],
                        "dep_flight": dep["flight_id"],
                        "arr_time": arr["scheduled_ts"],
                        "dep_time": dep["scheduled_ts"],
                        "start": format_dt(occ_start),
                        "end": format_dt(occ_end)
                    })
            timeline.sort(key=lambda x: x["start"])
            stand_copy = s.copy()
            stand_copy["timeline"] = timeline
            stand_copy["occupancy_count"] = len(timeline)
            stands_res.append(stand_copy)
        return stands_res

    def simulate_custom_flight(self, req):
        """
        Interactive calculation sandbox:
        Tests an arrival/departure slot, evaluates gate compatibility,
        estimates turnaround tasks, and projects charges.
        """
        ac_type = req.get("aircraft_type", "A320")
        size_code = self.aircraft_size_map.get(ac_type, "C")
        airline = req.get("airline_code", "KV")
        arr_ts = req.get("arrival_ts", "2026-10-14 12:00:00")
        dep_ts = req.get("departure_ts", "2026-10-14 14:30:00")
        intl = to_bool(req.get("international", False))

        arr_dt = parse_dt(arr_ts)
        dep_dt = parse_dt(dep_ts)

        # 1. Runway slot check
        runway_mgr = RunwayManager()
        sim_flight = {
            "flight_id": "SIM-FLT",
            "direction": "ARR",
            "scheduled_ts": arr_ts,
            "is_delayed_over_30": False,
            "aircraft_type": size_code
        }
        res_flt = runway_mgr.allocate_batch([sim_flight])[0]
        alloc_bin = res_flt["allocated_bin"]

        # 2. Gate recommendation
        gate_mgr = GateManager()
        test_flight = {
            "flight_id": "SIM-ARR",
            "rotation_id": "ROT-SIM",
            "airline_code": airline,
            "aircraft_type": size_code,
            "scheduled_ts": arr_ts,
            "departure_ts": dep_ts,
            "international": intl
        }
        assigned = gate_mgr.assign_gates([test_flight], self.stands)[0]
        rec_stand_id = assigned.get("assigned_stand")
        rec_stand = self.stands_map.get(rec_stand_id)

        # 3. Ground turnaround estimation
        teams = [s.copy() for s in self.raw_service_teams]
        task_durations = []
        for t in self.raw_task_durations:
            t_copy = t.copy()
            if t_copy["task"].strip().upper() == "SECURITY_CHECK":
                t_copy["task"] = "security"
            t_copy["predecessors"] = t_copy.get("predecessors", "").replace("SECURITY_CHECK", "security")
            task_durations.append(t_copy)

        scheduler = TaskScheduler(teams, task_durations)
        try:
            tasks = scheduler.schedule_tasks([{
                "rotation_id": "ROT-SIM",
                "scheduled_ts": arr_ts,
                "international": intl
            }])
        except Exception:
            tasks = []

        # 4. Projected Charges
        duration_min = max(0, int((dep_dt - arr_dt).total_seconds() / 60))
        stand_type = rec_stand["stand_type"] if rec_stand else "CONTACT"
        free_min = 240 if stand_type == "REMOTE" else 120
        billable_min = max(0, duration_min - free_min)
        blocks_15m = math.ceil(billable_min / 15.0) if billable_min > 0 else 0
        rate = 900.0 if size_code == "E" else 400.0
        parking_fee = blocks_15m * rate
        aerobridge_fee = 2500.0 if (rec_stand and rec_stand.get("aerobridge")) else 0.0

        is_peak = (
            (6 <= arr_dt.hour < 9) or (18 <= arr_dt.hour < 21) or
            (6 <= dep_dt.hour < 9) or (18 <= dep_dt.hour < 21)
        )
        peak_fee = (parking_fee * 0.25) if is_peak else 0.0
        total_est = parking_fee + aerobridge_fee + peak_fee

        return {
            "status": "SUCCESS",
            "aircraft_type": ac_type,
            "size_code": size_code,
            "airline_code": airline,
            "arrival_ts": arr_ts,
            "departure_ts": dep_ts,
            "duration_minutes": duration_min,
            "runway_allocated_bin": alloc_bin,
            "recommended_stand": rec_stand_id,
            "stand_details": rec_stand,
            "estimated_turnaround_tasks": tasks,
            "charges_estimate": {
                "free_minutes": free_min,
                "billable_minutes": billable_min,
                "billable_blocks_15m": blocks_15m,
                "rate_per_block": rate,
                "parking_fee": parking_fee,
                "aerobridge_fee": aerobridge_fee,
                "is_peak": is_peak,
                "peak_fee": peak_fee,
                "total_estimated_fee": total_est
            }
        }

    def get_surveillance_telemetry(self):
        """
        Generate realistic simulated aviation visual intelligence & surveillance telemetry:
        - Multi-perspective camera feeds (Runway 09/27, Main Apron, Domestic Terminal, International Terminal)
        - 360-degree radar tracks derived deterministically from flights
        - Top-down airport ground nodes and stand occupancy matrix
        """
        camera_feeds = [
            {
                "id": "CAM-01",
                "name": "RUNWAY 09/27 (ACTIVE THRESHOLD)",
                "view_type": "RUNWAY_09_27",
                "label": "SIMULATED FEED • DEMO CAMERA 01",
                "status": "OPERATIONAL",
                "rwy": "09/27",
                "rvr": "2000m",
                "vis": "10 km",
                "wind": "270° / 12 KT",
                "qnh": "1013 hPa",
                "elevation": "82 FT MSL",
                "image_url": "https://images.unsplash.com/photo-1520437358207-323b43b50729?auto=format&fit=crop&w=1200&q=80",
                "desc": "Touchdown zone and rapid-exit taxiway Alpha surveillance"
            },
            {
                "id": "CAM-02",
                "name": "MAIN APRON & TAXIWAY CHARLIE",
                "view_type": "MAIN_APRON",
                "label": "SIMULATED FEED • DEMO CAMERA 02",
                "status": "OPERATIONAL",
                "rwy": "APRON-MAIN",
                "rvr": "VISUAL",
                "vis": "10 km",
                "wind": "270° / 12 KT",
                "qnh": "1013 hPa",
                "elevation": "78 FT MSL",
                "image_url": "https://images.unsplash.com/photo-1540959733332-eab4deabeeaf?auto=format&fit=crop&w=1200&q=80",
                "desc": "Apron movement control, pushback corridors and ground servicing"
            },
            {
                "id": "CAM-03",
                "name": "DOMESTIC TERMINAL (PIERS DOM_A & B)",
                "view_type": "DOMESTIC_TERMINAL",
                "label": "SIMULATED FEED • DEMO CAMERA 03",
                "status": "OPERATIONAL",
                "rwy": "TERMINAL-1",
                "rvr": "VISUAL",
                "vis": "10 km",
                "wind": "270° / 12 KT",
                "qnh": "1013 hPa",
                "elevation": "80 FT MSL",
                "image_url": "https://images.unsplash.com/photo-1583863788434-e58a36330cf0?auto=format&fit=crop&w=1200&q=80",
                "desc": "Domestic aerobridges G01-G12 with narrowbody A320/B738 operations"
            },
            {
                "id": "CAM-04",
                "name": "INTERNATIONAL TERMINAL (PIER INTL)",
                "view_type": "INTERNATIONAL_TERMINAL",
                "label": "SIMULATED FEED • DEMO CAMERA 04",
                "status": "OPERATIONAL",
                "rwy": "TERMINAL-2 INTL",
                "rvr": "VISUAL",
                "vis": "10 km",
                "wind": "270° / 12 KT",
                "qnh": "1013 hPa",
                "elevation": "85 FT MSL",
                "image_url": "https://images.unsplash.com/photo-1569154941061-e231b4725ef1?auto=format&fit=crop&w=1200&q=80",
                "desc": "Heavy widebody gates G13-G18 accommodating B777, B787 and A350 aircraft"
            }
        ]

        # Generate deterministic radar tracks for all active flights
        radar_tracks = []
        active_flights = [f for f in self.flights if f.get("status") != "CANCELLED"]

        for idx, flt in enumerate(active_flights):
            flight_id = flt["flight_id"]
            direction = flt["direction"]
            airline = flt["airline_code"]
            ac_type = flt["aircraft_type"]
            size_code = flt["size_code"]
            is_delayed = flt.get("is_delayed_over_30", False) or (flt.get("delay_minutes", 0) > 0)
            status = flt.get("status", "SCHEDULED")

            # Deterministic pseudo-random seed based on flight index
            seed = (idx * 37 + 13) % 100

            if direction == "ARR":
                # Approaches funneling towards runway 09 from west/northwest/southwest
                base_bearing = 250 + (seed % 60) - 30 # 220 to 280 deg
                base_range = 6.0 + (idx % 25) * 2.8 # 6 to 76 NM
                heading = (85 + (seed % 15) - 7) % 360 # Heading ~090 towards runway 09
                altitude = max(1800, int(base_range * 320 + 1200))
                speed = 155 + (idx % 8) * 12
                phase = "FINAL APPROACH" if base_range < 12 else ("DESCENT" if base_range < 35 else "EN ROUTE")
            else:
                # Departures climbing out east/southeast
                base_bearing = 70 + (seed % 50) # 70 to 120 deg
                base_range = 8.0 + (idx % 22) * 3.2 # 8 to 78 NM
                heading = (95 + (seed % 20) - 10) % 360
                altitude = max(3500, int(base_range * 450 + 2000))
                speed = 240 + (idx % 12) * 15
                phase = "CLIMBING" if base_range < 25 else "EN ROUTE CRUISE"

            # Cartesian coordinates relative to airport center (0,0) in NM
            rad = math.radians(base_bearing)
            pos_x = round(base_range * math.sin(rad), 2)
            pos_y = round(base_range * math.cos(rad), 2)

            radar_tracks.append({
                "flight_id": flight_id,
                "flight_no": flt.get("flight_no", flight_id),
                "airline_code": airline,
                "aircraft_type": ac_type,
                "aircraft_reg": flt.get("aircraft_reg", "VT-AIR"),
                "size_code": size_code,
                "direction": direction,
                "status": status,
                "is_delayed": is_delayed,
                "bearing_deg": round(base_bearing, 1),
                "range_nm": round(base_range, 1),
                "pos_x_nm": pos_x,
                "pos_y_nm": pos_y,
                "altitude_ft": min(38000, altitude),
                "speed_kt": speed,
                "heading_deg": heading,
                "phase": phase,
                "assigned_stand": flt.get("assigned_stand"),
                "allocated_bin": flt.get("allocated_bin"),
                "scheduled_ts": flt.get("scheduled_ts")
            })

        # Stand ground positions for top-down airport map
        stand_positions = []
        for s in self.stands:
            sid = s["stand_id"]
            pier = s["pier"]
            # Check if any rotation is actively docked at this stand
            docked_rot = next((r for r in self.rotations if r.get("stand_id") == sid), None)
            is_occupied = docked_rot is not None

            # Calculate top-down normalized SVG coordinates (x: 0-1000, y: 0-600)
            if pier == "DOM_A":
                # Stands G01 to G08 (Upper domestic concourse)
                idx = int(sid.replace("G", "")) - 1
                pos_x = 320 + idx * 45
                pos_y = 190
            elif pier == "DOM_B":
                # Stands G09 to G12 (Lower domestic concourse)
                idx = int(sid.replace("G", "")) - 9
                pos_x = 340 + idx * 55
                pos_y = 290
            elif pier == "INTL":
                # Stands G13 to G18 (Heavy international pier)
                idx = int(sid.replace("G", "")) - 13
                pos_x = 640 + idx * 52
                pos_y = 240
            else:
                # Remote R01 to R06
                idx = int(sid.replace("R", "")) - 1
                pos_x = 130 + idx * 50
                pos_y = 390

            stand_positions.append({
                "stand_id": sid,
                "stand_type": s["stand_type"],
                "pier": pier,
                "max_size_code": s["max_size_code"],
                "aerobridge": s.get("aerobridge", False),
                "swing_gate": s.get("swing_gate", False),
                "pos_x": pos_x,
                "pos_y": pos_y,
                "is_occupied": is_occupied,
                "docked_rotation_id": docked_rot.get("rotation_id") if docked_rot else None,
                "docked_flight_no": docked_rot["arrival"].get("flight_no") if (docked_rot and docked_rot.get("arrival")) else None,
                "docked_aircraft": docked_rot.get("aircraft_type") if docked_rot else None,
                "docked_airline": docked_rot.get("airline_code") if docked_rot else None
            })

        return {
            "camera_feeds": camera_feeds,
            "radar_tracks": radar_tracks,
            "stand_nodes": stand_positions,
            "active_tracks_count": len(radar_tracks),
            "surveillance_status": "SYNCHRONIZED WITH SIMULATION DATA",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        }
