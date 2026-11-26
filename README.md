# T030-PS-121 - Airport Ground Handling Slot and Gate Allocation Engine

## Project Overview
This is a command-line driven engine that simulates an airport operations centre. It handles runway slot allocation, gate/stand assignment (with adjacency blocking), ground service task scheduling, and airline charge calculations. It is built using Python 3 and requires no external frameworks or UI.

## Prerequisites
- Python 3.10 or higher

## How to Run
1. Navigate to the project root folder.
2. Run the main engine:
   python src/main.py
3. The script will load the data from the data/ folder, process the commands, run the allocation engines, and generate 4 output CSV files in the root directory:
   - gate_plan.csv
   - slot_bins.csv
   - task_schedule.csv
   - charges.csv

## How to Run Tests
The project uses pytest for unit testing. Run the test suite using:
pip install pytest
python -m pytest tests/

## Repository Structure
- src/parser.py: Loads and cleans CSV master files.
- src/runway.py: Allocates 15-minute runway bins with priority rules.
- src/gate_manager.py: Assigns contact/remote stands with adjacency blocking and SWITCH modes.
- src/task_scheduler.py: Schedules ground service tasks with team availability.
- src/charges.py: Calculates parking, aerobridge, and towing charges.
- src/outputs.py: Exports data to the required CSV formats.
- src/main.py: The main integration entry point.