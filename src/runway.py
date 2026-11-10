
from datetime import datetime, timedelta


class RunwayManager:
    """
    Airport runway slot allocation manager.

    Rules:
    1. Maximum 12 movements per 15-minute bin.
    2. Flights exceeding capacity are pushed to the next bin.
    3. Departures delayed over 30 minutes get priority.
    4. Arrivals are pushed out before normal departures.
    """

    CAPACITY = 12
    BIN_DURATION = 15

    TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

    def __init__(self):
        # Stores the allocated flights for each 15-minute bin.
        self.bin_flights = {}

    def _get_bin_start(self, timestamp):
        """
        Find the starting time of the 15-minute bin.

        Examples:
        08:07 -> 08:00
        08:18 -> 08:15
        08:32 -> 08:30
        """

        minute = (
            timestamp.minute // self.BIN_DURATION
        ) * self.BIN_DURATION

        return timestamp.replace(
            minute=minute,
            second=0,
            microsecond=0
        )

    def _get_priority(self, flight):
        """
        Assign priority to each flight.

        Priority 0: Delayed departure (highest priority)
        Priority 1: Normal departure
        Priority 2: Arrival (lowest priority)

        This ensures delayed departures are retained first,
        while arrivals are pushed out before normal departures.
        """

        if (
            flight['direction'] == 'DEP'
            and flight['is_delayed_over_30']
        ):
            return 0

        elif flight['direction'] == 'DEP':
            return 1

        else:
            return 2

    def allocate_batch(self, flights):
        """
        Allocate multiple flights in batches.

        Args:
            flights: List of flight dictionaries.

        Returns:
            Updated list of flights containing allocated_bin.
        """

        # Clear previous allocation data.
        self.bin_flights = {}

        # Parse timestamps and validate flight information.
        processed_flights = []

        for flight in flights:

            if flight['direction'] not in ('ARR', 'DEP'):
                raise ValueError(
                    "Direction must be 'ARR' or 'DEP'"
                )

            scheduled_time = datetime.strptime(
                flight['scheduled_ts'],
                self.TIMESTAMP_FORMAT
            )

            processed_flights.append({
                **flight,
                '_scheduled_datetime': scheduled_time,
                '_allocated_datetime': self._get_bin_start(
                    scheduled_time
                )
            })

        # STEP 1: Sort flights by scheduled timestamp.
        processed_flights.sort(
            key=lambda f: f['_scheduled_datetime']
        )

        # STEP 2: Group flights by their initial 15-minute bin.
        for flight in processed_flights:

            bin_time = flight['_allocated_datetime']

            self.bin_flights.setdefault(
                bin_time, []
            ).append(flight)

        # STEP 3: Process bins chronologically.
        # Continue processing until every bin satisfies capacity.
        current_bin = min(self.bin_flights, default=None)

        while current_bin is not None:

            current_flights = self.bin_flights[current_bin]

            # STEP 4: Check whether the current bin exceeds capacity.
            if len(current_flights) > self.CAPACITY:

                # STEP 5: Sort flights according to priority.
                # Scheduled timestamp breaks ties, preserving
                # chronological order within the same priority.
                current_flights.sort(
                    key=lambda f: (
                        self._get_priority(f),
                        f['_scheduled_datetime']
                    )
                )

                # Keep the highest-priority 12 flights.
                accepted_flights = current_flights[:self.CAPACITY]

                # Push remaining flights into the next bin.
                overflow_flights = current_flights[self.CAPACITY:]

                # Update the current bin with accepted flights.
                self.bin_flights[current_bin] = accepted_flights

                # STEP 6: Move overflow flights to the next bin.
                next_bin = current_bin + timedelta(
                    minutes=self.BIN_DURATION
                )

                self.bin_flights.setdefault(
                    next_bin, []
                ).extend(overflow_flights)

            # STEP 7: Move to the next chronological bin.
            # This also processes flights pushed from previous bins.
            future_bins = [
                bin_time
                for bin_time in self.bin_flights
                if bin_time > current_bin
            ]

            current_bin = min(future_bins, default=None)

        # STEP 8: Prepare the final updated flight list.
        result = []

        for bin_time in sorted(self.bin_flights):

            for flight in self.bin_flights[bin_time]:

                # Add the final allocated bin to the flight.
                flight['allocated_bin'] = bin_time.strftime(
                    self.TIMESTAMP_FORMAT
                )

                # Remove internal processing fields.
                flight.pop('_scheduled_datetime')
                flight.pop('_allocated_datetime')

                result.append(flight)

        # Return all allocated flights.
        return result



# 
if __name__ == "__main__":
    manager = RunwayManager()
    
    # Create 11 normal flights
    flights = [
        {
            'flight_id': f'FLT-{i}',
            'scheduled_ts': '2026-10-14 08:00:00',
            'direction': 'ARR',
            'is_delayed_over_30': False
        } for i in range(1, 12)
    ]
    
    # Add a delayed departure (should get priority)
    flights.append({
        'flight_id': 'FLT-12',
        'scheduled_ts': '2026-10-14 08:00:00',
        'direction': 'DEP',
        'is_delayed_over_30': True
    })
    
    # Add a normal departure (should be pushed out)
    flights.append({
        'flight_id': 'FLT-13',
        'scheduled_ts': '2026-10-14 08:00:00',
        'direction': 'DEP',
        'is_delayed_over_30': False
    })
    
    result = manager.allocate_batch(flights)
    
    print("Runway Allocation Results:")
    for f in result:
        print(f"Flight {f['flight_id']} ({f['direction']}) -> Bin: {f['allocated_bin']}")