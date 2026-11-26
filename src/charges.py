from datetime import datetime

def calculate_charges(final_flights, stands):
    charges = []
    
    # Create a quick lookup for stand types
    stand_map = {s["stand_id"]: s for s in stands}
    
    # Rates from the brief
    PARKING_C = 400
    PARKING_E = 900
    AEROBRIDGE = 2500
    
    # We only want to charge once per rotation, so we use a dictionary to prevent duplicates
    charged_rotations = set()
    
    for f in final_flights:
        rot = f["rotation_id"]
        
        # Skip if we already calculated charges for this rotation
        if rot in charged_rotations:
            continue
            
        if not f.get("assigned_stand"):
            continue
            
        # We calculate charges based on the combined gate info (which we saved earlier)
        airline = f["airline_code"]
        stand = stand_map[f["assigned_stand"]]
        
        # Get arrival and departure times
        arr_time = datetime.strptime(f["scheduled_ts"], "%Y-%m-%d %H:%M:%S")
        
        # If this is an ARR flight, find its linked departure time from the dict
        if f.get("departure_ts"):
            dep_time = datetime.strptime(f["departure_ts"], "%Y-%m-%d %H:%M:%S")
        else:
            # This is a DEP flight, so scheduled_ts IS the departure time. We skip it 
            # because we will charge based on the ARR flight.
            continue

        duration_hours = (dep_time - arr_time).total_seconds() / 3600
        
        # Check if within free period (2 hrs contact, 4 hrs remote)
        free_hours = 2 if stand["stand_type"] == "CONTACT" else 4
        
        if duration_hours > free_hours:
            chargeable_hours = duration_hours - free_hours
            # Round up to the nearest 15 minutes (0.25 hours)
            blocks = int(chargeable_hours / 0.25)
            if chargeable_hours % 0.25 > 0:
                blocks += 1
                
            rate = PARKING_E if f["aircraft_type"] == "E" else PARKING_C
            amount = blocks * rate
            charges.append({
                "airline_code": airline, "rotation_id": rot,
                "charge_code": "PARKING", "quantity": blocks, "rate": rate, "amount": amount
            })
            
        # 2. Aerobridge Charge
        if stand["aerobridge"] is True or str(stand["aerobridge"]).lower() == "true":
            charges.append({
                "airline_code": airline, "rotation_id": rot,
                "charge_code": "AEROBRIDGE", "quantity": 1, "rate": AEROBRIDGE, "amount": AEROBRIDGE
            })
            
        # 3. Tow Charge (if turnaround > 4 hours)
        if duration_hours > 4:
            charges.append({
                "airline_code": airline, "rotation_id": rot,
                "charge_code": "TOW", "quantity": 2, "rate": 6000, "amount": 12000
            })
            
        # Mark this rotation as charged
        charged_rotations.add(rot)
            
    # Add TOTAL rows per airline
    airlines = set(c["airline_code"] for c in charges)
    for a in airlines:
        total = sum(c["amount"] for c in charges if c["airline_code"] == a)
        charges.append({
            "airline_code": a, "rotation_id": "TOTAL",
            "charge_code": "TOTAL", "quantity": 1, "rate": total, "amount": total
        })
        
    return charges