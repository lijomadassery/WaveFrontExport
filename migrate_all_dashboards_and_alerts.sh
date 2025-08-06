#!/bin/bash
#
# Set/Load env variables
#
. .env_dev

#
# Migrate all dashboards and alerts from Wavefront to Grafana
#
echo "."
echo "🚀 Migrating all dashboards and alerts from Wavefront to Grafana..."
python3 wavefront-grafana-migrator.py \
  --wavefront-url $WAVEFRONT_URL \
  --wavefront-token $WAVEFRONT_TOKEN \
  --grafana-url $GRAFANA_URL \
  --grafana-token $GRAFANA_TOKEN \
  --datasource-type prometheus \
  --datasource-uid $DATASOURCE_UID
if [ $? -ne 0 ]; then
    echo "❌ Migration failed. Please check the logs for details."
    exit 1
fi
echo "."
echo "✅ Migration completed successfully."
echo "📊 View your data at: $GRAFANA_URL/dashboards"

