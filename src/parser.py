import csv

def load_csv(filepath):
    """Reads a CSV file and returns a list of dictionaries."""
    data = []
    with open(filepath, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append(row)
    return data

# This part only runs if you execute this file directly
if __name__ == "__main__":
    # We use ../ because the terminal runs from the main folder, but data is in the data folder
    flights = load_csv('data/flights.csv')
    stands = load_csv('data/stands.csv')
    commands = load_csv('data/runway_capacity.csv')
    
    print(f"Success! Loaded:")
    print(f"- {len(flights)} flights")
    print(f"- {len(stands)} stands")
    print(f"- {len(commands)} runway bins")