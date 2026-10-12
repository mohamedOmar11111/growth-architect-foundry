import sqlite3
import os

def verify():
    db_path = 'hq.db'
    if not os.path.exists(db_path):
        print("FAIL: hq.db not found.")
        exit(1)
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check Squads
    cursor.execute("SELECT count(*) FROM squads")
    squad_count = cursor.fetchone()[0]
    if squad_count != 11:
        print(f"FAIL: Expected 11 squads, found {squad_count}")
        exit(1)

    # Check Agents
    cursor.execute("SELECT count(*) FROM agents")
    agent_count = cursor.fetchone()[0]
    if agent_count != 29:
        print(f"FAIL: Expected 29 agents, found {agent_count}")
        exit(1)
        
    print(f"SUCCESS: Kernel verified. {squad_count} squads and {agent_count} agents active.")
    conn.close()

if __name__ == "__main__":
    verify()
