"""טעינת נתונים מ-Google Sheets ופירסור שלהם."""
from __future__ import annotations

import json
import os
from datetime import datetime, time
from typing import Any

import gspread
import pandas as pd

import config


# שמות העמודות הצפויים (בדיוק כפי שהמתגברים רואים בטופס)
COL_TIMESTAMP = "Timestamp"
COL_TUTOR = "שם מתגבר"
COL_DATE = "תאריך שיעור"
COL_START = "שעת התחלה"
COL_END = "שעת סיום"
COL_STUDENTS = "שמות סטודנטים שנכחו"
COL_TOPIC = "נושא השיעור"
COL_RATING = "איך היה השיעור?"
COL_NOTES = "הערות"


# מילות מפתח לזיהוי אוטומטי של עמודות (אם השם בטופס שונה מהצפוי)
_COLUMN_KEYWORDS: dict[str, list[str]] = {
    COL_TIMESTAMP: ["timestamp", "חותמת"],
    COL_TUTOR: ["מתגבר"],
    COL_DATE: ["תאריך"],
    COL_START: ["התחלה", "start"],
    COL_END: ["סיום", "end"],
    COL_STUDENTS: ["סטודנט", "תלמיד", "נכח"],
    COL_TOPIC: ["נושא"],
    COL_RATING: ["דירוג", "איך היה", "ציון"],
    COL_NOTES: ["הערה", "הערות", "notes"],
}


def _find_column(actual_columns: list[str], canonical: str) -> str | None:
    """מחזיר את שם העמודה האמיתי בגיליון שמתאים לעמודה הקנונית."""
    if canonical in actual_columns:
        return canonical
    keywords = _COLUMN_KEYWORDS.get(canonical, [])
    for col in actual_columns:
        col_lower = str(col).lower()
        for kw in keywords:
            if kw.lower() in col_lower:
                return col
    return None


def _rename_to_canonical(df: pd.DataFrame) -> pd.DataFrame:
    """ממפה שמות עמודות בפועל לשמות הקנוניים בקוד."""
    rename_map: dict[str, str] = {}
    actual = list(df.columns)
    for canonical in _COLUMN_KEYWORDS:
        found = _find_column(actual, canonical)
        if found and found != canonical:
            rename_map[found] = canonical
    return df.rename(columns=rename_map)


def _get_client() -> gspread.Client:
    # ב-Render: משתמשים במשתנה סביבה GOOGLE_CREDENTIALS (JSON כ-string)
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if creds_json:
        return gspread.service_account_from_dict(json.loads(creds_json))
    # פיתוח מקומי: קובץ JSON
    return gspread.service_account(filename=str(config.CREDENTIALS_PATH))


def _parse_time(value: Any) -> time | None:
    if value is None or value == "":
        return None
    if isinstance(value, time):
        return value
    s = str(value).strip()
    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M:%S %p"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    return None


def _duration_hours(start: time | None, end: time | None) -> float | None:
    if start is None or end is None:
        return None
    start_minutes = start.hour * 60 + start.minute
    end_minutes = end.hour * 60 + end.minute
    diff = end_minutes - start_minutes
    if diff < 0:
        diff += 24 * 60
    return round(diff / 60, 2)


def _split_students(value: Any) -> list[str]:
    if not value:
        return []
    text = str(value)
    # פיצול לפי פסיק, פסיק עברי, נקודה-פסיק, מעבר שורה
    separators = [",", "،", ";", "\n", "|"]
    for sep in separators[1:]:
        text = text.replace(sep, ",")
    names = [n.strip() for n in text.split(",")]
    return [n for n in names if n]


