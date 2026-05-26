"""
Assign form registrations to tutors.
- Reads all 6 form response tabs
- Cross-references with probation list and existing tutor assignments
- Adds a "סטודנטים רגילים" column (col I) to מתגברים
- Updates probation student lists for probation students not yet assigned
- Assigns regular students to matching tutors
"""
import gspread
import time as _time
import config

client = gspread.service_account(filename=str(config.CREDENTIALS_PATH))
spreadsheet = client.open(config.SHEET_NAME)

# ── 1. Read form tabs ──────────────────────────────────────────────
TAB_MAP = {
    "הרשמות - אריאל - מכונות":              ("אוניברסיטת אריאל", "מכונות"),
    "הרשמות - אריאל - חשמל":               ("אוניברסיטת אריאל", "חשמל"),
    "הרשמות -  בראודה - חשמל":             ("בראודה", "חשמל"),
    "הרשמות - סמי שמעון - חשמל":           ("סמי שמעון", "חשמל"),
    "הרשמות - סמי שמעון - תעשייה וניהול":   ("סמי שמעון", "תעשייה וניהול"),
    "הרשמות - סמי שמעון - תוכנה":          ("סמי שמעון", "תוכנה"),
}

# Subject aliases (form spelling → tutor record spelling)
SUBJECT_ALIAS = {
    "אלגברה לינרית": "אלגברה לינארית",
    "שפת סי": "שפת C",
    "אנליזה": "אנליזה",
}

def norm_subj(s):
    s = s.strip()
    return SUBJECT_ALIAS.get(s, s)

all_regs = []
for tab_name, (inst, track) in TAB_MAP.items():
    ws = spreadsheet.worksheet(tab_name)
    rows = ws.get_all_values()
    for r in rows[1:]:
        name = r[1].strip()
        if not name:
            continue
        courses = [norm_subj(c) for c in r[3].split(",") if c.strip()]
        all_regs.append({"name": name, "id_num": r[2].strip(),
                         "courses": courses, "institution": inst, "track": track})

# Deduplicate by (name, id_num) — keep latest
seen = {}
for reg in all_regs:
    key = (reg["name"], reg["id_num"])
    seen[key] = reg
regs = list(seen.values())
print(f"Total unique registrations: {len(regs)}")

# ── 2. Read probation list ─────────────────────────────────────────
ws_prob = spreadsheet.worksheet("על תנאי")
prob_names = set()
for row in ws_prob.get_all_records():
    n = str(row.get("שם סטודנט", "")).strip()
    if n:
        prob_names.add(n)

# ── 3. Read tutor registry ─────────────────────────────────────────
ws_tutors = spreadsheet.worksheet(config.TUTORS_TAB)
tutor_records = ws_tutors.get_all_records()
tutor_rows_raw = ws_tutors.get_all_values()  # for row indices

tutors = []
for i, row in enumerate(tutor_records):
    name = str(row.get("שם מתגבר", "")).strip()
    if not name:
        continue
    actual_raw = str(row.get("מקצוע בפועל", "")).strip()
    actual_subjects = [s.strip() for s in actual_raw.split(",") if s.strip()]
    prob_raw = str(row.get("סטודנטים על-תנאי", "")).strip()
    prob_students = []
    for chunk in prob_raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" in chunk:
            chunk = chunk.split(":")[0].strip()
        elif "(" in chunk:
            chunk = chunk.split("(")[0].strip()
        prob_students.append(chunk)
    tutors.append({
        "name": name,
        "institution": str(row.get("מוסד", "")).strip(),
        "track": str(row.get("מגמה", "")).strip(),
        "actual_subjects": actual_subjects,
        "prob_students": prob_students,
        "prob_raw": prob_raw,
        "sheet_row": i + 2,  # 1-indexed, +1 for header
    })

# ── 4. Match registrations to tutors ───────────────────────────────
# For each (institution, track, subject) find matching tutors
def find_tutors(inst, track, subject):
    """Find tutors matching institution, track, and subject."""
    matches = []
    for t in tutors:
        if t["institution"] != inst:
            continue
        if t["track"] != track:
            continue
        if subject in t["actual_subjects"]:
            matches.append(t)
    return matches

# Build assignment plan
new_probation_assignments = []  # (tutor, student_name, subject)
new_regular_assignments = []    # (tutor, student_name, subject)
unmatched = []

