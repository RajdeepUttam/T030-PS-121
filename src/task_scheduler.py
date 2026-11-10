
from datetime import datetime, timedelta


class TaskScheduler:

    def __init__(self, teams, task_durations):
        self.teams = teams
        self.task_durations = task_durations

        self.team_availability = {
            str(team["team_id"]): None
            for team in teams
        }

        self.task_definitions = self._load_task_definitions(task_durations)

        self._validate_dependencies()

    # ---------------------------------------------------------
    # TIME HELPERS
    # ---------------------------------------------------------

    @staticmethod
    def _parse_time(value):
        if isinstance(value, datetime):
            return value

        return datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )

    @staticmethod
    def _format_time(value):
        return value.isoformat(
            sep=" ",
            timespec="seconds"
        )

    # ---------------------------------------------------------
    # PREDECESSOR HANDLING
    # ---------------------------------------------------------

    @staticmethod
    def _parse_predecessors(predecessors):
        """
        Convert predecessors into a clean list.

        Supports:
            "cleaning;fuelling;catering"
            "cleaning,fuelling,catering"
            ["cleaning", "fuelling", "catering"]
            None or empty string
        """

        if not predecessors:
            return []

        if isinstance(predecessors, (list, tuple, set)):
            values = predecessors
        else:
            values = str(predecessors).replace(",", ";").split(";")

        return [
            str(value).strip().lower()
            for value in values
            if str(value).strip()
        ]

    # ---------------------------------------------------------
    # LOAD TASK DEFINITIONS
    # ---------------------------------------------------------

    def _load_task_definitions(self, task_durations):

        definitions = {}

        for task in task_durations:

            task_name = task["task"].strip().lower()

            definitions[task_name] = {
                "task": task_name,
                "duration_min": int(task["duration_min"]),
                "team_type": task["team_type"].strip(),
                "predecessors": self._parse_predecessors(
                    task.get("predecessors", "")
                )
            }

        return definitions

    # ---------------------------------------------------------
    # VALIDATE DEPENDENCIES
    # ---------------------------------------------------------

    def _validate_dependencies(self):

        task_names = set(self.task_definitions.keys())

        for task_name, definition in self.task_definitions.items():

            predecessors = self._parse_predecessors(
                definition.get("predecessors", [])
            )

            definition["predecessors"] = predecessors

            for predecessor in predecessors:

                if predecessor not in task_names:
                    raise ValueError(
                        f"Unknown predecessor '{predecessor}' "
                        f"for task '{task_name}'"
                    )

        self._check_cycles()

    def _check_cycles(self):

        visited = set()
        visiting = set()

        def visit(task_name):

            if task_name in visiting:
                raise ValueError(
                    f"Circular dependency detected at task '{task_name}'"
                )

            if task_name in visited:
                return

            visiting.add(task_name)

            for predecessor in self.task_definitions[task_name]["predecessors"]:
                visit(predecessor)

            visiting.remove(task_name)
            visited.add(task_name)

        for task_name in self.task_definitions:
            visit(task_name)

    # ---------------------------------------------------------
    # TEAM SELECTION
    # ---------------------------------------------------------

    @staticmethod
    def _team_sort_key(team_id):
        return str(team_id)

    def _get_team(self, team_type, earliest_start):

        suitable_teams = [
            team for team in self.teams
            if team["task_type"].strip().lower() == team_type.strip().lower()
        ]

        if not suitable_teams:
            raise ValueError(
                f"No team available for task type '{team_type}'"
            )

        candidates = []

        for team in suitable_teams:

            team_id = str(team["team_id"])
            available_time = self.team_availability[team_id]

            start_time = earliest_start

            if available_time is not None:
                start_time = max(start_time, available_time)

            candidates.append(
                (
                    start_time,
                    self._team_sort_key(team_id),
                    team_id
                )
            )

        candidates.sort()

        start_time, _, selected_team_id = candidates[0]

        return selected_team_id, start_time

    # ---------------------------------------------------------
    # SCHEDULE ONE TASK
    # ---------------------------------------------------------

    def _schedule_task(
        self,
        rotation_id,
        task_name,
        earliest_start
    ):

        definition = self.task_definitions[task_name]

        team_id, start_time = self._get_team(
            definition["team_type"],
            earliest_start
        )

        duration = definition["duration_min"]

        end_time = start_time + timedelta(minutes=duration)

        self.team_availability[team_id] = end_time

        return {
            "rotation_id": rotation_id,
            "task": task_name,
            "team_id": team_id,
            "start_ts": start_time,
            "end_ts": end_time
        }

    # ---------------------------------------------------------
    # MAIN SCHEDULER
    # ---------------------------------------------------------

    def schedule(self, flights):

        scheduled_tasks = []

        # Reset team availability for every new scheduling run.
        for team_id in self.team_availability:
            self.team_availability[team_id] = None

        rotation_data = {}

        for flight in flights:

            rotation_id = flight["rotation_id"]
            arrival_time = self._parse_time(flight["scheduled_ts"])

            international = str(
                flight["international"]
            ).strip().lower() in ("true", "1", "yes")

            required_tasks = {}

            # Prepare the tasks required for this flight.
            for task_name, definition in self.task_definitions.items():

                # Domestic flights do not need security.
                if task_name == "security" and not international:
                    continue

                required_tasks[task_name] = {
                    "predecessors": list(definition["predecessors"]),
                    "scheduled": False
                }

            # -------------------------------------------------
            # HANDLE SECURITY DEPENDENCY
            # -------------------------------------------------

            if international:

                if "security" not in required_tasks:
                    raise ValueError(
                        "International flights require a 'security' "
                        "task definition in task_durations.csv"
                    )

                if "boarding" not in required_tasks:
                    raise ValueError(
                        "A 'boarding' task definition is required"
                    )

                # International boarding must wait for security.
                if "security" not in required_tasks["boarding"]["predecessors"]:
                    required_tasks["boarding"]["predecessors"].append(
                        "security"
                    )

            else:

                # Domestic flights skip security.
                # Therefore, remove security from boarding dependencies
                # BEFORE validating the dependencies.
                if "boarding" in required_tasks:

                    required_tasks["boarding"]["predecessors"] = [
                        predecessor
                        for predecessor in required_tasks["boarding"]["predecessors"]
                        if predecessor != "security"
                    ]

            # -------------------------------------------------
            # STORE ROTATION INFORMATION
            # -------------------------------------------------

            rotation_data[rotation_id] = {
                "arrival_time": arrival_time,
                "tasks": required_tasks,
                "task_end_times": {}
            }

        # -----------------------------------------------------
        # VALIDATE DEPENDENCIES FOR EACH ROTATION
        # -----------------------------------------------------

        for rotation_id, data in rotation_data.items():

            required_task_names = set(data["tasks"].keys())

            for task_name, task_data in data["tasks"].items():

                # Parse predecessors before checking them.
                predecessors = self._parse_predecessors(
                    task_data["predecessors"]
                )

                task_data["predecessors"] = predecessors

                for predecessor in predecessors:

                    if predecessor not in required_task_names:
                        raise ValueError(
                            f"Task '{task_name}' in rotation "
                            f"'{rotation_id}' depends on unavailable "
                            f"task '{predecessor}'"
                        )

        # -----------------------------------------------------
        # SCHEDULE TASKS
        # -----------------------------------------------------

        while True:

            candidates = []

            for rotation_id, data in rotation_data.items():

                arrival_time = data["arrival_time"]
                tasks = data["tasks"]
                task_end_times = data["task_end_times"]

                for task_name, task_data in tasks.items():

                    if task_data["scheduled"]:
                        continue

                    predecessors = self._parse_predecessors(
                        task_data["predecessors"]
                    )

                    # Wait until every predecessor has finished.
                    if not all(
                        predecessor in task_end_times
                        for predecessor in predecessors
                    ):
                        continue

                    earliest_start = arrival_time

                    for predecessor in predecessors:
                        earliest_start = max(
                            earliest_start,
                            task_end_times[predecessor]
                        )

                    definition = self.task_definitions[task_name]

                    team_id, possible_start = self._get_team(
                        definition["team_type"],
                        earliest_start
                    )

                    candidates.append(
                        (
                            possible_start,
                            self._team_sort_key(team_id),
                            str(rotation_id),
                            task_name,
                            rotation_id,
                            earliest_start
                        )
                    )

            if not candidates:

                unfinished = [
                    (rotation_id, task_name)
                    for rotation_id, data in rotation_data.items()
                    for task_name, task_data in data["tasks"].items()
                    if not task_data["scheduled"]
                ]

                if unfinished:
                    raise ValueError(
                        f"Unable to schedule remaining tasks: {unfinished}"
                    )

                break

            # Schedule the task that can start earliest.
            candidates.sort()

            (
                _,
                _,
                _,
                task_name,
                rotation_id,
                earliest_start
            ) = candidates[0]

            task_result = self._schedule_task(
                rotation_id,
                task_name,
                earliest_start
            )

            rotation_data[rotation_id]["tasks"][task_name]["scheduled"] = True

            rotation_data[rotation_id]["task_end_times"][task_name] = (
                task_result["end_ts"]
            )

            scheduled_tasks.append(task_result)

        # -----------------------------------------------------
        # FORMAT FINAL OUTPUT
        # -----------------------------------------------------

        for task in scheduled_tasks:

            task["start_ts"] = self._format_time(task["start_ts"])
            task["end_ts"] = self._format_time(task["end_ts"])

        scheduled_tasks.sort(
            key=lambda task: (
                task["start_ts"],
                str(task["team_id"]),
                str(task["rotation_id"])
            )
        )

        return scheduled_tasks

    # Alias for compatibility.
    def schedule_tasks(self, flights):
        return self.schedule(flights)