def load_data() -> pd.DataFrame:
    """קורא את הגיליון ומחזיר DataFrame מעובד."""
    client = _get_client()
    spreadsheet = client.open(config.SHEET_NAME)
    worksheet_name = getattr(config, "WORKSHEET_NAME", None)
    if worksheet_name:
        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            # נופל חזרה לטאב הראשון אם השם לא נמצא
            worksheet = spreadsheet.get_worksheet(0)
    else:
        worksheet = spreadsheet.get_worksheet(0)
    records = worksheet.get_all_records()

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df = _rename_to_canonical(df)

    # פירסור תאריך
    if COL_DATE in df.columns:
        df[COL_DATE] = pd.to_datetime(df[COL_DATE], errors="coerce", dayfirst=True)

    # פירסור שעות וחישוב משך
    if COL_START in df.columns and COL_END in df.columns:
        df["_start_time"] = df[COL_START].apply(_parse_time)
        df["_end_time"] = df[COL_END].apply(_parse_time)
        df["משך (שעות)"] = df.apply(
            lambda r: _duration_hours(r["_start_time"], r["_end_time"]), axis=1
        )

    # פיצול סטודנטים לרשימה
    if COL_STUDENTS in df.columns:
        df["_students_list"] = df[COL_STUDENTS].apply(_split_students)
        df["מספר סטודנטים"] = df["_students_list"].apply(len)

    # דירוג כמספר
    if COL_RATING in df.columns:
        df[COL_RATING] = pd.to_numeric(df[COL_RATING], errors="coerce")

    # מיון לפי תאריך אם קיים
    if COL_DATE in df.columns:
        df = df.sort_values(COL_DATE, ascending=False).reset_index(drop=True)

    return df


def get_unique_tutors(df: pd.DataFrame) -> list[str]:
    if df.empty or COL_TUTOR not in df.columns:
        return []
    return sorted(df[COL_TUTOR].dropna().unique().tolist())


def get_unique_students(df: pd.DataFrame) -> list[str]:
    if df.empty or "_students_list" not in df.columns:
        return []
    all_students: set[str] = set()
    for lst in df["_students_list"]:
        all_students.update(lst)
    return sorted(all_students)


# רשימת סטודנטים קבועה (מאגר ידוע מראש)
KNOWN_STUDENTS: list[str] = [
    "ויאאם אבו עביד",
    "ראווי אל חסיסי",
    "יוסף אלון",
    "אוריה אברהם",
    "אלמוג הבטמו בלאי",
    "אוריאל אדלר",
    "נאור ניסים אמר",
    "יאיר אוסמו",
    "מאיה פקדו",
    "תהל צאייהות סולומון",
    "אורן אוחיון",
    "אילון יצחק כהן",
    "אריאל ענבר",
    "אריאל מנחם שטרית",
    "ברוך מרדכי מעהל",
    "דניאל זאב",
    "ליאור שפירו",
    "רוני אורמן",
    "שי לי ברנשטיין",
    "יאיר אליצור",
    "לביא אוחנה",
    "נתנאל שמעון דעי",
    "אדוארד אפלביים",
    "יואב אלפסי",
    "עידן שניידר",
    "יהל הופמן",
    "עמית עמוס חדד",
    "הראל אינדפורקר",
    "ניצן אלגרבלי",
    "סהר אתגר",
    "אלכסנדר מטלניקוב",
    "אלעד מצה",
    "קארינה בלקיי",
    "קורן משה שיטרית",
    "רותם ויזל טל",
    "שחר מזרחי",
    "בן נמירובסקי",
    "בניה יוסף בן עמי",
    "יאיר בוחבוט",
    "שמעון יוסף אדלר",
    "ישי אליצור",
    "דביר כהן",
    "דוד אוסטרובסקי",
    "נעם אלמקייס",
    "דוד ברעם",
    "אדיר כמאל",
    "דניאל טרכטנברג",
    "ניתאי בטיטו",
    "שלי גוניק",
    "טוהר גוסלקר",
    "עידו גלוברמן",
    "שחר בן-סימון",
    "אבטיס גוקסיאן",
    "טוהר רון חזן",
    "שמעון און בן מוחה",
    "יאיר שיימן",
    "עומר יוסף דרמון",
    "יהונתן קן",
    "אביה נחום",
    "עדן גורן",
    "יובל חיזקיהו",
    "איתי סרוסי",
    "ינון אביב",
    "יהלי כהן",
    "מאור דוד הראוש",
    "שלו חסון שרגר",
    "נתנאל מושייב",
    "יפתח מזור",
    "ליאור חכמוב",
    "ליאל קסונקר",
    "ליאן עמרם",
    "ליה אבגי",
    "הדר צגאי",
    "לינוי מירון",
    "מאור לוי",
    "ולדיסלבה נוביקוב",
    "אמיר הופמן",
    "מיה איטקין",
    "ליה יופה",
    "יבגני ניקונוב",
    "עילאי צרפתי",
    "נועה סול רחל אבוטבול",
    "ניב לנקרי",
    "דן נירמן",
    "יעל כלפון",
    "מעיין עטיה",
    "אלחנן פזואלו",
    "אושרי מהרט",
    "סילין גרינברג",
    "אלין מושייב",
    "עידן לובטון",
    "מילנה ניאזוב",
    "בר פינצ'וק",
    "יקיר צנגאוקר",
    "דניאל קליינר",
    "עילאי אופיר",
    "יהונתן פינחס קוטנר",
    "עמית כהן",
    "דן קרייזל",
    "פורת פרץ חורי",
    "אלעד צדוק",
    "איתי קרן",
    "רביד דוד עטיה",
    "רואי כהן",
    "רום צורף",
    "עודד שבתאי",
    "רועי קסיס",
    "שחר לוי",
    "איתי שמלץ",
    "אריה צ'רנובילסקי",
    "אלסה קאסה",
    "אלי רדינסקי",
    "גיא שטרית",
    "ווס שאגום",
]