for reg in regs:
    is_prob = reg["name"] in prob_names
    for course in reg["courses"]:
        matching_tutors = find_tutors(reg["institution"], reg["track"], course)
        if not matching_tutors:
            unmatched.append((reg["name"], reg["institution"], reg["track"], course, is_prob))
            continue
        # Pick the tutor with fewest students for load balancing
        best = min(matching_tutors, key=lambda t: len(t["prob_students"]))
        if is_prob:
            if reg["name"] not in best["prob_students"]:
                new_probation_assignments.append((best, reg["name"], course))
        else:
            new_regular_assignments.append((best, reg["name"], course))

# ── 5. Print assignment plan ───────────────────────────────────────
print("\n=== NEW PROBATION ASSIGNMENTS (על תנאי not yet assigned) ===")
for tutor, student, subject in new_probation_assignments:
    print(f"  {tutor['name']} ← {student} ({subject})")

print(f"\n=== REGULAR STUDENT ASSIGNMENTS ({len(new_regular_assignments)}) ===")
for tutor, student, subject in new_regular_assignments:
    print(f"  {tutor['name']} ← {student} ({subject})")

print(f"\n=== UNMATCHED ({len(unmatched)}) ===")
for name, inst, track, course, is_prob in unmatched:
    tag = "על-תנאי" if is_prob else "רגיל"
    print(f"  [{tag}] {name} @ {inst}/{track} wants {course} — NO TUTOR FOUND")

# ── 6. Build updates ──────────────────────────────────────────────
# Group by tutor
from collections import defaultdict

tutor_new_prob = defaultdict(set)   # tutor_name → set of new probation students
tutor_regulars = defaultdict(set)   # tutor_name → set of regular students

for tutor, student, subject in new_probation_assignments:
    tutor_new_prob[tutor["name"]].add(f"{student}: {subject}")

for tutor, student, subject in new_regular_assignments:
    tutor_regulars[tutor["name"]].add(f"{student}: {subject}")

print("\n=== SHEET UPDATES PLAN ===")
for t in tutors:
    changes = []
    if t["name"] in tutor_new_prob:
        changes.append(f"  +probation: {tutor_new_prob[t['name']]}")
    if t["name"] in tutor_regulars:
        changes.append(f"  +regular: {tutor_regulars[t['name']]}")
    if changes:
        print(f"\n{t['name']} (row {t['sheet_row']}):")
        for c in changes:
            print(c)

# ── 7. Apply updates ──────────────────────────────────────────────
print("\n\nApplying updates to Google Sheets...")

# First, add "סטודנטים רגילים" header if not present
headers = ws_tutors.row_values(1)
if "סטודנטים רגילים" not in headers:
    col_idx = len(headers) + 1
    # Resize sheet if needed
    if ws_tutors.col_count < col_idx:
        ws_tutors.resize(cols=col_idx)
        print(f"Resized sheet to {col_idx} columns")
        _time.sleep(2)
    ws_tutors.update_cell(1, col_idx, "סטודנטים רגילים")
    print(f"Added 'סטודנטים רגילים' header at column {col_idx}")
    _time.sleep(2)

# Re-read headers to get correct column index
headers = ws_tutors.row_values(1)
reg_col_idx = headers.index("סטודנטים רגילים") + 1  # 1-indexed
prob_col_idx = headers.index("סטודנטים על-תנאי") + 1

update_count = 0
for t in tutors:
    # Update probation column if new students
    if t["name"] in tutor_new_prob:
        existing = t["prob_raw"]
        new_entries = tutor_new_prob[t["name"]]
        if existing:
            updated = existing + ", " + ", ".join(sorted(new_entries))
        else:
            updated = ", ".join(sorted(new_entries))
        ws_tutors.update_cell(t["sheet_row"], prob_col_idx, updated)
        print(f"  Updated probation for {t['name']}: +{len(new_entries)} students")
        update_count += 1
        if update_count % 10 == 0:
            print("  (cooling down 30s for API quota...)")
            _time.sleep(30)
        else:
            _time.sleep(2)

    # Update regular students column
    if t["name"] in tutor_regulars:
        entries = tutor_regulars[t["name"]]
        # Read existing value in that cell
        try:
            existing = ws_tutors.cell(t["sheet_row"], reg_col_idx).value or ""
        except Exception:
            existing = ""
        if existing:
            updated = existing + ", " + ", ".join(sorted(entries))
        else:
            updated = ", ".join(sorted(entries))
        ws_tutors.update_cell(t["sheet_row"], reg_col_idx, updated)
        print(f"  Updated regulars for {t['name']}: +{len(entries)} students")
        update_count += 1
        if update_count % 10 == 0:
            print("  (cooling down 30s for API quota...)")
            _time.sleep(30)
        else:
            _time.sleep(2)

print(f"\nDone! {update_count} cells updated.")
