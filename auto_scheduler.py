"""שיבוץ אוטומטי של תגבורים בשעות פנויות של שתי הכיתות (שנה א' + שנה ב') באותה מגמה.

חוקים:
- רק בימים ששתי הכיתות לומדות (אם כיתה אחת לא לומדת באותו יום – לא לשבץ).
- חלון השיבוץ עד 20:00 בערב, מ-08:00 בבוקר.
- שיבוץ באורך 60 דקות לפחות.
- באוניברסיטת אריאל: עדיפות לשיבוץ ב-08:00-09:00 (לפני שיעורי שתי הכיתות).
- אסור שסטודנט יקבל שני תגבורים בו זמנית עם מתגברים שונים.
"""
from __future__ import annotations

import json
import os
from typing import Any

import config

CLASS_SCHEDULES_FILE = os.path.join(os.path.dirname(__file__), "class_schedules.json")

DAY_START_MIN = 8 * 60      # 08:00
DAY_END_MIN = 20 * 60       # 20:00
SLOT_LEN_MIN = 60           # default lesson length
ARIEL_INSTITUTION = "אוניברסיטת אריאל"
ARIEL_PREFERRED = (8 * 60, 9 * 60)


def _to_min(t: str) -> int:
    """Convert 'HH:MM' to minutes since midnight."""
    if not t:
        return 0
    parts = t.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def _to_hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def _merge(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping (start_min, end_min) intervals."""
    if not intervals:
        return []
    intervals = sorted(intervals)
    merged = [intervals[0]]
    for s, e in intervals[1:]:
        ls, le = merged[-1]
        if s <= le:
            merged[-1] = (ls, max(le, e))
        else:
            merged.append((s, e))
    return merged


def _free_slots(busy: list[tuple[int, int]],
                window_start: int = DAY_START_MIN,
                window_end: int = DAY_END_MIN) -> list[tuple[int, int]]:
    """Return free intervals (>= 1 minute) within [window_start, window_end]."""
    merged = _merge([(max(s, window_start), min(e, window_end))
                     for s, e in busy if e > window_start and s < window_end])
    free: list[tuple[int, int]] = []
    cursor = window_start
    for s, e in merged:
        if s > cursor:
            free.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < window_end:
        free.append((cursor, window_end))
    return free


def load_class_schedules() -> dict[str, Any]:
    if not os.path.exists(CLASS_SCHEDULES_FILE):
        return {}
    with open(CLASS_SCHEDULES_FILE, encoding="utf-8") as f:
        return json.load(f)


def _track_busy_per_day(class_schedules: dict, institution: str, track: str) -> dict[str, dict[str, list[tuple[int, int]]]]:
    """For an institution/track, return {day: {year: [(start_min,end_min)...]}} for each year that has events."""
    track_data = class_schedules.get(institution, {}).get(track, {})
    if not isinstance(track_data, dict):
        return {}
    out: dict[str, dict[str, list[tuple[int, int]]]] = {}
    for year, events in track_data.items():
        if not isinstance(events, list):
            continue
        for ev in events:
            day = ev.get("day")
            s = _to_min(ev.get("start", ""))
            e = _to_min(ev.get("end", ""))
            if not day or e <= s:
                continue
            out.setdefault(day, {}).setdefault(year, []).append((s, e))
    return out


def _student_busy(weekly_schedule: list[dict], tutor_to_students: dict[str, list[str]]) -> dict[str, dict[str, list[tuple[int, int]]]]:
    """Return {student_name: {day: [busy intervals from existing tutoring]}}."""
    out: dict[str, dict[str, list[tuple[int, int]]]] = {}
    for slot in weekly_schedule:
        day = slot.get("day", "")
        s = _to_min(slot.get("start", ""))
        e = _to_min(slot.get("end", ""))
        if not day or e <= s:
            continue
        students = tutor_to_students.get(slot.get("tutor", ""), [])
        for st in students:
            out.setdefault(st, {}).setdefault(day, []).append((s, e))
    return out


def _tutor_existing_busy(weekly_schedule: list[dict], tutor_name: str) -> dict[str, list[tuple[int, int]]]:
    busy: dict[str, list[tuple[int, int]]] = {}
    for slot in weekly_schedule:
        if slot.get("tutor") != tutor_name:
            continue
        day = slot.get("day", "")
        s = _to_min(slot.get("start", ""))
        e = _to_min(slot.get("end", ""))
        if day and e > s:
            busy.setdefault(day, []).append((s, e))
    return busy


def _subject_groups(tutor: dict) -> list[tuple[str, list[str]]]:
    """Return list of (subject, students) groups for this tutor.

    If per-student mapping exists, group students by subject. Students without
    an explicit mapping inherit the default subject. If actual_subject contains
    multiple comma-separated subjects, each becomes its own group (using all
    unmapped students). If only a single subject is taught — return one group.
    """
    prob_students = tutor.get("probation_students", [])
    reg_students = tutor.get("regular_students", [])
    all_students = list(prob_students) + list(reg_students)
    if not all_students:
        return []
    ss = tutor.get("student_subjects", {}) or {}
    rs = tutor.get("regular_subjects", {}) or {}
    # Merge both subject mappings
    combined_ss = {**ss, **rs}
    actual = (tutor.get("actual_subject") or "").strip()
    default_subjects = [s.strip() for s in actual.split(",") if s.strip()]
    if not default_subjects:
        default_subjects = tutor.get("subjects", []) or [""]

    # If we have explicit per-student mappings, build per-subject groups from them
    groups: dict[str, list[str]] = {}
    unmapped: list[str] = []
    for st in all_students:
        subj = combined_ss.get(st)
        if subj:
            groups.setdefault(subj, []).append(st)
        else:
            unmapped.append(st)

    if groups:
        # Distribute unmapped students across the default_subjects (one lesson per default subject).
        # If there's only one default subject, all unmapped go there.
        if unmapped:
            if len(default_subjects) <= 1:
                target = default_subjects[0] if default_subjects else next(iter(groups))
                groups.setdefault(target, []).extend(unmapped)
            else:
                for subj in default_subjects:
                    groups.setdefault(subj, []).extend(unmapped)
        return list(groups.items())

    # No per-student mapping: one lesson per default subject (all students together)
    if len(default_subjects) > 1:
        return [(subj, list(all_students)) for subj in default_subjects]
    return [(default_subjects[0] if default_subjects else "", list(all_students))]


def suggest_for_tutor(
    tutor: dict,
    class_schedules: dict,
    weekly_schedule: list[dict],
    tutor_to_students: dict[str, list[str]],
    slot_len: int = SLOT_LEN_MIN,
) -> list[dict]:
    """Suggest weekly slots for the tutor — one per subject they teach. Returns list."""
    institution = tutor.get("institution", "")
    track = tutor.get("track", "")
    if not institution or not track:
        return []
    groups = _subject_groups(tutor)
    if not groups:
        return []

    track_busy = _track_busy_per_day(class_schedules, institution, track)
    if not track_busy:
        return []

    is_ariel = institution.strip() == ARIEL_INSTITUTION
    # Working copy of weekly so subsequent subject slots avoid earlier ones
    working = list(weekly_schedule)
    suggestions: list[dict] = []

    for subject, subj_students in groups:
        if not subj_students:
            continue
        # Recompute busy maps each iteration so we incorporate earlier subjects
        student_busy_map = _student_busy(working, tutor_to_students)
        tutor_busy = _tutor_existing_busy(working, tutor.get("name", ""))

        # Collect all candidate (day, start, end, score) across the week, then pick the best.
        candidates: list[tuple[int, str, int, int]] = []  # (score, day, start_min, end_min)

        for day in config.WEEKDAYS:
            years_today = track_busy.get(day, {})
            if len(years_today) < 2:
                continue
            combined: list[tuple[int, int]] = []
            for ivs in years_today.values():
                combined.extend(ivs)
            combined.extend(tutor_busy.get(day, []))
            for st in subj_students:
                combined.extend(student_busy_map.get(st, {}).get(day, []))

            free = _free_slots(combined, DAY_START_MIN, DAY_END_MIN)
            if not free:
                continue

            # Ariel 08:00-09:00 preference — if available and both years start ≥ 09:00, score it best.
            if is_ariel:
                earliest_class = min(min(s for s, _ in ivs) for ivs in years_today.values())
                pref_s, pref_e = ARIEL_PREFERRED
                if earliest_class >= pref_e:
                    # Check the 8-9 window is fully inside a free interval
                    inside = any(s <= pref_s and e >= pref_e for s, e in free)
                    if inside:
                        candidates.append((0, day, pref_s, pref_e))

            for s, e in free:
                if e - s < slot_len:
                    continue
                start_min = s
                end_min = s + slot_len
                # Convenience score: prefer mid-day; heavy penalty for evening (>=18:00),
                # mild penalty for very early (<09:00) when not Ariel.
                score = start_min
                if start_min >= 18 * 60:
                    score += 10000
                elif start_min < 9 * 60 and not is_ariel:
                    score += 5000
                candidates.append((score, day, start_min, end_min))

        if not candidates:
            continue
        candidates.sort(key=lambda c: c[0])
        _, day, s_min, e_min = candidates[0]
        slot = {
            "tutor": tutor["name"],
            "day": day,
            "start": _to_hhmm(s_min),
            "end": _to_hhmm(e_min),
            "subject": subject,
            "notes": "שובץ אוטומטית",
        }
        suggestions.append(slot)
        working.append(slot)

    return suggestions


def suggest_all(tutors_registry: list[dict], weekly_schedule: list[dict],
                only_unscheduled: bool = True) -> list[dict]:
    """Suggest weekly slots for all tutors who need one.

    If only_unscheduled=True, skips tutors who already have a weekly slot.
    Each successful suggestion is immediately added to a local working copy of
    weekly_schedule so subsequent suggestions can avoid student/tutor conflicts.
    """
    class_schedules = load_class_schedules()
    tutor_to_students = {t["name"]: list(t.get("probation_students", [])) + list(t.get("regular_students", [])) for t in tutors_registry}
    # Set of (tutor, subject) pairs that already have a slot.
    existing_pairs: set[tuple[str, str]] = {
        (s["tutor"], (s.get("subject") or "").strip()) for s in weekly_schedule
    }

    working = list(weekly_schedule)
    suggestions: list[dict] = []
    for tutor in tutors_registry:
        if not tutor.get("probation_students") and not tutor.get("regular_students"):
            continue
        slots = suggest_for_tutor(tutor, class_schedules, working, tutor_to_students)
        for slot in slots:
            if only_unscheduled and (slot["tutor"], slot["subject"]) in existing_pairs:
                continue
            suggestions.append(slot)
            working.append(slot)
            existing_pairs.add((slot["tutor"], slot["subject"]))
    return suggestions
