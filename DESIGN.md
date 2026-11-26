# Design Document

## Glossary
- Turnaround: The process from aircraft arrival (on-block) to departure (off-block).
- Bin: A 15-minute window used to track runway capacity (max 12 movements).
- SWING Gate: A gate that can switch between domestic and international mode (takes 20 mins).
- MCT: Minimum Connecting Time.

## Class Diagram
- parser.py: Loads CSVs into dictionaries.
- runway.py: RunwayManager allocates 15-min bins based on capacity and delay priority.
- gate_manager.py: GateManager assigns stands, handles buffers, adjacency blocking, and SWING modes.
- task_scheduler.py: TaskScheduler manages parallel ground service tasks and team availability.
- charges.py: Calculates parking, aerobridge, and tow charges.

## Business Rule Register
- BR-01: Runway capacity is 12 per 15-min bin. Delayed departures get priority.
- BR-02: Minimum turnaround by aircraft size (C=45/60, E=90/120).
- BR-03: Gate compatibility (size, pier, adjacency blocking).
- BR-04: Assignment order (Preferred -> Contact -> Remote).
- BR-05: 15-minute buffer between aircraft on the same gate.
- BR-06: Parallel ground service tasks with precedence and team availability.
- BR-07: Delay re-plans gate if buffer exceeded.
- BR-08: Diversions take remote stands; cancellations release gates.
- BR-09: Charges for parking, aerobridge, and tow.
- BR-10: Penalties for airline-caused delays.
- BR-11: MCT connection flags.
- BR-12: Precedence of allocation (bins -> turnaround -> gates -> tasks).