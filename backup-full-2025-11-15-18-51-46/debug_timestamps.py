#!/usr/bin/env python3
import sqlite3
from datetime import datetime

conn = sqlite3.connect('./pingit.db')
cursor = conn.cursor()

print('Current local time:', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
print()

# Check latest records
cursor.execute('SELECT target_name, timestamp FROM ping_statistics ORDER BY timestamp DESC LIMIT 5')
rows = cursor.fetchall()
print('Latest 5 records:')
for row in rows:
    print('  {}: {}'.format(row[0], row[1]))

print()
print('Records by time range:')
for range_name, hours in [('1h', 1), ('2h', 2), ('24h', 24)]:
    cursor.execute('SELECT COUNT(*) FROM ping_statistics WHERE datetime(timestamp) > datetime("now", "-{} hours", "localtime")'.format(hours))
    count = cursor.fetchone()[0]
    print('  Last {}: {} records'.format(range_name, count))

conn.close()

