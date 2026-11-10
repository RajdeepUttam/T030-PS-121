
from parser import load_csv
from runway import RunwayManager
from gate_manager import GateManager


def to_bool(value):
    """Convert CSV boolean values into Python booleans."""

    if isinstance(value, bool):
        return value

    return str(value).strip().lower() in (
        "true", "1", "yes"
    )


def main():

    # =====================================================
    # STEP 1: LOAD CSV FILES
    # =====================================================

    flights = load_csv("data/flights.csv")
    stands = load_csv("data/stands.csv")
    aircraft_types = load_csv("data/aircraft_types.csv")

    print("CSV files loaded successfully.")

    # =====================================================
    # STEP 2: PREPARE AIRCRAFT SIZE MAPPING
    # =====================================================

    # Assumed aircraft_types.csv columns:
    # aircraft_type, size_code
    #
    # Example:
    # A320, C
    # B777, E

    aircraft_size_map = {
        aircraft["aircraft_type"]: aircraft["size_code"]
        for aircraft in aircraft_types
    }

    # Add the corresponding size code to each flight.
    for flight in flights:

        aircraft_type = flight["aircraft_type"]

        flight["aircraft_type"] = aircraft_size_map.get(
            aircraft_type,
            aircraft_type
        )

        # Convert CSV boolean values into actual booleans.
        if "international" in flight:
            flight["international"] = to_bool(
                flight["international"]
            )

        flight["is_delayed_over_30"] = to_bool(
            flight.get("is_delayed_over_30", False)
        )

    # =====================================================
    # STEP 3: LINK ARRIVALS AND DEPARTURES
    # USING ROTATION_ID
    # =====================================================

    # Store departure flights using their rotation_id.
    departure_map = {}

    for flight in flights:

        if flight["direction"] == "DEP":

            rotation_id = flight["rotation_id"]

            if rotation_id in departure_map:
                raise ValueError(
                    f"Duplicate departure for rotation: {rotation_id}"
                )

            departure_map[rotation_id] = flight

    # Create combined arrival/departure records for gate allocation.
    gate_flights = []

    for flight in flights:

        if flight["direction"] == "ARR":

            rotation_id = flight["rotation_id"]

            # Find the matching departure.
            departure = departure_map.get(rotation_id)

            if departure is None:
                raise ValueError(
                    f"No matching departure found for rotation: "
                    f"{rotation_id}"
                )

            # Create a combined flight record.
            linked_flight = flight.copy()

            # Departure time is taken from the matching DEP flight.
            linked_flight["departure_ts"] = (
                departure["scheduled_ts"]
            )

            gate_flights.append(linked_flight)

    print("Arrival and departure flights linked successfully.")

    # =====================================================
    # STEP 4: RUNWAY SLOT ALLOCATION
    # =====================================================

    runway_manager = RunwayManager()

    # Both arrivals and departures must be passed to the
    # runway manager because both count as runway movements.
    allocated_movements = runway_manager.allocate_batch(
        [flight.copy() for flight in flights]
    )

    print("Runway slot allocation completed.")

    # Create a lookup for allocated runway bins.
    allocated_bin_map = {
        flight["flight_id"]: flight["allocated_bin"]
        for flight in allocated_movements
    }

    # =====================================================
    # STEP 5: GATE ALLOCATION
    # =====================================================

    gate_manager = GateManager()

    # Pass combined arrival/departure rotations.
    # Each rotation receives one stand for its turnaround.
    assigned_flights = gate_manager.assign_gates(
        gate_flights,
        stands
    )

    print("Gate allocation completed.")

    # Store assigned stands using rotation_id.
    assigned_stand_map = {
        flight["rotation_id"]: flight["assigned_stand"]
        for flight in assigned_flights
    }

    # =====================================================
    # STEP 6: COMBINE RUNWAY AND GATE RESULTS
    # =====================================================

    final_flights = []

    for flight in flights:

        result = flight.copy()

        # Add allocated runway bin.
        result["allocated_bin"] = allocated_bin_map.get(
            flight["flight_id"]
        )

        # Add the stand assigned to its aircraft rotation.
        result["assigned_stand"] = assigned_stand_map.get(
            flight["rotation_id"]
        )

        final_flights.append(result)

    # =====================================================
    # STEP 7: DISPLAY FIRST FIVE FLIGHTS
    # =====================================================

    print("\nFIRST 5 FLIGHT ALLOCATIONS")
    print("-" * 75)

    for flight in final_flights[:5]:

        print(
            f"Flight ID: {flight['flight_id']} | "
            f"Direction: {flight['direction']} | "
            f"Allocated Bin: {flight['allocated_bin']} | "
            f"Assigned Stand: {flight['assigned_stand']}"
        )

    print("-" * 75)


# =========================================================
# PROGRAM ENTRY POINT
# =========================================================

if __name__ == "__main__":
    main()
