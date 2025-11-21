#!/usr/bin/env python3
import subprocess
import time
import sqlite3
from datetime import datetime

print('Starting webserver...')
webserver = subprocess.Popen(['python', 'webserver.py', '--test'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2)

print('Starting pingit...')
pingit = subprocess.Popen(['python', 'pingit.py', '--test'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

print('Both services started')
print('Waiting 30 seconds for new data with correct timestamps...')
time.sleep(30)

print()
print('Checking data...')
conn = sqlite3.connect('./pingit.db')
cursor = conn.cursor()

print('Current local time:', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
print()

cursor.execute('SELECT COUNT(*) FROM ping_statistics WHERE datetime(timestamp) > datetime("now", "-2 hours", "localtime")')
recent = cursor.fetchone()[0]
print('Records in last 2 hours: {}'.format(recent))

cursor.execute('SELECT COUNT(*) FROM ping_statistics WHERE datetime(timestamp) > datetime("now", "-1 hours", "localtime")')
last_hour = cursor.fetchone()[0]
print('Records in last 1 hour: {}'.format(last_hour))

cursor.execute('SELECT target_name, timestamp FROM ping_statistics ORDER BY timestamp DESC LIMIT 3')
rows = cursor.fetchall()
print()
print('Latest records:')
for row in rows:
    print('  {}: {}'.format(row[0], row[1]))

conn.close()
print()
print('✅ If last 1 hour > 0, then timestamps are now correct!')

