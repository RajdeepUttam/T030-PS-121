# Decision Log

1. Language: Chose Python for faster development and easy CSV handling.
2. No External DB: Used in-memory Python dictionaries to keep the project lightweight.
3. Runway Logic: Implemented a batch-sorting algorithm to ensure delayed departures correctly push out arrivals.
4. Gate Adjacency: Pre-loaded gate_adjacency.csv into a dictionary lookup to quickly block adjacent gates for Code E aircraft.
5. Task Scheduling: Used a simple topological list (Deboarding -> Cleaning/Fuelling/Catering -> Boarding) instead of a complex DAG algorithm for easier viva explanation.
6. Team Ties: Sorted teams numerically (TEAM-01 before TEAM-10) to handle availability ties.
7. Charges: Simplified the charges to standard rates and ignored complex peak surcharges to ensure code readability.
8. Output: Generated CSV files directly from the data models to match the exact format required by the evaluator.