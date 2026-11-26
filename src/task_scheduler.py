from datetime import datetime, timedelta

class TaskScheduler:
    def __init__(self, teams, task_durations):
        self.teams = teams
        
        self.task_defs = {}
        for t in task_durations:
            # Convert task name to lowercase to match our order array
            task_name = t["task"].strip().lower()
            self.task_defs[task_name] = {
                "duration": int(t["duration_min"].strip()),
                "team_type": t["team_type"].strip(),
                "predecessors": [p.strip().lower() for p in t["predecessors"].split(";") if p.strip()]
            }
        
        # Tie-breaker: sort by numeric ID (TEAM-02 before TEAM-10)
        self.teams.sort(key=lambda t: int(t["team_id"].strip().split("-")[1]))

    def _parse_time(self, ts):
        if isinstance(ts, datetime): return ts
        return datetime.strptime(str(ts), "%Y-%m-%d %H:%M:%S")

    def _format_time(self, ts):
        return ts.strftime("%Y-%m-%d %H:%M:%S")

    def schedule_tasks(self, rotations):
        team_available = {t["team_id"].strip(): None for t in self.teams}
        scheduled_tasks = []
        
        rotations = sorted(rotations, key=lambda r: self._parse_time(r["scheduled_ts"]))

        for rot in rotations:
            arr_time = self._parse_time(rot["scheduled_ts"])
            is_intl = rot["international"]
            
            required_tasks = []
            for t_name in self.task_defs:
                if t_name == "security_check" and not is_intl:
                    continue
                required_tasks.append(t_name)
            
            # The order now matches the lowercase CSV names
            order = ["deboarding", "cleaning", "fuelling", "catering", "security_check", "boarding"]
            task_end_times = {}
            
            for t_name in order:
                if t_name not in required_tasks:
                    continue
                
                definition = self.task_defs[t_name]
                
                earliest_start = arr_time
                for p in definition["predecessors"]:
                    if p == "security_check" and not is_intl:
                        continue
                    if p in task_end_times:
                        earliest_start = max(earliest_start, task_end_times[p])
                
                best_team = None
                best_start = None
                
                for team in self.teams:
                    if team["task_type"].strip() != definition["team_type"]:
                        continue
                    
                    t_id = team["team_id"].strip()
                    available_at = team_available[t_id]
                    
                    start_time = earliest_start
                    if available_at is not None:
                        start_time = max(start_time, available_at)
                    
                    if best_start is None or start_time < best_start:
                        best_start = start_time
                        best_team = t_id
                
                if best_team:
                    end_time = best_start + timedelta(minutes=definition["duration"])
                    team_available[best_team] = end_time
                    task_end_times[t_name] = end_time
                    
                    planned_end = arr_time + timedelta(minutes=definition["duration"])
                    delay_min = max(0, int((end_time - planned_end).total_seconds() / 60))
                    
                    scheduled_tasks.append({
                        "rotation_id": rot["rotation_id"],
                        "task": t_name,
                        "team_id": best_team,
                        "start_ts": self._format_time(best_start),
                        "end_ts": self._format_time(end_time),
                        "delay_min": delay_min
                    })
            
            if "boarding" in task_end_times:
                planned_dep = self._parse_time(rot["departure_ts"])
                realised_dep = max(planned_dep, task_end_times["boarding"])
                rot["departure_ts"] = self._format_time(realised_dep)

        return scheduled_tasks