from datetime import datetime, timedelta

class GateManager:
    """
    Airport gate allocation manager.
    Handles size compatibility, pier restrictions, buffer times, and adjacency blocking.
    """
    TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
    
    # Occupancy rules from the brief
    ARRIVAL_BUFFER = 5
    DEPARTURE_BUFFER = 10
    NEXT_FLIGHT_BUFFER = 15 # 10 + 15 = 25 mins after departure

    SIZE_RANK = {"C": 1, "E": 2}

    def __init__(self, adjacency_list=None):
        # Stores occupied time intervals for every stand: {stand_id: [(start, end, size), ...]}
        self.stand_occupancy = {}
        
        # Store adjacency: {gate_id: {adjacent_gate_1, adjacent_gate_2}}
        self.adjacency = {}
        if adjacency_list:
            for a, b in adjacency_list:
                self.adjacency.setdefault(a, set()).add(b)
                self.adjacency.setdefault(b, set()).add(a)

    def _parse_time(self, timestamp):
        if isinstance(timestamp, datetime):
            return timestamp
        return datetime.strptime(str(timestamp), self.TIMESTAMP_FORMAT)

    def _get_occupancy(self, flight):
        """Returns (occupancy_start, occupancy_end, buffer_end)"""
        arrival = self._parse_time(flight["scheduled_ts"])
        departure = self._parse_time(flight["departure_ts"])
        
        occ_start = arrival - timedelta(minutes=self.ARRIVAL_BUFFER)
        occ_end = departure + timedelta(minutes=self.DEPARTURE_BUFFER)
        buf_end = occ_end + timedelta(minutes=self.NEXT_FLIGHT_BUFFER)
        
        return occ_start, occ_end, buf_end

    def _is_size_compatible(self, flight, stand):
        return self.SIZE_RANK.get(flight["aircraft_type"], 0) <= self.SIZE_RANK.get(stand["max_size_code"], 0)

    def _is_pier_compatible(self, flight, stand):
        if flight["international"]:
            return stand["pier"] == "INTL" or stand["swing_gate"] is True or stand["pier"] == "REMOTE"
        else:
            return stand["pier"] != "INTL" or stand["swing_gate"] is True or stand["pier"] == "REMOTE"

    def _is_stand_free(self, stand, occ_start, buf_end, size_code):
        """Checks for overlapping times and adjacency blocking"""
        stand_id = stand["stand_id"]
        
        # 1. Check standard overlap
        for (e_start, e_end, e_size) in self.stand_occupancy.get(stand_id, []):
            if (occ_start < e_end and buf_end > e_start):
                return False
                
        # 2. Check Adjacency Blocking (BR-03: Code E blocks neighbours)
        if size_code == "E":
            neighbours = self.adjacency.get(stand_id, set())
            for n_id in neighbours:
                for (e_start, e_end, e_size) in self.stand_occupancy.get(n_id, []):
                    if (occ_start < e_end and buf_end > e_start):
                        return False
                        
        # Also check if an existing E aircraft is blocking this stand
        for other_gate, reservations in self.stand_occupancy.items():
            if other_gate in self.adjacency.get(stand_id, set()):
                for (e_start, e_end, e_size) in reservations:
                    if e_size == "E" and (occ_start < e_end and buf_end > e_start):
                        return False
                        
        return True

    def _assign(self, flight, stand, occ_start, occ_end, buf_end, reason):
        flight["assigned_stand"] = stand["stand_id"]
        flight["mode"] = "DOMESTIC" if not flight["international"] else ("SWITCH" if stand["swing_gate"] else "INTERNATIONAL")
        flight["reason"] = reason
        flight["occupancy_start"] = occ_start.strftime(self.TIMESTAMP_FORMAT)
        flight["occupancy_end"] = occ_end.strftime(self.TIMESTAMP_FORMAT)
        flight["buffer_end"] = buf_end.strftime(self.TIMESTAMP_FORMAT)
        
        self.stand_occupancy.setdefault(stand["stand_id"], []).append((occ_start, buf_end, flight["aircraft_type"]))
        
        # If swing gate used for international, add a SWITCH interval
        if flight["international"] and stand["swing_gate"]:
            switch_end = occ_end + timedelta(minutes=20)
            self.stand_occupancy.setdefault(stand["stand_id"], []).append((occ_end, switch_end, "C"))

    def assign_gates(self, flights, stands):
        self.stand_occupancy = {} # Reset
        
        # Sort flights by arrival time
        sorted_flights = sorted(flights, key=lambda f: self._parse_time(f["scheduled_ts"]))
        
        for flight in sorted_flights:
            flight["assigned_stand"] = None
            occ_start, occ_end, buf_end = self._get_occupancy(flight)
            size_code = flight["aircraft_type"]
            
            assigned = False
            
            # 1. Preferred Gate
            preferred = [s for s in stands if s["preferred_airline"] == flight["airline_code"] and self._is_size_compatible(flight, s) and self._is_pier_compatible(flight, s)]
            for stand in preferred:
                if self._is_stand_free(stand, occ_start, buf_end, size_code):
                    self._assign(flight, stand, occ_start, occ_end, buf_end, "PREFERENCE")
                    assigned = True
                    break
            if assigned: continue
            
            # 2. Nearest Contact Gate
            contacts = [s for s in stands if s["stand_type"] == "CONTACT" and self._is_size_compatible(flight, s) and self._is_pier_compatible(flight, s)]
            contacts.sort(key=lambda s: s["walking_distance_m"])
            for stand in contacts:
                if self._is_stand_free(stand, occ_start, buf_end, size_code):
                    self._assign(flight, stand, occ_start, occ_end, buf_end, "NEAREST")
                    assigned = True
                    break
            if assigned: continue
            
            # 3. Remote Stand
            remotes = [s for s in stands if s["stand_type"] == "REMOTE" and self._is_size_compatible(flight, s) and self._is_pier_compatible(flight, s)]
            for stand in remotes:
                if self._is_stand_free(stand, occ_start, buf_end, size_code):
                    self._assign(flight, stand, occ_start, occ_end, buf_end, "REMOTE")
                    assigned = True
                    break
                    
        return flights