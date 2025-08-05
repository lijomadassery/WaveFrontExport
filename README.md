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
# Using Grafana API token
python wavefront-grafana-migrator.py \
    --wavefront-url YOUR_WAVEFRONT_URL \
    --wavefront-token YOUR_WAVEFRONT_TOKEN \
    --grafana-url YOUR_GRAFANA_URL \
    --grafana-token YOUR_GRAFANA_TOKEN \
    --datasource-type prometheus \
    --datasource-uid YOUR_DATASOURCE_UID

# OR using Grafana username/password
python wavefront-grafana-migrator.py \
    --wavefront-url YOUR_WAVEFRONT_URL \
    --wavefront-token YOUR_WAVEFRONT_TOKEN \
    --grafana-url YOUR_GRAFANA_URL \
    --grafana-credentials admin your-password \
    --datasource-type prometheus \
    --datasource-uid YOUR_DATASOURCE_UID
```

### Command Line Arguments

- `--wavefront-url`: Wavefront API URL (required)
- `--wavefront-token`: Wavefront API token (required)
- `--grafana-url`: Grafana API URL (required)

**Grafana Authentication (choose one):**
- `--grafana-token`: Grafana API token
- `--grafana-credentials USERNAME PASSWORD`: Grafana username and password

**Other Arguments:**
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

#### Migrate using username/password (local Grafana):
```bash
python wavefront-grafana-migrator.py \
    --wavefront-url https://your-instance.wavefront.com \
    --wavefront-token your-token \
    --grafana-url http://localhost:3000 \
    --grafana-credentials admin your-password \
    --datasource-type prometheus \
    --datasource-uid abc123def
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

### Grafana Authentication

**Option 1: API Token (Recommended)**
1. Log in to your Grafana instance
2. Navigate to API Keys:
   - **Grafana 7.x and earlier**: Configuration → API Keys
   - **Grafana 8.x - 9.x**: Administration → API Keys  
   - **Grafana 10.x+**: Administration → Users and access → Service accounts
3. Create a new API key/service account with Editor or Admin role
4. Use with `--grafana-token` parameter

**Option 2: Username/Password**
- Use your Grafana admin username and password
- Use with `--grafana-credentials username password` parameter
- Ideal for local development or when API tokens aren't available

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

## Testing with Synthetic Data

If you have Grafana dashboards but no data yet, you can generate synthetic test data using Prometheus Push Gateway.

### Quick Setup

1. **Start Push Gateway**:
```bash
docker run -d -p 9091:9091 prom/pushgateway
```

2. **Configure your existing Prometheus** to scrape Push Gateway in `prometheus.yml`:
```yaml
scrape_configs:
  - job_name: 'pushgateway'
    static_configs:
      - targets: ['localhost:9091']
```

3. **Restart Prometheus** to pick up the new configuration

4. **Push sample metrics**:
```bash
# CI/CD Pipeline metrics
echo "ci_build_duration_seconds 45.2" | curl --data-binary @- http://localhost:9091/metrics/job/ci_pipeline/instance/jenkins
echo "ci_test_count 150" | curl --data-binary @- http://localhost:9091/metrics/job/ci_pipeline/instance/jenkins
echo "ci_deployment_success 1" | curl --data-binary @- http://localhost:9091/metrics/job/ci_pipeline/instance/production

# Application metrics
echo "app_requests_total 1250" | curl --data-binary @- http://localhost:9091/metrics/job/webapp/instance/prod
echo "app_response_time_seconds 0.125" | curl --data-binary @- http://localhost:9091/metrics/job/webapp/instance/prod
echo "app_error_rate 0.02" | curl --data-binary @- http://localhost:9091/metrics/job/webapp/instance/prod
```

### Quick Test Data

Use the provided script for instant test data:
```bash
# One-time sample data push
./push_sample_metrics.sh
```

### Automated Test Data Generation

Use the provided Python script for continuous data generation:
```bash
python3 generate_test_data.py
```

Or create your own `generate_test_data.py`:
```python
#!/usr/bin/env python3
import requests
import time
import random

def push_metrics():
    base_url = "http://localhost:9091/metrics/job"
    
    # CI/CD metrics
    ci_metrics = [
        f"ci_build_duration_seconds {random.uniform(30, 300)}",
        f"ci_test_count {random.randint(50, 500)}",
        f"ci_deployment_success {random.choice([0, 1])}",
        f"ci_code_coverage_percent {random.uniform(60, 95)}",
    ]
    
    # Application metrics
    app_metrics = [
        f"app_requests_total {random.randint(1000, 5000)}",
        f"app_response_time_seconds {random.uniform(0.1, 2.0)}",
        f"app_cpu_usage_percent {random.uniform(10, 80)}",
        f"app_memory_usage_bytes {random.randint(100000000, 1000000000)}",
    ]
    
    # Push CI metrics
    for metric in ci_metrics:
        requests.post(f"{base_url}/ci_pipeline/instance/jenkins", data=metric)
    
    # Push app metrics  
    for metric in app_metrics:
        requests.post(f"{base_url}/webapp/instance/prod", data=metric)
    
    print(f"Pushed {len(ci_metrics + app_metrics)} metrics at {time.strftime('%H:%M:%S')}")

if __name__ == "__main__":
    while True:
        push_metrics()
        time.sleep(30)  # Push every 30 seconds
```

Run the script:
```bash
python3 generate_test_data.py
```

### Verify Data

1. **Push Gateway UI**: http://localhost:9091
2. **Your existing Prometheus UI**: Check for metrics with `{job="ci_pipeline"}`
3. **Your existing Grafana**: Dashboards should now display the synthetic data

### Common Test Metrics

```bash
# Infrastructure metrics
echo "cpu_usage_percent 45.5" | curl --data-binary @- http://localhost:9091/metrics/job/infrastructure/instance/server1
echo "memory_usage_percent 67.2" | curl --data-binary @- http://localhost:9091/metrics/job/infrastructure/instance/server1
echo "disk_usage_percent 23.8" | curl --data-binary @- http://localhost:9091/metrics/job/infrastructure/instance/server1

# Business metrics
echo "sales_revenue_total 45000" | curl --data-binary @- http://localhost:9091/metrics/job/business/instance/ecommerce
echo "user_signups_total 125" | curl --data-binary @- http://localhost:9091/metrics/job/business/instance/webapp
echo "order_conversion_rate 0.034" | curl --data-binary @- http://localhost:9091/metrics/job/business/instance/ecommerce
```

## Limitations

- Query translation is simplified and may not cover all WQL functions
- Some Wavefront-specific features may not have Grafana equivalents
- Complex dashboard layouts may need manual adjustment
- Alert conditions are simplified during migration

## Contributing

Feel free to submit issues or pull requests to improve the migration tool.

## License

This tool is provided as-is for migration purposes.