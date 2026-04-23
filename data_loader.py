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