def get_all_students(df: pd.DataFrame) -> list[str]:
    """מחזיר רשימת סטודנטים ממוזגת: מאגר קבוע + סטודנטים מהגיליון."""
    all_students = set(KNOWN_STUDENTS)
    all_students.update(get_unique_students(df))
    return sorted(all_students)


def load_probation_students() -> list[dict[str, Any]]:
    """קורא את טאב 'על תנאי' מהגיליון ומחזיר רשימת סטודנטים על תנאי."""
    try:
        client = _get_client()
        spreadsheet = client.open(config.SHEET_NAME)
        worksheet = spreadsheet.worksheet("על תנאי")
    except (gspread.exceptions.WorksheetNotFound, Exception):
        return []

    records = worksheet.get_all_records()
    if not records:
        return []

    result = []
    for row in records:
        name = str(row.get("שם סטודנט", "")).strip()
        if not name:
            continue
        result.append({
            "name": name,
            "reason": str(row.get("סיבה", "")).strip(),
            "institution": str(row.get("מוסד", "")).strip(),
            "track": str(row.get("מגמה", "")).strip(),
            "start_date": str(row.get("תאריך התחלה", "")).strip(),
            "min_lessons": int(row.get("מינימום שיעורים בחודש", 0) or 0),
            "notes": str(row.get("הערות", "")).strip(),
        })
    return result


def append_probation_student(student: dict[str, str]) -> None:
    """מוסיף סטודנט על תנאי לטאב 'על תנאי' בגיליון."""
    client = _get_client()
    spreadsheet = client.open(config.SHEET_NAME)
    try:
        worksheet = spreadsheet.worksheet("על תנאי")
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title="על תנאי", rows=100, cols=7)
        worksheet.append_row(["שם סטודנט", "סיבה", "מוסד", "מגמה", "תאריך התחלה", "מינימום שיעורים בחודש", "הערות"],
                             value_input_option="USER_ENTERED")

    headers = worksheet.row_values(1)
    new_row = [student.get(h, "") for h in headers]
    worksheet.append_row(new_row, value_input_option="USER_ENTERED")


def remove_probation_student(student_name: str) -> bool:
    """מסיר סטודנט מטאב 'על תנאי'. מחזיר True אם נמצא ונמחק."""
    client = _get_client()
    spreadsheet = client.open(config.SHEET_NAME)
    try:
        worksheet = spreadsheet.worksheet("על תנאי")
    except gspread.exceptions.WorksheetNotFound:
        return False

    cell = worksheet.find(student_name, in_column=1)
    if cell:
        worksheet.delete_rows(cell.row)
        return True
    return False


# ---------- מתגברים (Tutor Registry) ----------

def _open_tab(tab_name: str) -> gspread.Worksheet:
    """פותח טאב ספציפי בגיליון. יוצר אם לא קיים."""
    client = _get_client()
    spreadsheet = client.open(config.SHEET_NAME)
    try:
        return spreadsheet.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
        raise


