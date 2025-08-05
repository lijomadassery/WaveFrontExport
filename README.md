# Wavefront to Grafana Migration Tool

A Python tool to migrate dashboards and alerts from Wavefront (now VMware Aria Operations for Applications) to Grafana.

## Features

- **Dashboard Migration**: Converts Wavefront dashboards to Grafana format
- **Alert Migration**: Transforms Wavefront alerts to Grafana alert rules
- **Query Translation**: Translates Wavefront Query Language (WQL) to:
  - PromQL (Prometheus)
  - InfluxQL (InfluxDB)
- **Batch Processing**: Migrate all or specific dashboards/alerts
- **Export Capability**: Save converted dashboards/alerts as JSON files

## Prerequisites

- Python 3.7+
- Wavefront API access (URL and token)
- Grafana instance with API access (URL and token)
- Target datasource configured in Grafana (Prometheus, InfluxDB, etc.)

### Installing Python

#### macOS
```bash
# Using Homebrew (recommended)
brew install python3

# Or download from python.org
# https://www.python.org/downloads/macos/
```

#### Ubuntu/Debian
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv
```

#### CentOS/RHEL/Fedora
```bash
sudo yum install python3 python3-pip
# or for newer versions:
sudo dnf install python3 python3-pip
```

#### Windows
1. Download from [python.org](https://www.python.org/downloads/windows/)
2. Run installer and check "Add Python to PATH"
3. Or use Windows Store: search for "Python 3"

#### Verify Installation
```bash
python3 --version
pip3 --version
```

## Installation

1. Clone the repository:
```bash
cd /Users/lijomadassery/Documents/Work/WavefrontExport
```

2. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Basic Command Structure

```bash
python wavefront-grafana-migrator.py \
    --wavefront-url YOUR_WAVEFRONT_URL \
    --wavefront-token YOUR_WAVEFRONT_TOKEN \
    --grafana-url YOUR_GRAFANA_URL \
    --grafana-token YOUR_GRAFANA_TOKEN \
    --datasource-type prometheus \
    --datasource-uid YOUR_DATASOURCE_UID
```

### Command Line Arguments

- `--wavefront-url`: Wavefront API URL (required)
- `--wavefront-token`: Wavefront API token (required)
- `--grafana-url`: Grafana API URL (required)
- `--grafana-token`: Grafana API token (required)
- `--datasource-type`: Target datasource type: `prometheus`, `influxdb`, `elasticsearch`, `cloudwatch` (required)
- `--datasource-uid`: Grafana datasource UID (required)
- `--dashboards`: Specific dashboard IDs to migrate (optional)
- `--alerts`: Specific alert IDs to migrate (optional)
- `--skip-dashboards`: Skip dashboard migration (optional)
- `--skip-alerts`: Skip alert migration (optional)

### Examples

#### Migrate all dashboards and alerts:
```bash
python wavefront-grafana-migrator.py \
    --wavefront-url https://your-instance.wavefront.com \
    --wavefront-token your-token \
    --grafana-url http://localhost:3000 \
    --grafana-token your-grafana-token \
    --datasource-type prometheus \
    --datasource-uid abc123def
```

#### Migrate specific dashboards only:
```bash
python wavefront-grafana-migrator.py \
    --wavefront-url https://your-instance.wavefront.com \
    --wavefront-token your-token \
    --grafana-url http://localhost:3000 \
    --grafana-token your-grafana-token \
    --datasource-type prometheus \
    --datasource-uid abc123def \
    --dashboards dashboard-id-1 dashboard-id-2 \
    --skip-alerts
```

#### Migrate to InfluxDB datasource:
```bash
python wavefront-grafana-migrator.py \
    --wavefront-url https://your-instance.wavefront.com \
    --wavefront-token your-token \
    --grafana-url http://localhost:3000 \
    --grafana-token your-grafana-token \
    --datasource-type influxdb \
    --datasource-uid your-influx-uid
```

## Getting Required Information

### Wavefront API Token
1. Log in to your Wavefront instance
2. Navigate to your user profile settings
3. Generate an API token with appropriate permissions

### Grafana API Token
1. Log in to your Grafana instance
2. Go to Configuration → API Keys
3. Create a new API key with Editor or Admin role

### Grafana Datasource UID
1. In Grafana, go to Configuration → Data Sources
2. Click on your target datasource
3. The UID is shown in the datasource settings or URL

## Output

The tool will:
1. Save each migrated dashboard as `dashboard_<id>.json`
2. Save each migrated alert as `alert_<id>.json`
3. Automatically import to Grafana (unless there are errors)
4. Provide detailed logs of the migration process

## Query Translation Notes

The query translator provides basic WQL to PromQL/InfluxQL conversion. Complex queries may require manual adjustment. The translator handles:

- Basic `ts()` function conversion
- Common aggregations (avg, sum, max, min)
- Tag filtering
- Simple rate calculations

For complex queries, review the generated JSON files and adjust as needed before importing.

## Troubleshooting

1. **Authentication Errors**: Verify your API tokens have the necessary permissions
2. **Query Translation Issues**: Check the generated JSON files and manually adjust complex queries
3. **Import Failures**: Ensure the target datasource exists in Grafana with the correct UID
4. **Missing Panels**: Some Wavefront chart types may not have direct Grafana equivalents

## Limitations

- Query translation is simplified and may not cover all WQL functions
- Some Wavefront-specific features may not have Grafana equivalents
- Complex dashboard layouts may need manual adjustment
- Alert conditions are simplified during migration

## Contributing

Feel free to submit issues or pull requests to improve the migration tool.

## License

This tool is provided as-is for migration purposes.