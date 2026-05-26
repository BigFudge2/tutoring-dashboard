from data_loader import load_tutors_registry, load_weekly_schedule

registry = load_tutors_registry()
weekly = load_weekly_schedule()

print("=== Ariel Chashmal tutors ===")
for t in registry:
    if t["institution"] == "אוניברסיטת אריאל" and t["track"] == "חשמל":
        prob = t.get("probation_students", [])
        ss = t.get("student_subjects", {})
        print(f"  {t['name']} | actual={t['actual_subject']}")
        print(f"    probation: {prob}")
        print(f"    student_subjects: {ss}")
        print()

print("=== Schedule for Ariel Chashmal ===")
ariel_tutors = {t["name"] for t in registry if t["institution"] == "אוניברסיטת אריאל" and t["track"] == "חשמל"}
for s in weekly:
    if s["tutor"] in ariel_tutors:
        print(f"  {s['tutor']} | {s['day']} {s['start']}-{s['end']} | {s['subject']}")

# Check if אורן אוחיון appears in multiple tutors
print("\n=== אורן אוחיון assignments ===")
for t in registry:
    prob = t.get("probation_students", [])
    reg = t.get("regular_students", [])
    if "אורן אוחיון" in prob or "אורן אוחיון" in reg:
        ss = t.get("student_subjects", {})
        rs = t.get("regular_subjects", {})
        subj = ss.get("אורן אוחיון") or rs.get("אורן אוחיון") or t.get("actual_subject", "")
        which = "probation" if "אורן אוחיון" in prob else "regular"
        print(f"  {t['name']} ({t['institution']}/{t['track']}) - {which} - subject: {subj}")