def load_tutors_registry() -> list[dict[str, Any]]:
    """קורא את טאב 'מתגברים' ומחזיר רשימת מתגברים."""
    try:
        ws = _open_tab(config.TUTORS_TAB)
    except gspread.exceptions.WorksheetNotFound:
        return []
    records = ws.get_all_records()
    result = []
    for row in records:
        name = str(row.get("שם מתגבר", "")).strip()
        if not name:
            continue
        subjects_raw = str(row.get("מקצועות", ""))
        subjects = [s.strip() for s in subjects_raw.split(",") if s.strip()]
        probation_raw = str(row.get("סטודנטים על-תנאי", ""))
        probation = [s.strip() for s in probation_raw.split(",") if s.strip()]
        result.append({
            "name": name,
            "institution": str(row.get("מוסד", "")).strip(),
            "track": str(row.get("מגמה", "")).strip(),
            "subjects": subjects,
            "probation_students": probation,
            "phone": str(row.get("טלפון", "")).strip(),
            "notes": str(row.get("הערות", "")).strip(),
        })
    return result


def append_tutor(tutor: dict[str, Any]) -> None:
    """מוסיף מתגבר חדש לטאב 'מתגברים'."""
    client = _get_client()
    spreadsheet = client.open(config.SHEET_NAME)
    try:
        ws = spreadsheet.worksheet(config.TUTORS_TAB)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=config.TUTORS_TAB, rows=100, cols=7)
        ws.append_row(
            ["שם מתגבר", "מוסד", "מגמה", "מקצועות", "סטודנטים על-תנאי", "טלפון", "הערות"],
            value_input_option="USER_ENTERED",
        )

    subjects = ", ".join(tutor.get("subjects", [])) if isinstance(tutor.get("subjects"), list) else tutor.get("subjects", "")
    probation = ", ".join(tutor.get("probation_students", [])) if isinstance(tutor.get("probation_students"), list) else tutor.get("probation_students", "")
    new_row = [
        tutor.get("name", ""),
        tutor.get("institution", ""),
        tutor.get("track", ""),
        subjects,
        probation,
        tutor.get("phone", ""),
        tutor.get("notes", ""),
    ]
    ws.append_row(new_row, value_input_option="USER_ENTERED",
                  insert_data_option="INSERT_ROWS", table_range="A1")


def update_tutor(tutor_name: str, updated: dict[str, Any]) -> bool:
    """מעדכן פרטי מתגבר לפי שם. מחזיר True אם נמצא ועודכן."""
    try:
        ws = _open_tab(config.TUTORS_TAB)
    except gspread.exceptions.WorksheetNotFound:
        return False
    cell = ws.find(tutor_name, in_column=1)
    if not cell:
        return False
    subjects = ", ".join(updated.get("subjects", [])) if isinstance(updated.get("subjects"), list) else updated.get("subjects", "")
    probation = ", ".join(updated.get("probation_students", [])) if isinstance(updated.get("probation_students"), list) else updated.get("probation_students", "")
    row_values = [
        updated.get("name", tutor_name),
        updated.get("institution", ""),
        updated.get("track", ""),
        subjects,
        probation,
        updated.get("phone", ""),
        updated.get("notes", ""),
    ]
    ws.update(f"A{cell.row}:G{cell.row}", [row_values], value_input_option="USER_ENTERED")
    return True


def remove_tutor(tutor_name: str) -> bool:
    """מסיר מתגבר לפי שם. מחזיר True אם נמצא ונמחק."""
    try:
        ws = _open_tab(config.TUTORS_TAB)
    except gspread.exceptions.WorksheetNotFound:
        return False
    cell = ws.find(tutor_name, in_column=1)
    if cell:
        ws.delete_rows(cell.row)
        return True
    return False


def get_tutor_subjects(tutor_name: str) -> list[str]:
    """מחזיר רשימת מקצועות של מתגבר ספציפי."""
    registry = load_tutors_registry()
    for t in registry:
        if t["name"] == tutor_name:
            return t["subjects"]
    return []


# ---------- לוז שבועי (Weekly Schedule) ----------

