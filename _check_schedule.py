from data_loader import load_tutors_registry, load_weekly_schedule
from auto_scheduler import suggest_all

registry = load_tutors_registry()
weekly = load_weekly_schedule()

missing = ['ליאם אבן חיים', 'איליי אלעזר דהן']
for t in registry:
    if t['name'] in missing:
        print(f"{t['name']}:")
        print(f"  institution={t['institution']}")
        print(f"  track={t['track']}")
        print(f"  actual_subject={t.get('actual_subject', '')}")
        print(f"  regular_students={t.get('regular_students', [])}")
        print(f"  regular_subjects={t.get('regular_subjects', {})}")
        print()

suggestions = suggest_all(registry, weekly, only_unscheduled=True)
print("=== Suggestions ===")
for s in suggestions:
    print(s)
