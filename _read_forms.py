"""Read all form response tabs, deduplicate, cross-reference with existing data."""
import gspread
import json
import os
import config

client = gspread.service_account(filename=str(config.CREDENTIALS_PATH))
spreadsheet = client.open(config.SHEET_NAME)

# Map each tab to institution/track
tab_mapping = {
    "הרשמות - אריאל - מכונות": ("אוניברסיטת אריאל", "מכונות"),
    "הרשמות - אריאל - חשמל": ("אוניברסיטת אריאל", "הנדסת חשמל"),
    "הרשמות -  בראודה - חשמל": ("בראודה", "הנדסת חשמל"),
    "הרשמות - סמי שמעון - חשמל": ("סמי שמעון", "הנדסת חשמל"),
    "הרשמות - סמי שמעון - תעשייה וניהול": ("סמי שמעון", "תעשייה וניהול"),
    "הרשמות - סמי שמעון - תוכנה": ("סמי שמעון", "הנדסת תוכנה"),
}

all_registrations = []
for tab_name, (inst, track) in tab_mapping.items():
    ws = spreadsheet.worksheet(tab_name)
    rows = ws.get_all_values()
    if len(rows) <= 1:
        continue
    for r in rows[1:]:
        if not r[1].strip():
            continue
        all_registrations.append({
            "name": r[1].strip(),
            "id_num": r[2].strip(),
            "courses": r[3].strip(),
            "institution": inst,
            "track": track,
        })

# Deduplicate by (name, id_num) - keep latest
seen = {}
for reg in all_registrations:
    key = (reg["name"], reg["id_num"])
    seen[key] = reg  # last wins
deduped = list(seen.values())

print(f"Total registrations (raw): {len(all_registrations)}")
print(f"After dedup: {len(deduped)}")
print()

# Read existing probation students
ws_prob = spreadsheet.worksheet("על תנאי")
prob_rows = ws_prob.get_all_records()
probation_names = set()
for row in prob_rows:
    name = str(row.get("שם סטודנט", "")).strip()
    if name:
        probation_names.add(name)

# Read existing tutors registry
ws_tutors = spreadsheet.worksheet(config.TUTORS_TAB)
tutor_rows = ws_tutors.get_all_records()
tutor_probation_students = set()
for row in tutor_rows:
    raw = str(row.get("סטודנטים על-תנאי", ""))
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if ":" in chunk:
            chunk = chunk.split(":")[0].strip()
        elif "(" in chunk:
            chunk = chunk.split("(")[0].strip()
        if chunk:
            tutor_probation_students.add(chunk)

print(f"Probation students (על תנאי tab): {len(probation_names)}")
print(f"Probation students (in tutor records): {len(tutor_probation_students)}")
print()

# Cross reference
for r in deduped:
    is_probation = r["name"] in probation_names or r["name"] in tutor_probation_students
    tag = "על-תנאי" if is_probation else "רגיל"
    print(f"  [{tag}] {r['institution']} | {r['track']} | {r['name']} | {r['courses']}")

print()
print("=== Probation students NOT in form registrations ===")
form_names = {r["name"] for r in deduped}
for name in sorted(probation_names | tutor_probation_students):
    if name not in form_names:
        in_prob = "על-תנאי-tab" if name in probation_names else ""
        in_tutor = "tutor-record" if name in tutor_probation_students else ""
        print(f"  {name} ({in_prob} {in_tutor})")

# Also print tutors grouped by institution/track
print()
print("=== Tutors by institution/track ===")
for row in tutor_rows:
    name = str(row.get("שם מתגבר", "")).strip()
    inst = str(row.get("מוסד", "")).strip()
    track = str(row.get("מגמה", "")).strip()
    actual = str(row.get("מקצוע בפועל", "")).strip()
    prob = str(row.get("סטודנטים על-תנאי", "")).strip()
    print(f"  {inst} | {track} | {name} | actual={actual} | students={prob}")

# Read existing weekly schedule
print()
print("=== Weekly Schedule ===")
ws_sched = spreadsheet.worksheet(config.SCHEDULE_TAB)
sched_rows = ws_sched.get_all_records()
for row in sched_rows:
    tutor = str(row.get("שם מתגבר", "")).strip()
    day = str(row.get("יום", "")).strip()
    start = str(row.get("שעת התחלה", "")).strip()
    end = str(row.get("שעת סיום", "")).strip()
    subj = str(row.get("מקצוע", "")).strip()
    notes = str(row.get("הערות", "")).strip()
    print(f"  {tutor} | {day} {start}-{end} | {subj} | {notes}")