def load_weekly_schedule() -> list[dict[str, Any]]:
    """קורא את טאב 'לוז שבועי' ומחזיר רשימת שיעורים קבועים."""
    try:
        ws = _open_tab(config.SCHEDULE_TAB)
    except gspread.exceptions.WorksheetNotFound:
        return []
    records = ws.get_all_records()
    result = []
    for row in records:
        slot_id = str(row.get("ID", "")).strip()
        name = str(row.get("שם מתגבר", "")).strip()
        if not name:
            continue
        result.append({
            "id": slot_id,
            "tutor": name,
            "day": str(row.get("יום", "")).strip(),
            "start": str(row.get("שעת התחלה", "")).strip(),
            "end": str(row.get("שעת סיום", "")).strip(),
            "subject": str(row.get("מקצוע", "")).strip(),
            "notes": str(row.get("הערות", "")).strip(),
        })
    return result


def _next_id(ws: gspread.Worksheet) -> str:
    """מחשב ID הבא בטאב (מספרי)."""
    ids = ws.col_values(1)[1:]  # skip header
    numeric = [int(x) for x in ids if x.isdigit()]
    return str(max(numeric) + 1) if numeric else "1"


def append_schedule_slot(slot: dict[str, Any]) -> str:
    """מוסיף שיעור קבוע חדש. מחזיר את ה-ID שנוצר."""
    client = _get_client()
    spreadsheet = client.open(config.SHEET_NAME)
    try:
        ws = spreadsheet.worksheet(config.SCHEDULE_TAB)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=config.SCHEDULE_TAB, rows=200, cols=7)
        ws.append_row(
            ["ID", "שם מתגבר", "יום", "שעת התחלה", "שעת סיום", "מקצוע", "הערות"],
            value_input_option="USER_ENTERED",
        )

    new_id = _next_id(ws)
    new_row = [
        new_id,
        slot.get("tutor", ""),
        slot.get("day", ""),
        slot.get("start", ""),
        slot.get("end", ""),
        slot.get("subject", ""),
        slot.get("notes", ""),
    ]
    ws.append_row(new_row, value_input_option="USER_ENTERED",
                  insert_data_option="INSERT_ROWS", table_range="A1")
    return new_id


def update_schedule_slot(slot_id: str, updated: dict[str, Any]) -> bool:
    """מעדכן שיעור קבוע לפי ID."""
    try:
        ws = _open_tab(config.SCHEDULE_TAB)
    except gspread.exceptions.WorksheetNotFound:
        return False
    cell = ws.find(slot_id, in_column=1)
    if not cell:
        return False
    row_values = [
        slot_id,
        updated.get("tutor", ""),
        updated.get("day", ""),
        updated.get("start", ""),
        updated.get("end", ""),
        updated.get("subject", ""),
        updated.get("notes", ""),
    ]
    ws.update(f"A{cell.row}:G{cell.row}", [row_values], value_input_option="USER_ENTERED")
    return True


def remove_schedule_slot(slot_id: str) -> bool:
    """מסיר שיעור קבוע לפי ID."""
    try:
        ws = _open_tab(config.SCHEDULE_TAB)
    except gspread.exceptions.WorksheetNotFound:
        return False
    col = ws.col_values(1)
    rows = [i + 1 for i, v in enumerate(col) if str(v).strip() == slot_id]
    if not rows:
        return False
    for row in reversed(rows):
        ws.delete_rows(row)
    return True


# ---------- שיעורים חד-פעמיים (One-time lessons) ----------

def load_onetime_lessons() -> list[dict[str, Any]]:
    """קורא את טאב 'שיעורים חד-פעמיים'."""
    try:
        ws = _open_tab(config.ONETIME_TAB)
    except gspread.exceptions.WorksheetNotFound:
        return []
    records = ws.get_all_records()
    result = []
    for row in records:
        lesson_id = str(row.get("ID", "")).strip()
        name = str(row.get("שם מתגבר", "")).strip()
        if not name:
            continue
        result.append({
            "id": lesson_id,
            "tutor": name,
            "date": str(row.get("תאריך", "")).strip(),
            "start": str(row.get("שעת התחלה", "")).strip(),
            "end": str(row.get("שעת סיום", "")).strip(),
            "subject": str(row.get("מקצוע", "")).strip(),
            "notes": str(row.get("הערות", "")).strip(),
        })
    return result


