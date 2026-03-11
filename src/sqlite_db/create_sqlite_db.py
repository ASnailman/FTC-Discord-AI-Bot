import sqlite3
import json

def initialize_database():
    conn = sqlite3.connect('ftc_data.db')
    cursor = conn.cursor()

    # Create the core Teams table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS teams (
        team_number INTEGER PRIMARY KEY,
        team_name TEXT,
        # region TEXT,
        # rookie_year INTEGER,
        # auto_points REAL,
        # teleop_points REAL,
        # opr REAL
    )
    ''')

    # add later (maybe)
        # region TEXT,
        # rookie_year INTEGER,
        # auto_points REAL,
        # teleop_points REAL,
        # opr REAL
    
    conn.commit()
    print("SQLite database 'ftc_data.db' and 'teams' table created!")

    try:
        with open('output_names.json', 'r') as file:
            teams_data = json.load(file)
                    
        # Insert or ignore prevents errors if you run the script twice
        for name, number in teams_data.items():
            cursor.execute('''
            INSERT OR IGNORE INTO teams (team_number, team_name)
            VALUES (?, ?)
            ''', (int(number), name))
            
        conn.commit()
        print("Basic team numbers and names populated!")
        
    except FileNotFoundError:
        print("output_names.json not found, skipping population.")
    conn.close()

if __name__ == "__main__":
    initialize_database()