"""הגדרות הדשבורד. עדכן את הערכים כאן."""
from pathlib import Path

# נתיב לקובץ ה-credentials (Service Account JSON)
CREDENTIALS_PATH = Path(__file__).parent / "tutoring-dashboard-494208-f7c7d9ad1f0a.json"

# שם הגיליון ב-Google Drive (השם המדויק כפי שמופיע בכותרת הגיליון)
# לדוגמה: "דיווחי תגבורים (Responses)"
SHEET_NAME = "דיווחי תגבורים"

# שם העמוד (sheet tab) בתוך הגיליון. ברירת המחדל של Google Forms: "Form Responses 1"
WORKSHEET_NAME = "Form Responses 1"

# סף הדמיון לזיהוי נושאים דומים (0-100). גבוה יותר = חיפוש מחמיר יותר
TOPIC_SIMILARITY_THRESHOLD = 70

# זמן cache לנתונים (בשניות). 300 = 5 דקות
CACHE_TTL_SECONDS = 300