def append_onetime_lesson(lesson: dict[str, Any]) -> str:
    """מוסיף שיעור חד-פעמי. מחזיר ID."""
    client = _get_client()
    spreadsheet = client.open(config.SHEET_NAME)
    try:
        ws = spreadsheet.worksheet(config.ONETIME_TAB)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=config.ONETIME_TAB, rows=200, cols=7)
        ws.append_row(
            ["ID", "שם מתגבר", "תאריך", "שעת התחלה", "שעת סיום", "מקצוע", "הערות"],
            value_input_option="USER_ENTERED",
        )

    new_id = _next_id(ws)
    new_row = [
        new_id,
        lesson.get("tutor", ""),
        lesson.get("date", ""),
        lesson.get("start", ""),
        lesson.get("end", ""),
        lesson.get("subject", ""),
        lesson.get("notes", ""),
    ]
    ws.append_row(new_row, value_input_option="USER_ENTERED",
                  insert_data_option="INSERT_ROWS", table_range="A1")
    return new_id


def update_onetime_lesson(lesson_id: str, updated: dict[str, Any]) -> bool:
    """מעדכן שיעור חד-פעמי לפי ID."""
    try:
        ws = _open_tab(config.ONETIME_TAB)
    except gspread.exceptions.WorksheetNotFound:
        return False
    cell = ws.find(lesson_id, in_column=1)
    if not cell:
        return False
    row_values = [
        lesson_id,
        updated.get("tutor", ""),
        updated.get("date", ""),
        updated.get("start", ""),
        updated.get("end", ""),
        updated.get("subject", ""),
        updated.get("notes", ""),
    ]
    ws.update(f"A{cell.row}:G{cell.row}", [row_values], value_input_option="USER_ENTERED")
    return True


def remove_onetime_lesson(lesson_id: str) -> bool:
    """מסיר שיעור חד-פעמי לפי ID."""
    try:
        ws = _open_tab(config.ONETIME_TAB)
    except gspread.exceptions.WorksheetNotFound:
        return False
    col = ws.col_values(1)
    rows = [i + 1 for i, v in enumerate(col) if str(v).strip() == lesson_id]
    if not rows:
        return False
    for row in reversed(rows):
        ws.delete_rows(row)
    return True


def remove_schedule_by_tutor(tutor_name: str) -> int:
    """מסיר את כל השיעורים של מתגבר מהלוז השבועי ומשיעורים חד-פעמיים. מחזיר מספר שורות שנמחקו."""
    removed = 0
    for tab_name in (config.SCHEDULE_TAB, config.ONETIME_TAB):
        try:
            ws = _open_tab(tab_name)
        except gspread.exceptions.WorksheetNotFound:
            continue
        col = ws.col_values(2)  # column B = tutor name
        rows = [i + 1 for i, v in enumerate(col) if str(v).strip() == tutor_name]
        for row in reversed(rows):
            ws.delete_rows(row)
            removed += 1
    return removed


def append_row(row: dict[str, str]) -> None:
    """מוסיף שורה חדשה לגיליון ב-Google Sheets."""
    client = _get_client()
    spreadsheet = client.open(config.SHEET_NAME)
    worksheet_name = getattr(config, "WORKSHEET_NAME", None)
    if worksheet_name:
        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.get_worksheet(0)
    else:
        worksheet = spreadsheet.get_worksheet(0)

    headers = worksheet.row_values(1)

    # Map actual sheet headers to canonical column names using fuzzy matching
    canonical_names = [COL_TIMESTAMP, COL_TUTOR, COL_DATE, COL_START, COL_END,
                       COL_STUDENTS, COL_TOPIC, COL_RATING, COL_NOTES]
    header_map: dict[str, str] = {}
    for canonical in canonical_names:
        actual = _find_column(headers, canonical)
        if actual:
            header_map[actual] = canonical

    new_row: list[str] = []
    for header in headers:
        key = header_map.get(header, header)
        new_row.append(row.get(key, ""))
    worksheet.append_row(new_row, value_input_option="USER_ENTERED",
                         insert_data_option="INSERT_ROWS",
                         table_range="A1")
