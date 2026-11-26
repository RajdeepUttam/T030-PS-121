import pytest
import sys
import os

# This tells Python to look in the src folder for your code
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from runway import RunwayManager
from gate_manager import GateManager

def test_runway_priority():
    """Tests BR-01: A delayed departure gets priority over arrivals in a full bin."""
    manager = RunwayManager()
    
    # Create 12 normal arrivals for the 08:00 bin
    flights = [
        {"flight_id": f"F{i}", "scheduled_ts": "2026-10-14 08:00:00", "direction": "ARR", "is_delayed_over_30": False} 
        for i in range(12)
    ]
    # Add 1 delayed departure
    flights.append({"flight_id": "F_DELAYED", "scheduled_ts": "2026-10-14 08:00:00", "direction": "DEP", "is_delayed_over_30": True})
    
    result = manager.allocate_batch(flights)
    
    # The delayed flight must get the 08:00 bin, pushing an arrival to 08:15
    delayed_flight = next(f for f in result if f["flight_id"] == "F_DELAYED")
    assert delayed_flight["allocated_bin"] == "2026-10-14 08:00:00"

def test_gate_domestic_never_intl():
    """Tests BR-03: Domestic flights cannot be assigned to INTL pier gates."""
    manager = GateManager()
    
    # Only 1 gate available, and it is in the INTL pier
    stands = [{"stand_id": "G1", "stand_type": "CONTACT", "pier": "INTL", "max_size_code": "E", "swing_gate": False, "walking_distance_m": 100, "preferred_airline": ""}]
    
    flights = [{"flight_id": "F1", "international": False, "aircraft_type": "C", "airline_code": "AI", "scheduled_ts": "2026-10-14 08:00:00", "departure_ts": "2026-10-14 09:00:00"}]
    
    result = manager.assign_gates(flights, stands)
    
    # The domestic flight should get None because it is blocked from the INTL pier
    assert result[0]["assigned_stand"] is None