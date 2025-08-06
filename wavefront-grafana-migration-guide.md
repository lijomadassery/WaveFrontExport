# Wavefront to Grafana Migration Guide

## Overview

This guide provides a comprehensive approach to migrate dashboards and alerts from Wavefront to Grafana. The migration uses a semi-automated Python script that extracts configurations from Wavefront via API, transforms queries and dashboard structures, and imports them into Grafana.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Migration Strategy](#migration-strategy)
- [Setup Instructions](#setup-instructions)
- [Using the Migration Script](#using-the-migration-script)
- [Query Translation Reference](#query-translation-reference)
- [Customization Guide](#customization-guide)
- [Validation and Testing](#validation-and-testing)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)

## Prerequisites

### Required Tools
- Python 3.7 or higher
- `pip` package manager
- Network access to both Wavefront and Grafana APIs

### Required Information
- Wavefront API URL (e.g., `https://your-company.wavefront.com`)
- Wavefront API token with read permissions
- Grafana API URL (e.g., `https://your-grafana.com`)
- Grafana API token with Admin permissions
- Target datasource type (Prometheus, InfluxDB, etc.)
- Grafana datasource UID

### Python Dependencies
```bash
pip install requests
```

## Migration Strategy

The migration process follows these steps:

1. **Extract** - Fetch dashboard and alert configurations from Wavefront API
2. **Transform** - Convert WQL queries to target query language (PromQL, InfluxQL)
3. **Build** - Generate Grafana-compatible JSON structures
4. **Validate** - Save JSON files locally for review
5. **Import** - Push configurations to Grafana via API

## Setup Instructions

### 1. Obtain API Tokens

#### Wavefront API Token
1. Log into Wavefront
2. Navigate to **Settings** → **API Tokens**
3. Click **Generate Token**
4. Name your token (e.g., "Migration Script")
5. Copy and save the token securely

#### Grafana API Token
1. Log into Grafana
2. Navigate to API Keys (location varies by version):
   - **Grafana 7.x and earlier**: **Configuration** → **API Keys**
   - **Grafana 8.x - 9.x**: **Administration** → **API Keys**
   - **Grafana 10.x+**: **Administration** → **Users and access** → **Service accounts**
3. Click **Add API key** (or **New service account** for 10.x+)
4. Set role to **Admin**
5. Set expiration as needed
6. Copy and save the token securely

### 2. Identify Grafana Datasource UID

The datasource UID is a unique identifier that Grafana uses internally. You can find it using one of these methods:

#### Method 1: Via Grafana UI
1. Log into your Grafana instance
2. Navigate to **Configuration** → **Data Sources** (or **Connections** → **Data sources** in newer versions)
3. Click on the datasource you want to use (e.g., Prometheus, InfluxDB)
4. Look at the URL in your browser - it will contain the UID:
   - Example: `https://grafana.example.com/datasources/edit/abc123def`
   - The UID is `abc123def`

#### Method 2: Via Grafana API
```bash
curl -H "Authorization: Bearer YOUR_GRAFANA_TOKEN" \
  https://your-grafana-url/api/datasources
```

This returns JSON with all datasources:
```json
[
  {
    "id": 1,
    "uid": "P1234567890",
    "name": "Prometheus",
    "type": "prometheus",
    "url": "http://localhost:9090"
  }
]
```

#### Method 3: Datasource Settings Page
1. Open the datasource in Grafana
2. Look for the "UID" field in the settings (some versions display it directly)
3. It's typically an alphanumeric string like `P1234567890` or `abc123def`

### 3. Download the Migration Script

Save the `migrate.py` script from this repository to your local machine.

### 4. Configure Your Environment

Create a `.env` file (do not commit this to Git):
```bash
# Wavefront Configuration
WAVEFRONT_URL=https://your-company.wavefront.com
WAVEFRONT_TOKEN=your-wavefront-token

# Grafana Configuration
GRAFANA_URL=https://your-grafana.com
# Choose one authentication method:
GRAFANA_TOKEN=your-grafana-token          # Option 1: API Token
# OR
GRAFANA_USERNAME=admin                    # Option 2: Username
GRAFANA_PASSWORD=your-password            # Option 2: Password

DATASOURCE_TYPE=prometheus  # or influxdb, elasticsearch, cloudwatch
DATASOURCE_UID=your-datasource-uid
```

## Using the Migration Script

### Basic Usage

#### Migrate All Dashboards and Alerts

**Using API Token:**
```bash
python wavefront-grafana-migrator.py \
  --wavefront-url $WAVEFRONT_URL \
  --wavefront-token $WAVEFRONT_TOKEN \
  --grafana-url $GRAFANA_URL \
  --grafana-token $GRAFANA_TOKEN \
  --datasource-type prometheus \
  --datasource-uid $DATASOURCE_UID
```

**Using Username/Password:**
```bash
python wavefront-grafana-migrator.py \
  --wavefront-url $WAVEFRONT_URL \
  --wavefront-token $WAVEFRONT_TOKEN \
  --grafana-url $GRAFANA_URL \
  --grafana-credentials $GRAFANA_USERNAME $GRAFANA_PASSWORD \
  --datasource-type prometheus \
  --datasource-uid $DATASOURCE_UID
```

#### Migrate Specific Dashboards Only
```bash
python wavefront-grafana-migrator.py \
  --wavefront-url $WAVEFRONT_URL \
  --wavefront-token $WAVEFRONT_TOKEN \
  --grafana-url $GRAFANA_URL \
  --grafana-token $GRAFANA_TOKEN \
  --datasource-type prometheus \
  --datasource-uid $DATASOURCE_UID \
  --dashboards dashboard-id-1 dashboard-id-2 \
  --skip-alerts
```

#### Migrate Alerts Only
```bash
python wavefront-grafana-migrator.py \
  --wavefront-url $WAVEFRONT_URL \
  --wavefront-token $WAVEFRONT_TOKEN \
  --grafana-url $GRAFANA_URL \
  --grafana-token $GRAFANA_TOKEN \
  --datasource-type prometheus \
  --datasource-uid $DATASOURCE_UID \
  --skip-dashboards \
  --alerts alert-id-1 alert-id-2
```

#### Migrate Alerts with Custom Group Settings
```bash
python wavefront-grafana-migrator.py \
  --wavefront-url $WAVEFRONT_URL \
  --wavefront-token $WAVEFRONT_TOKEN \
  --grafana-url $GRAFANA_URL \
  --grafana-token $GRAFANA_TOKEN \
  --datasource-type prometheus \
  --datasource-uid $DATASOURCE_UID \
  --skip-dashboards \
  --alert-group-name "Production Alerts" \
  --alert-folder "Operations" \
  --alert-interval "30s"
```

### Command Line Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--wavefront-url` | Yes | Wavefront API endpoint URL |
| `--wavefront-token` | Yes | Wavefront API authentication token |
| `--grafana-url` | Yes | Grafana API endpoint URL |
| `--grafana-token` | Yes | Grafana API authentication token |
| `--datasource-type` | Yes | Target datasource type: `prometheus`, `influxdb`, `elasticsearch`, `cloudwatch` |
| `--datasource-uid` | Yes | UID of the Grafana datasource to use |
| `--dashboards` | No | Space-separated list of specific dashboard IDs to migrate |
| `--alerts` | No | Space-separated list of specific alert IDs to migrate |
| `--skip-dashboards` | No | Skip dashboard migration |
| `--skip-alerts` | No | Skip alert migration |
| `--alert-group-name` | No | Name for the alert rule group (default: "Wavefront Alerts") |
| `--alert-folder` | No | Folder name for alerts in Grafana (default: "Wavefront Migration") |
| `--alert-interval` | No | Evaluation interval for alerts (default: "60s") |

### Output Files

The script generates JSON files for each migrated item:
- `dashboard_{id}.json` - Grafana dashboard configurations
- `alert_{uid}.json` - Individual alert rule configurations
- `alert_group_{name}.json` - Complete alert group configuration with all rules

Review these files before importing to ensure correct translation.

## Query Translation Reference

### Supported WQL to PromQL Conversions

| WQL Pattern | PromQL Translation | Notes |
|-------------|-------------------|--------|
| `ts(metric.name)` | `metric_name` | Dots replaced with underscores |
| `ts(metric.name, tag="value")` | `metric_name{tag="value"}` | Tag filters preserved |
| `rate(ts(...))` | `rate(metric_name[5m])` | 5m default range |
| `avg(ts(...))` | `avg(metric_name)` | Direct function mapping |
| `sum(ts(...))` | `sum(metric_name)` | Direct function mapping |
| `max(ts(...))` | `max(metric_name)` | Direct function mapping |
| `min(ts(...))` | `min(metric_name)` | Direct function mapping |

### Supported WQL to InfluxQL Conversions

| WQL Pattern | InfluxQL Translation | Notes |
|-------------|---------------------|--------|
| `ts(metric.name)` | `SELECT mean("value") FROM "metric.name"` | Preserves dots in metric names |
| `ts(metric.name, tag="value")` | `SELECT mean("value") FROM "metric.name" WHERE "tag"='value'` | Tag filters in WHERE clause |
| `sum(ts(...))` | `SELECT sum("value") FROM "metric.name"` | Aggregation functions mapped |
| All queries | Appended with `GROUP BY time($__interval) fill(null)` | Grafana time grouping |

### Unsupported Patterns Requiring Manual Translation

- Complex mathematical operations
- Nested aggregations
- Wavefront-specific functions (mavg, mpercentile, etc.)
- Advanced time-shifting operations
- Multi-series joins

## Customization Guide

### Extending Query Translation

To add support for additional WQL patterns, modify the `QueryTranslator` class:

```python
# In migrate.py, extend the wql_to_promql method

@staticmethod
def wql_to_promql(wql_query: str) -> str:
    # ... existing code ...
    
    # Add custom pattern for moving average
    if 'mavg(' in wql_query:
        # Extract window size and convert to PromQL
        window_match = re.search(r'mavg\((\d+[smhd]),', wql_query)
        if window_match:
            window = window_match.group(1)
            promql = f"avg_over_time({promql}[{window}])"
    
    # Add custom pattern for percentiles
    if 'percentile(' in wql_query:
        percentile_match = re.search(r'percentile\((\d+),', wql_query)
        if percentile_match:
            p = float(percentile_match.group(1)) / 100
            promql = f"quantile({p}, {promql})"
    
    return promql
```

### Adding Dashboard Features

#### Variables/Templating
```python
# In GrafanaDashboardBuilder.build_dashboard method
def build_dashboard(self, wf_dashboard: Dict) -> Dict:
    grafana_dashboard = {
        "dashboard": {
            # ... existing config ...
            "templating": {
                "list": [
                    {
                        "name": "environment",
                        "type": "custom",
                        "current": {"text": "prod", "value": "prod"},
                        "options": [
                            {"text": "prod", "value": "prod"},
                            {"text": "staging", "value": "staging"},
                            {"text": "dev", "value": "dev"}
                        ]
                    }
                ]
            }
        }
    }
```

#### Custom Panel Types
```python
# In _convert_chart_to_panel method
panel_type_map = {
    'line': 'timeseries',
    'area': 'timeseries',
    'column': 'barchart',
    'scatter': 'timeseries',
    'table': 'table',
    'single-stat': 'stat',
    'sparkline': 'sparkline',
    'heatmap': 'heatmap',  # Add new mapping
    'gauge': 'gauge'        # Add new mapping
}
```

### Supporting Additional Datasources

Add new translation methods for other datasource types:

```python
@staticmethod
def wql_to_elasticsearch(wql_query: str) -> Dict:
    """Convert WQL to Elasticsearch query DSL"""
    # Parse WQL
    ts_pattern = r'ts\(([\w\.\-]+)(?:,\s*(.+))?\)'
    match = re.search(ts_pattern, wql_query)
    
    if match:
        metric = match.group(1)
        # Build Elasticsearch query
        es_query = {
            "query": {
                "match": {
                    "metric": metric
                }
            },
            "aggs": {
                "time_buckets": {
                    "date_histogram": {
                        "field": "@timestamp",
                        "interval": "1m"
                    }
                }
            }
        }
        return json.dumps(es_query)
    
    return "{}"
```

## Alert Migration Details

### Alert Rule Groups and Folders

Modern Grafana requires alerts to be organized into **Alert Rule Groups** within **Folders**. The migration tool automatically handles this structure:

1. **Alert Rule Groups**: All migrated alerts are placed in a named group
   - Configurable via `--alert-group-name` (default: "Wavefront Alerts")
   - Groups define the evaluation interval for all contained rules
   - Multiple alerts can be evaluated together for efficiency

2. **Folders**: Alerts are organized in Grafana folders
   - Configurable via `--alert-folder` (default: "Wavefront Migration")
   - Folders provide access control and organization
   - The tool automatically creates folders if they don't exist

3. **Alert Structure**: Each alert uses a 3-step evaluation chain
   - **Step A**: Query execution (fetches metric data)
   - **Step B**: Reduce (converts time series to single value)
   - **Step C**: Threshold evaluation (applies conditions)

### Alert Group JSON Structure

The migrated alerts follow this structure:
```json
{
  "apiVersion": 1,
  "groups": [{
    "orgId": 1,
    "name": "Wavefront Alerts",
    "folder": "Wavefront Migration",
    "interval": "60s",
    "rules": [
      {
        "uid": "wf_alert_id",
        "title": "Alert Name",
        "condition": "C",
        "data": [
          // Query, reduce, and threshold steps
        ],
        "noDataState": "NoData",
        "execErrState": "Alerting",
        "for": "5m",
        "annotations": {
          "description": "Alert description",
          "summary": "Alert summary"
        },
        "labels": {
          "tag_environment": "production"
        }
      }
    ]
  }]
}
```

## Validation and Testing

### Pre-Migration Checklist

- [ ] Backup existing Grafana dashboards
- [ ] Test API connectivity to both Wavefront and Grafana
- [ ] Verify datasource is properly configured in Grafana
- [ ] Run script with `--dashboards` flag on a single test dashboard first
- [ ] Review generated JSON files before importing

### Post-Migration Validation

1. **Visual Inspection**
   - Compare dashboard layouts between Wavefront and Grafana
   - Verify all panels are present
   - Check that time ranges are appropriate

2. **Query Validation**
   - Verify queries return data
   - Compare metric values between systems
   - Check for query errors in Grafana panel inspect

3. **Alert Testing**
   - Verify alert rules are evaluating
   - Test notification channels
   - Validate threshold values

### Validation Script

Create a `validate.py` script to compare metrics:

```python
import requests
import json
from datetime import datetime, timedelta

def compare_metrics(wavefront_url, wavefront_token, grafana_url, grafana_token, metric_name):
    """Compare metric values between Wavefront and Grafana"""
    
    # Get time range (last hour)
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=1)
    
    # Fetch from Wavefront
    wf_response = requests.get(
        f"{wavefront_url}/api/v2/chart/api",
        headers={'Authorization': f'Bearer {wavefront_token}'},
        params={
            'q': f'ts({metric_name})',
            's': int(start_time.timestamp()),
            'e': int(end_time.timestamp())
        }
    )
    
    # Fetch from Grafana
    grafana_response = requests.post(
        f"{grafana_url}/api/ds/query",
        headers={'Authorization': f'Bearer {grafana_token}'},
        json={
            'queries': [{
                'expr': metric_name.replace('.', '_'),
                'refId': 'A'
            }],
            'from': str(int(start_time.timestamp() * 1000)),
            'to': str(int(end_time.timestamp() * 1000))
        }
    )
    
    # Compare results
    print(f"Metric: {metric_name}")
    print(f"Wavefront points: {len(wf_response.json().get('timeseries', []))}")
    print(f"Grafana points: {len(grafana_response.json().get('results', {}).get('A', {}).get('frames', []))}")
```

## Troubleshooting

### Common Issues and Solutions

#### 1. Authentication Errors
**Error:** `401 Unauthorized`
**Solution:** 
- Verify API tokens are correct and not expired
- Check token permissions (read for Wavefront, Admin for Grafana)
- Ensure URLs don't have trailing slashes

#### 2. Query Translation Failures
**Error:** `TODO: Translate WQL` in panel queries
**Solution:**
- Review the WQL query in generated JSON files
- Manually update the query in Grafana
- Add custom translation logic for unsupported patterns

#### 3. Dashboard Import Failures
**Error:** `400 Bad Request` when importing dashboard
**Solution:**
- Check datasource UID exists in Grafana
- Validate JSON structure using a JSON validator
- Review Grafana logs for specific error details

#### 4. Missing Panels
**Issue:** Some panels don't appear in Grafana
**Solution:**
- Check if panel type is supported
- Review console logs for conversion errors
- Verify queries are returning data

#### 5. Alert Migration Issues
**Error:** Alert rules not working
**Solution:**
- Ensure Grafana alerting is enabled
- Check notification channels are configured
- Verify query syntax for your datasource

#### 6. Alert Group/Folder Issues
**Error:** `Failed to import alert group` or alerts missing folder
**Solution:**
- Ensure the user has permissions to create folders in Grafana
- Verify folder name doesn't contain invalid characters
- Check if folder already exists with different UID
- Review alert group JSON structure in `alert_group_*.json` file

### Debug Mode

Run the script with increased logging:

```python
# Add to the script
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Best Practices

### 1. Phased Migration Approach

**Phase 1: Discovery**
- Inventory all dashboards and alerts
- Identify critical vs. non-critical dashboards
- Document custom WQL queries

**Phase 2: Pilot**
- Select 2-3 representative dashboards
- Run migration script
- Validate and refine translation logic

**Phase 3: Bulk Migration**
- Migrate by dashboard category or team
- Run in batches of 10-20 dashboards
- Validate each batch before proceeding

**Phase 4: Cutover**
- Run both systems in parallel for 1-2 weeks
- Compare metrics and alert behaviors
- Gradually transition teams to Grafana

### 2. Version Control

```bash
# Create a migration repository
mkdir wavefront-migration
cd wavefront-migration
git init

# Organize migrated files
mkdir -p migrated/dashboards
mkdir -p migrated/alerts
mkdir -p original/wavefront

# Track migration progress
echo "dashboard_id,status,date,notes" > migration_log.csv
```

### 3. Dashboard Organization in Grafana

- Create folders by team or service
- Use consistent naming: `[Service] - [Environment] - [Dashboard Name]`
- Apply tags for easy filtering
- Set appropriate permissions per folder

### 4. Query Optimization

After migration, optimize queries for better performance:

- Add recording rules for frequently-used queries (Prometheus)
- Use continuous queries for pre-aggregation (InfluxDB)
- Implement caching where appropriate
- Review and optimize refresh intervals

### 5. Documentation

Document the following for your team:

- Mapping between Wavefront and Grafana dashboards
- Custom query translations implemented
- Known limitations or manual adjustments needed
- Rollback procedures if issues arise

### 6. Monitoring the Migration

Create a migration monitoring dashboard in Grafana:

- Number of dashboards migrated vs. remaining
- Query error rates
- Alert firing comparisons
- User adoption metrics

## Appendix

### A. Sample Migration Log Format

```csv
dashboard_id,dashboard_name,status,migrated_date,validated_date,notes
dash-001,Service Health,success,2024-01-15,2024-01-16,"All panels working"
dash-002,API Metrics,partial,2024-01-15,2024-01-17,"Complex queries need manual adjustment"
dash-003,Database Performance,failed,2024-01-15,,"Unsupported visualization type"
```

### B. Rollback Procedure

If you need to rollback a migration:

1. Keep Wavefront dashboards unchanged during migration
2. Export Grafana dashboards before overwriting
3. Use Grafana's dashboard version history
4. Maintain a mapping of Dashboard ID to Grafana UID

### C. Getting Help

- Review Grafana logs: `/var/log/grafana/grafana.log`
- Check browser console for frontend errors
- Use Grafana's Query Inspector for debugging
- Consult Grafana documentation: https://grafana.com/docs/
- Review Wavefront API docs: https://docs.wavefront.com/wavefront_api.html

## Contributing

To improve this migration tool:

1. Fork the repository
2. Create a feature branch
3. Add your improvements (new query patterns, datasource support, etc.)
4. Submit a pull request with:
   - Description of changes
   - Example WQL queries that are now supported
   - Test results

## License

[Your License Here]

## Authors

[Your Team Name]

---

*Last Updated: [Date]*
*Version: 1.0.0*