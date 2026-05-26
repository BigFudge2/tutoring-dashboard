"""Write the 2 new schedule slots to the לוז שבועי tab."""
import time
import gspread

gc = gspread.service_account(filename='tutoring-dashboard-494208-f7c7d9ad1f0a.json')
sh = gc.open('דיווחי תגבורים')
ws = sh.worksheet('לוז שבועי')

# Current max ID
rows = ws.get_all_values()
max_id = max(int(r[0]) for r in rows[1:] if r[0].isdigit())
print(f"Current max ID: {max_id}")

new_slots = [
    {'tutor': 'ליאם אבן חיים', 'day': 'חמישי', 'start': '14:15', 'end': '15:15', 'subject': 'תכנות מונחה עצמים', 'notes': 'שובץ אוטומטית'},
    {'tutor': 'איליי אלעזר דהן', 'day': 'ראשון', 'start': '15:00', 'end': '16:00', 'subject': 'אלגברה לינארית', 'notes': 'שובץ אוטומטית'},
]

for i, slot in enumerate(new_slots, 1):
    new_id = max_id + i
    row = [str(new_id), slot['tutor'], slot['day'], slot['start'], slot['end'], slot['subject'], slot['notes']]
    ws.append_row(row, value_input_option='USER_ENTERED')
    print(f"Added row {new_id}: {slot['tutor']} - {slot['day']} {slot['start']}-{slot['end']} ({slot['subject']})")
    time.sleep(2)

print("\nDone! 2 new slots added to לוז שבועי.")
