import sys
import json
import sqlite3

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def verify():
    with open("data/schemes_seed.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"Total schemes in seed: {len(data)}")
    with_process = [s for s in data if s.get("application_process")]
    print(f"Schemes with application_process: {len(with_process)}/{len(data)}")
    
    print("\n--- SAMPLE SCHEMES AND APPLICATION PROCESSES ---")
    for s in data[:5]:
        print(f"\nScheme: {s['scheme_name']} ({s['scheme_short_code']})")
        print(f"Mode: {s.get('application_mode')}")
        print(f"Portal: {s.get('official_portal_url')}")
        print(f"Steps count: {len(s.get('application_process', []))}")
        print("Sample steps:")
        for step in s.get("application_process", [])[:3]:
            print(f"  * {step}")

    # Check SQLite DB
    conn = sqlite3.connect("data/schemes_knowledge.db")
    c = conn.cursor()
    c.execute("SELECT scheme_id, full_json FROM schemes")
    rows = c.fetchall()
    db_with_process = 0
    for r in rows:
        j = json.loads(r[1])
        if j.get("application_process"):
            db_with_process += 1
    print(f"\nSQLite DB schemes with application_process: {db_with_process}/{len(rows)}")

if __name__ == "__main__":
    verify()
