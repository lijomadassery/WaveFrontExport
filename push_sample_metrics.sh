#!/bin/bash
#
# Quick script to push sample metrics to Prometheus Push Gateway
# Perfect for testing Grafana dashboards with synthetic data
#
# Prerequisites: 
#   1. docker run -d -p 9091:9091 prom/pushgateway
#   2. Configure Prometheus to scrape localhost:9091 (see README.md)
#   3. Restart Prometheus
#

PUSHGATEWAY="http://localhost:9091/metrics/job"

echo "🚀 Pushing sample metrics to Push Gateway..."

# Function to push metric
push_metric() {
    local metric="$1"
    local job="$2" 
    local instance="$3"
    
    echo "$metric" | curl -s --data-binary @- "$PUSHGATEWAY/$job/instance/$instance"
    if [ $? -eq 0 ]; then
        echo "✅ $job/$instance: $metric"
    else
        echo "❌ Failed to push: $job/$instance: $metric"
    fi
}

# Check if Push Gateway is running
if ! curl -s "$PUSHGATEWAY/../metrics" > /dev/null; then
    echo "❌ Cannot connect to Push Gateway at localhost:9091"
    echo "Please start it with: docker run -d -p 9091:9091 prom/pushgateway"
    exit 1
fi

echo "✅ Connected to Push Gateway"
echo

# CI/CD Pipeline Metrics
echo "📦 Pushing CI/CD metrics..."
push_metric "ci_build_duration_seconds $(shuf -i 30-300 -n 1)" "ci_pipeline" "jenkins"
push_metric "ci_test_count $(shuf -i 50-500 -n 1)" "ci_pipeline" "jenkins"
push_metric "ci_deployment_success $(shuf -i 0-1 -n 1)" "ci_pipeline" "production"
push_metric "ci_code_coverage_percent $(shuf -i 60-95 -n 1)" "ci_pipeline" "jenkins"
push_metric "ci_failed_tests $(shuf -i 0-25 -n 1)" "ci_pipeline" "jenkins"

# Application Metrics
echo "🌐 Pushing application metrics..."
push_metric "app_requests_total $(shuf -i 1000-5000 -n 1)" "webapp" "production"
push_metric "app_response_time_seconds 0.$(shuf -i 50-2000 -n 1)" "webapp" "production"
push_metric "app_error_rate 0.0$(shuf -i 1-50 -n 1)" "webapp" "production"
push_metric "app_cpu_usage_percent $(shuf -i 10-80 -n 1)" "webapp" "production"
push_metric "app_memory_usage_bytes $(shuf -i 100000000-1000000000 -n 1)" "webapp" "production"

# Infrastructure Metrics
echo "🖥️  Pushing infrastructure metrics..."
for server in server1 server2 server3; do
    push_metric "cpu_usage_percent $(shuf -i 5-85 -n 1)" "infrastructure" "$server"
    push_metric "memory_usage_percent $(shuf -i 20-80 -n 1)" "infrastructure" "$server"
    push_metric "disk_usage_percent $(shuf -i 10-70 -n 1)" "infrastructure" "$server"
done

# Business Metrics
echo "💼 Pushing business metrics..."
push_metric "sales_revenue_total $(shuf -i 10000-100000 -n 1)" "business" "ecommerce"
push_metric "user_signups_total $(shuf -i 50-500 -n 1)" "business" "webapp"
push_metric "order_conversion_rate 0.0$(shuf -i 20-80 -n 1)" "business" "ecommerce"
push_metric "page_views_total $(shuf -i 5000-50000 -n 1)" "business" "webapp"

# Database Metrics
echo "🗄️  Pushing database metrics..."
push_metric "db_connections_active $(shuf -i 5-100 -n 1)" "database" "mysql-prod"
push_metric "db_query_duration_seconds 0.0$(shuf -i 1-1000 -n 1)" "database" "mysql-prod"
push_metric "db_slow_queries_total $(shuf -i 0-10 -n 1)" "database" "mysql-prod"

echo
echo "🎉 Sample metrics pushed successfully!"
echo
echo "📊 View your data at:"
echo "• Push Gateway UI: http://localhost:9091"
echo "• Prometheus UI: http://localhost:9090"
echo "• Grafana: Your dashboards should now display data"
echo
echo "🔄 To continuously generate data, use:"
echo "python3 generate_test_data.py"