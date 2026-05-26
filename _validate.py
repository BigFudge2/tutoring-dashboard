"""Validate tutor statistics and schedule consistency."""
from data_loader import load_tutors_registry, load_weekly_schedule, load_registrations

registry = load_tutors_registry()
weekly = load_weekly_schedule()
registrations = load_registrations()

print("=== TUTOR STATS ===")
total_prob = 0
total_reg = 0
tutors_with_students = 0
for t in registry:
    prob = t.get("probation_students", [])
    reg = t.get("regular_students", [])
    n = len(prob) + len(reg)
    total_prob += len(prob)
    total_reg += len(reg)
    if n > 0:
        tutors_with_students += 1
    print(f"  {t['name']}: {len(prob)} prob + {len(reg)} reg = {n} total")

print(f"\nTotal tutors: {len(registry)}")
print(f"Tutors with students: {tutors_with_students}")
print(f"Total probation assignments: {total_prob}")
print(f"Total regular assignments: {total_reg}")

print(f"\n=== SCHEDULE ===")
print(f"Total slots: {len(weekly)}")
scheduled_tutors = set(s["tutor"] for s in weekly)
print(f"Tutors in schedule: {len(scheduled_tutors)}")

# Check which tutors with students are NOT in schedule
print("\n--- Tutors with students NOT in schedule ---")
found_missing = False
for t in registry:
    n = len(t.get("probation_students", [])) + len(t.get("regular_students", []))
    if n > 0 and t["name"] not in scheduled_tutors:
        print(f"  MISSING: {t['name']} ({n} students)")
        found_missing = True
if not found_missing:
    print("  None! All tutors with students are scheduled.")

print("\n=== REGISTRATIONS ===")
print(f"Total registrations from forms: {len(registrations)}")

# Check students from forms who aren't assigned to any tutor
all_assigned_prob = set()
all_assigned_reg = set()
for t in registry:
    for s in t.get("probation_students", []):
        # Strip subject mapping (name might have ": subject")
        all_assigned_prob.add(s.split(":")[0].strip() if ":" in s else s)
    for s in t.get("regular_students", []):
        all_assigned_reg.add(s.split(":")[0].strip() if ":" in s else s)

all_assigned = all_assigned_prob | all_assigned_reg
unassigned = []
for r in registrations:
    if r["name"] not in all_assigned:
        unassigned.append(r)
print(f"Assigned to a tutor: {len(registrations) - len(unassigned)}")
print(f"NOT assigned to any tutor: {len(unassigned)}")
for u in unassigned:
    print(f"  {u['name']} ({u['institution']}/{u['track']}): {u['courses']}")