if __name__ == "__main__":
    # 1. Define our teams
    teams = [
        {'team_id': 'TEAM-01', 'task_type': 'deboarding'},
        {'team_id': 'TEAM-02', 'task_type': 'cleaning'},
        {'team_id': 'TEAM-03', 'task_type': 'fuelling'},
        {'team_id': 'TEAM-04', 'task_type': 'catering'},
        {'team_id': 'TEAM-05', 'task_type': 'boarding'},
        {'team_id': 'TEAM-06', 'task_type': 'security'}
    ]
    
    # 2. Define the durations and dependencies
    task_durations = [
        {'task': 'deboarding', 'duration_min': '15', 'team_type': 'deboarding', 'predecessors': ''},
        {'task': 'cleaning', 'duration_min': '20', 'team_type': 'cleaning', 'predecessors': 'deboarding'},
        {'task': 'fuelling', 'duration_min': '25', 'team_type': 'fuelling', 'predecessors': 'deboarding'},
        {'task': 'catering', 'duration_min': '20', 'team_type': 'catering', 'predecessors': 'deboarding'},
        {'task': 'security', 'duration_min': '15', 'team_type': 'security', 'predecessors': 'deboarding'},
        {'task': 'boarding', 'duration_min': '25', 'team_type': 'boarding', 'predecessors': 'cleaning;fuelling;catering;security'}
    ]
    
    # 3. Define a domestic flight
    flights = [
        {'rotation_id': 'ROT-001', 'scheduled_ts': '2026-10-14 08:00:00', 'international': False}
    ]
    
    # NOTE: We pass teams and task_durations here now!
    scheduler = TaskScheduler(teams, task_durations)
    
    # Run the scheduler
    result = scheduler.schedule_tasks(flights)
    
    print("\nTask Schedule Results:")
    for task in result:
        print(f"{task['rotation_id']} | {task['task']:<10} | {task['team_id']} | {task['start_ts']} to {task['end_ts']}")