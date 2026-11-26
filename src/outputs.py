import csv

def write_gate_plan(filename, data):
    """Writes gate_plan.csv with exact headers."""
    headers = ['stand_id', 'rotation_id', 'occupancy_start', 'occupancy_end', 'buffer_end', 'mode', 'reason']
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in data:
            if row.get('assigned_stand'):
                writer.writerow({
                    'stand_id': row['assigned_stand'],
                    'rotation_id': row['rotation_id'],
                    'occupancy_start': row['occupancy_start'],
                    'occupancy_end': row['occupancy_end'],
                    'buffer_end': row['buffer_end'],
                    'mode': row['mode'],
                    'reason': row['reason']
                })

def write_slot_bins(filename, data):
    """Writes slot_bins.csv with exact headers."""
    headers = ['bin_start', 'arrivals', 'departures', 'total', 'pushed_in', 'pushed_out']
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in data:
            writer.writerow(row)

def write_task_schedule(filename, data):
    """Writes task_schedule.csv with exact headers."""
    headers = ['rotation_id', 'task', 'team_id', 'start_ts', 'end_ts', 'delay_min']
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in data:
            writer.writerow(row)

def write_charges(filename, data):
    """Writes charges.csv with exact headers."""
    headers = ['airline_code', 'rotation_id', 'charge_code', 'quantity', 'rate', 'amount']
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in data:
            writer.writerow(row)