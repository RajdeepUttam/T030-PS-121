import csv

def process_commands(filepath):
    """
    Reads the commands.txt file and returns a list of commands.
    Each command is a dictionary with 'action' and 'args'.
    """
    commands = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # Ignore empty lines and comments
            if not line or line.startswith('#'):
                continue
            
            # Split the line by the pipe character '|'
            parts = line.split('|')
            action = parts[0]
            args = parts[1:] # Everything after the action is an argument
            
            commands.append({
                'action': action,
                'args': args
            })
    return commands

def write_gate_plan(filename, data):
    """
    Writes a list of dictionaries to a CSV file with exact headers.
    """
    headers = ['stand_id', 'rotation_id', 'occupancy_start', 'occupancy_end', 'buffer_end', 'mode', 'reason']
    
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in data:
            writer.writerow(row)

# Test it
if __name__ == "__main__":
    commands = process_commands('data/commands.txt')
    print(f"Loaded {len(commands)} commands.")
    # Print the first 3 commands just to see them
    for cmd in commands[:3]:
        print(cmd)