#!/usr/bin/env python3
"""
Generate synthetic test data for Grafana dashboards using Prometheus Push Gateway

This script pushes various types of metrics to help test dashboards when real data isn't available.
Perfect for CI/CD, application monitoring, and infrastructure dashboards.

Usage:
    python3 generate_test_data.py

Requirements:
    - Prometheus Push Gateway running on localhost:9091
    - pip install requests

Start Push Gateway:
    docker run -d -p 9091:9091 prom/pushgateway
"""

import requests
import time
import random
import sys
from datetime import datetime

class MetricsGenerator:
    def __init__(self, pushgateway_url="http://localhost:9091"):
        self.base_url = f"{pushgateway_url}/metrics/job"
        self.session = requests.Session()
    
    def push_metric(self, job, instance, metric_line):
        """Push a single metric to Push Gateway"""
        url = f"{self.base_url}/{job}/instance/{instance}"
        try:
            response = self.session.post(url, data=metric_line)
            if response.status_code != 200:
                print(f"Warning: Failed to push metric to {job}/{instance}: {response.status_code}")
        except Exception as e:
            print(f"Error pushing metric to {job}/{instance}: {e}")
    
    def generate_cicd_metrics(self):
        """Generate CI/CD pipeline metrics"""
        job = "ci_pipeline"
        instance = "jenkins"
        
        metrics = [
            f"ci_build_duration_seconds {random.uniform(30, 300):.2f}",
            f"ci_test_count {random.randint(50, 500)}",
            f"ci_deployment_success {random.choice([0, 1])}",
            f"ci_code_coverage_percent {random.uniform(60, 95):.2f}",
            f"ci_failed_tests {random.randint(0, 25)}",
            f"ci_pipeline_runs_total {random.randint(1, 10)}",
            f"ci_artifact_size_mb {random.uniform(5, 500):.2f}",
        ]
        
        for metric in metrics:
            self.push_metric(job, instance, metric)
    
    def generate_app_metrics(self):
        """Generate application performance metrics"""
        job = "webapp"
        instance = "production"
        
        metrics = [
            f"app_requests_total {random.randint(1000, 5000)}",
            f"app_response_time_seconds {random.uniform(0.05, 2.0):.3f}",
            f"app_error_rate {random.uniform(0.001, 0.05):.4f}",
            f"app_cpu_usage_percent {random.uniform(10, 80):.2f}",
            f"app_memory_usage_bytes {random.randint(100000000, 1000000000)}",
            f"app_active_connections {random.randint(50, 1000)}",
            f"app_cache_hit_rate {random.uniform(0.7, 0.99):.3f}",
        ]
        
        for metric in metrics:
            self.push_metric(job, instance, metric)
    
    def generate_infrastructure_metrics(self):
        """Generate infrastructure monitoring metrics"""
        servers = ["server1", "server2", "server3"]
        job = "infrastructure"
        
        for server in servers:
            metrics = [
                f"cpu_usage_percent {random.uniform(5, 85):.2f}",
                f"memory_usage_percent {random.uniform(20, 80):.2f}",
                f"disk_usage_percent {random.uniform(10, 70):.2f}",
                f"network_io_bytes_per_sec {random.randint(1000000, 100000000)}",
                f"load_average {random.uniform(0.5, 4.0):.2f}",
                f"disk_io_ops_per_sec {random.randint(10, 1000)}",
            ]
            
            for metric in metrics:
                self.push_metric(job, server, metric)
    
    def generate_business_metrics(self):
        """Generate business/KPI metrics"""
        job = "business"
        instance = "ecommerce"
        
        metrics = [
            f"sales_revenue_total {random.randint(10000, 100000)}",
            f"user_signups_total {random.randint(50, 500)}",
            f"order_conversion_rate {random.uniform(0.02, 0.08):.4f}",
            f"page_views_total {random.randint(5000, 50000)}",
            f"cart_abandonment_rate {random.uniform(0.3, 0.7):.3f}",
            f"customer_satisfaction_score {random.uniform(3.5, 5.0):.2f}",
            f"support_tickets_open {random.randint(5, 100)}",
        ]
        
        for metric in metrics:
            self.push_metric(job, instance, metric)
    
    def generate_database_metrics(self):
        """Generate database performance metrics"""
        databases = ["mysql-prod", "postgres-analytics", "redis-cache"]
        job = "database"
        
        for db in databases:
            if "redis" in db:
                # Redis-specific metrics
                metrics = [
                    f"redis_connected_clients {random.randint(10, 200)}",
                    f"redis_memory_usage_bytes {random.randint(100000000, 2000000000)}",
                    f"redis_keyspace_hits_total {random.randint(1000, 50000)}",
                    f"redis_keyspace_misses_total {random.randint(10, 500)}",
                ]
            else:
                # SQL database metrics
                metrics = [
                    f"db_connections_active {random.randint(5, 100)}",
                    f"db_query_duration_seconds {random.uniform(0.001, 1.0):.4f}",
                    f"db_slow_queries_total {random.randint(0, 10)}",
                    f"db_size_bytes {random.randint(1000000000, 100000000000)}",
                    f"db_transactions_per_sec {random.randint(10, 1000)}",
                ]
            
            for metric in metrics:
                self.push_metric(job, db, metric)
    
    def generate_all_metrics(self):
        """Generate all types of metrics"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Generating synthetic metrics...")
        
        try:
            self.generate_cicd_metrics()
            self.generate_app_metrics()
            self.generate_infrastructure_metrics()
            self.generate_business_metrics()
            self.generate_database_metrics()
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ All metrics pushed successfully")
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Error generating metrics: {e}")

def main():
    print("🚀 Synthetic Data Generator for Grafana Dashboards")
    print("=" * 50)
    print("This script generates test data for various dashboard types:")
    print("• CI/CD Pipeline metrics")
    print("• Application performance metrics") 
    print("• Infrastructure monitoring metrics")
    print("• Business/KPI metrics")
    print("• Database performance metrics")
    print()
    print("📋 Prerequisites:")
    print("• Prometheus Push Gateway running on localhost:9091")
    print("• Run: docker run -d -p 9091:9091 prom/pushgateway")
    print()
    
    generator = MetricsGenerator()
    
    # Test connection
    try:
        response = requests.get("http://localhost:9091/metrics")
        if response.status_code != 200:
            print("❌ Cannot connect to Push Gateway at localhost:9091")
            print("Please start it with: docker run -d -p 9091:9091 prom/pushgateway")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Cannot connect to Push Gateway: {e}")
        print("Please start it with: docker run -d -p 9091:9091 prom/pushgateway")
        sys.exit(1)
    
    print("✅ Connected to Push Gateway")
    print("🔄 Starting metric generation (Ctrl+C to stop)...")
    print()
    
    try:
        while True:
            generator.generate_all_metrics()
            print(f"💤 Waiting 30 seconds before next batch...")
            print()
            time.sleep(30)
    except KeyboardInterrupt:
        print()
        print("⏹️  Stopped by user")
        print("📊 Check your data at:")
        print("• Push Gateway: http://localhost:9091")
        print("• Prometheus: http://localhost:9090")
        print("• Grafana: Your dashboards should now show data")

if __name__ == "__main__":
    main()