#!/usr/bin/env python3
import urllib.request, json, sys, io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

resp = urllib.request.urlopen('http://localhost:7030/api/data')
data = json.load(resp)

print("\n[OK] Updated API Response:\n")
print(f"  Total Targets: {data.get('total_targets')}")
print(f"  Total Disconnect Events: {data.get('total_disconnect_events')}")
print(f"\n  Disconnects per target:")
for d in data.get('disconnects', []):
    print(f"    {d['name']}: {d['disconnect_count']} event(s)")
    print(f"      Last: {d['last_disconnect']}")

