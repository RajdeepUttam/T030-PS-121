from datetime import datetime, timedelta


class GateManager:
    """
    Airport gate allocation manager.

    Assignment priority:
    1. Preferred airline gate, if compatible and available.
    2. Nearest compatible contact gate.
    3. Compatible remote stand.

    Pier restrictions:
    - International: INTL pier OR swing gate.
    - Domestic: Never INTL pier.
    - Domestic: DOM pier, swing gate, or remote stand.

    Occupancy:
    - Starts 5 minutes before arrival.
    - Ends 25 minutes after departure.
    """

    TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

    ARRIVAL_BUFFER = 5
    DEPARTURE_BUFFER = 25

    SIZE_RANK = {
        "C": 1,
        "E": 2
    }

    def __init__(self):
        self.stand_occupancy = {}

    def _parse_time(self, timestamp):
        """Convert timestamp string into datetime."""
        return datetime.strptime(
            timestamp,
            self.TIMESTAMP_FORMAT
        )

    def _get_occupancy_interval(self, flight):
        """Calculate stand occupancy interval."""

        arrival = self._parse_time(
            flight["scheduled_ts"]
        )

        departure = self._parse_time(
            flight["departure_ts"]
        )

        if departure < arrival:
            raise ValueError(
                "Departure time cannot be before arrival time"
            )

        start_time = arrival - timedelta(
            minutes=self.ARRIVAL_BUFFER
        )

        end_time = departure + timedelta(
            minutes=self.DEPARTURE_BUFFER
        )

        return start_time, end_time

    def _is_size_compatible(self, flight, stand):
        """Check aircraft and stand size compatibility."""

        aircraft_size = self.SIZE_RANK.get(
            flight["aircraft_type"]
        )

        stand_size = self.SIZE_RANK.get(
            stand["max_size_code"]
        )

        if aircraft_size is None or stand_size is None:
            return False

        return aircraft_size <= stand_size

    def _is_pier_compatible(self, flight, stand):
        """
        Check international/domestic pier restrictions.
        """
        if flight["international"]:
            # International flights must use INTL pier or a SWING gate
            return (
                stand["pier"] == "INTL"
                or stand["swing_gate"] is True
                or stand["pier"] == "REMOTE"
            )
        else:
            # Domestic flights must NOT use INTL pier gates (unless it's a SWING gate or remote)
            return (
                stand["pier"] != "INTL"
                or stand["swing_gate"] is True
                or stand["pier"] == "REMOTE"
            )

    def _is_compatible(self, flight, stand):
        """Check aircraft size and pier compatibility."""

        return (
            self._is_size_compatible(flight, stand)
            and self._is_pier_compatible(flight, stand)
        )

    def _is_stand_free(self, stand, start_time, end_time):
        """Check whether the stand has an overlapping reservation."""

        stand_id = stand["stand_id"]

        reservations = self.stand_occupancy.get(
            stand_id, []
        )

        for occupied_start, occupied_end in reservations:

            if (
                start_time < occupied_end
                and end_time > occupied_start
            ):
                return False

        return True

    def _assign_stand(
        self, flight, stand, start_time, end_time
    ):
        """Reserve a stand and update flight information."""

        stand_id = stand["stand_id"]

        self.stand_occupancy.setdefault(
            stand_id, []
        ).append((start_time, end_time))

        flight["assigned_stand"] = stand_id

        # Mark international swing gate assignments.
        if (
            flight["international"]
            and stand["swing_gate"]
        ):
            flight["assignment_flag"] = "SWITCH"
        else:
            flight.pop("assignment_flag", None)

    def assign_gates(self, flights, stands):
        """
        Allocate gates to flights.

        Returns the updated flights list.
        """

        # Reset reservations for a new allocation.
        self.stand_occupancy = {}

        # Process flights by arrival time.
        sorted_flights = sorted(
            flights,
            key=lambda f: self._parse_time(
                f["scheduled_ts"]
            )
        )

        for flight in sorted_flights:

            start_time, end_time = (
                self._get_occupancy_interval(flight)
            )

            flight["assigned_stand"] = None
            flight.pop("assignment_flag", None)

            assigned = False

            # STEP 1: Preferred airline gate.
            preferred_stands = [
                stand for stand in stands
                if stand["preferred_airline"]
                == flight["airline_code"]
            ]

            for stand in preferred_stands:

                if (
                    self._is_compatible(flight, stand)
                    and self._is_stand_free(
                        stand, start_time, end_time
                    )
                ):

                    self._assign_stand(
                        flight, stand, start_time, end_time
                    )

                    assigned = True
                    break

            if assigned:
                continue

            # STEP 2: Nearest compatible contact gate.
            contact_stands = [
                stand for stand in stands
                if (
                    stand["stand_type"] == "CONTACT"
                    and self._is_compatible(flight, stand)
                )
            ]

            contact_stands.sort(
                key=lambda s: s["walking_distance_m"]
            )

            for stand in contact_stands:

                if self._is_stand_free(
                    stand, start_time, end_time
                ):

                    self._assign_stand(
                        flight, stand, start_time, end_time
                    )

                    assigned = True
                    break

            if assigned:
                continue

            # STEP 3: Compatible remote stands.
            remote_stands = [
                stand for stand in stands
                if (
                    stand["stand_type"] == "REMOTE"
                    and self._is_compatible(flight, stand)
                )
            ]

            for stand in remote_stands:

                if self._is_stand_free(
                    stand, start_time, end_time
                ):

                    self._assign_stand(
                        flight, stand, start_time, end_time
                    )

                    assigned = True
                    break

            # If no compatible stand is available,
            # assigned_stand remains None.

        return flights


if __name__ == "__main__":
    manager = GateManager()
    
    stands = [
        {'stand_id': 'G1', 'stand_type': 'CONTACT', 'pier': 'INTL', 'max_size_code': 'E', 'swing_gate': False, 'walking_distance_m': 100, 'preferred_airline': 'AI'},
        {'stand_id': 'G2', 'stand_type': 'CONTACT', 'pier': 'DOM_A', 'max_size_code': 'C', 'swing_gate': False, 'walking_distance_m': 200, 'preferred_airline': 'AI'},
        {'stand_id': 'G3', 'stand_type': 'CONTACT', 'pier': 'INTL', 'max_size_code': 'E', 'swing_gate': False, 'walking_distance_m': 150, 'preferred_airline': 'None'},
        {'stand_id': 'R1', 'stand_type': 'REMOTE', 'pier': 'REMOTE', 'max_size_code': 'E', 'swing_gate': False, 'walking_distance_m': 500, 'preferred_airline': 'None'}
    ]
    
    flights = [
        {'flight_id': 'FLT-101', 'airline_code': 'AI', 'international': True, 'aircraft_type': 'C', 'scheduled_ts': '2026-10-14 08:00:00', 'departure_ts': '2026-10-14 10:00:00'},
        {'flight_id': 'FLT-102', 'airline_code': 'AI', 'international': False, 'aircraft_type': 'C', 'scheduled_ts': '2026-10-14 11:00:00', 'departure_ts': '2026-10-14 12:00:00'},
        {'flight_id': 'FLT-103', 'airline_code': 'SG', 'international': True, 'aircraft_type': 'E', 'scheduled_ts': '2026-10-14 08:00:00', 'departure_ts': '2026-10-14 10:00:00'}
    ]
    
    result = manager.assign_gates(flights, stands)
    
    print("\nGate Allocation Results:")
    for f in result:
        print(f"Flight {f['flight_id']} ({f['aircraft_type']}, INTL: {f['international']}) -> Stand: {f.get('assigned_stand')}")