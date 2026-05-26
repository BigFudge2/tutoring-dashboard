"""סקריפט חד־פעמי: מסנכרן את הקובץ 'דיווחי תגבורים - מתגברים.csv' לטאב 'מתגברים' ב-Google Sheets.

הוא:
1. קורא את כל השורות מה-CSV
2. מנקה את הטאב הקיים
3. כותב מחדש את הכותרות + כל השורות

הרצה: python sync_tutors_to_sheets.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import config
from data_loader import _get_client

CSV_PATH = Path(__file__).parent / "דיווחי תגבורים - מתגברים.csv"


def main() -> None:
    if not CSV_PATH.exists():
        print(f"[שגיאה] לא נמצא: {CSV_PATH}")
        sys.exit(1)

    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        rows = [r for r in reader if any(cell.strip() for cell in r)]

    if not rows:
        print("[שגיאה] הקובץ ריק")
        sys.exit(1)

    print(f"נטענו {len(rows) - 1} שורות מ-CSV (חוץ מכותרת)")

    client = _get_client()
    spreadsheet = client.open(config.SHEET_NAME)
    try:
        ws = spreadsheet.worksheet(config.TUTORS_TAB)
        print(f"נמצא טאב קיים: '{config.TUTORS_TAB}'")
    except Exception:
        ws = spreadsheet.add_worksheet(title=config.TUTORS_TAB, rows=max(100, len(rows) + 20), cols=10)
        print(f"נוצר טאב חדש: '{config.TUTORS_TAB}'")

    ws.clear()
    ws.update("A1", rows, value_input_option="USER_ENTERED")
    print(f"✓ עודכן בהצלחה. שורות: {len(rows)} (כולל כותרת)")


if __name__ == "__main__":
    main()
