# delete-alerts.py

## Purpose
Utility script to delete Grafana *unified alert rules* by their UIDs. Supports:
- Direct list of UIDs via CLI
- Bulk deletion from a JSON file containing an array of UIDs (strings or objects with a "uid" field)
- Auth via API token or username/password

Each UID is validated (fetched) before deletion to avoid misleading success logs.

## Requirements
- Python 3.8+
- requests (`pip install requests`)
- Network access to Grafana
- Grafana user / service account with alert provisioning delete permission

## Authentication
Provide exactly one:
--grafana-token <API_TOKEN>
--grafana-credentials <USERNAME> <PASSWORD>

## Basic Usage
Delete one alert:
```
python delete-alerts.py \
  --grafana-url http://localhost:3000 \
  --grafana-token GF_API_TOKEN \
  --delete-alerts wf_abcd1234
```

Delete multiple alerts (space‑separated):
```
python delete-alerts.py \
  --grafana-url http://localhost:3000 \
  --grafana-token GF_API_TOKEN \
  --delete-alerts wf_a1 wf_b2 wf_c3
```

Delete from JSON file:
```
python delete-alerts.py \
  --grafana-url http://localhost:3000 \
  --grafana-token GF_API_TOKEN \
  --delete-alerts-file sample_delete_alert_ids.json
```

Combine file + extra UIDs:
```
python delete-alerts.py \
  --grafana-url http://localhost:3000 \
  --grafana-token GF_API_TOKEN \
  --delete-alerts-file sample_delete_alert_ids.json \
  --delete-alerts wf_extra_01 wf_extra_02
```

Using username/password:
```
python delete-alerts.py \
  --grafana-url https://grafana.example.com \
  --grafana-credentials admin 'SuperSecret' \
  --delete-alerts-file sample_delete_alert_ids.json
```

## JSON File Format
sample_delete_alert_ids.json:
```json
[
  "wf_1724941576183",
  "wf_20240807120000a1b2c3",
  "wf_abcdef1234567890deadbeef",
  "wf_908f7e6d5c4b3a21",
  "wf_rule_00112233445566778899"
]
```

Both plain strings and objects with a uid key are accepted.

## Output
Logs:
- INFO for start/end, each deletion attempt, success summary
- WARNING if a UID not found
- ERROR for request failures or invalid input file

## Exit Behavior
Script returns 0 even if some deletions fail (failures reported in log). Adjust as needed if strict failure handling is required.

## Notes
- Endpoint used: /api/v1/provisioning/alert-rules/{uid}
- Pre‑fetch (GET) used to confirm existence before DELETE
- Timeouts set to 15s per request
- No retry logic (can be added if needed)

## Common Issues
- 401 Unauthorized: Check token scope / credentials
- 404 Not found: UID already deleted or incorrect
- SSL errors: Use HTTPS with valid certs or configure requests session
