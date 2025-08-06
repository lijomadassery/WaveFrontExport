#!/usr/bin/env python3
"""
Wavefront to Grafana Dashboard Migration Tool
Extracts dashboards from Wavefront and converts them to Grafana format
"""

import requests
import json
import re
from typing import Dict, List, Any, Optional
from datetime import datetime
import argparse
import logging
from dataclasses import dataclass
from enum import Enum

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DataSourceType(Enum):
    PROMETHEUS = "prometheus"
    INFLUXDB = "influxdb"
    ELASTICSEARCH = "elasticsearch"
    CLOUDWATCH = "cloudwatch"


@dataclass
class MigrationConfig:
    """Configuration for migration process"""
    wavefront_url: str
    wavefront_token: str
    grafana_url: str
    target_datasource: DataSourceType
    datasource_uid: str  # Grafana datasource UID
    # Grafana authentication - either token OR username/password
    grafana_token: Optional[str] = None
    grafana_username: Optional[str] = None
    grafana_password: Optional[str] = None


class WavefrontExtractor:
    """Extract dashboards and alerts from Wavefront"""
    
    def __init__(self, url: str, token: str):
        self.url = url.rstrip('/')
        self.token = token
        self.headers = {'Authorization': f'Bearer {token}'}
    
    def get_all_dashboards(self) -> List[Dict]:
        """Fetch all dashboards from Wavefront"""
        try:
            response = requests.get(
                f"{self.url}/api/v2/dashboard",
                headers=self.headers,
                params={'limit': 1000}
            )
            response.raise_for_status()
            dashboards = response.json().get('response', {}).get('items', [])
            logger.info(f"Found {len(dashboards)} dashboards in Wavefront")
            return dashboards
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch dashboards: {e}")
            return []
    
    def get_dashboard_details(self, dashboard_id: str) -> Optional[Dict]:
        """Fetch detailed dashboard configuration"""
        try:
            response = requests.get(
                f"{self.url}/api/v2/dashboard/{dashboard_id}",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json().get('response')
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch dashboard {dashboard_id}: {e}")
            return None
    
    def get_alerts(self) -> List[Dict]:
        """Fetch all alerts from Wavefront"""
        try:
            response = requests.get(
                f"{self.url}/api/v2/alert",
                headers=self.headers,
                params={'limit': 1000}
            )
            response.raise_for_status()
            alerts = response.json().get('response', {}).get('items', [])
            logger.info(f"Found {len(alerts)} alerts in Wavefront")
            return alerts
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch alerts: {e}")
            return []


class QueryTranslator:
    """Translate WQL queries to target query language"""
    
    @staticmethod
    def wql_to_promql(wql_query: str) -> str:
        """
        Convert Wavefront Query Language to PromQL
        This is a simplified translator - extend based on your specific queries
        """
        # Basic ts() function conversion
        # ts(metric.name, tag="value") -> metric_name{tag="value"}
        
        # Extract metric name and tags from ts() function
        ts_pattern = r'ts\(([\w\.\-]+)(?:,\s*(.+))?\)'
        match = re.search(ts_pattern, wql_query)
        
        if match:
            metric = match.group(1).replace('.', '_')
            tags_str = match.group(2) if match.group(2) else ""
            
            # Parse tags
            tags = {}
            if tags_str:
                tag_pattern = r'(\w+)="([^"]+)"'
                tag_matches = re.findall(tag_pattern, tags_str)
                tags = {k: v for k, v in tag_matches}
            
            # Build PromQL
            if tags:
                tag_str = ', '.join([f'{k}="{v}"' for k, v in tags.items()])
                promql = f"{metric}{{{tag_str}}}"
            else:
                promql = metric
            
            # Handle common WQL functions
            if 'rate(' in wql_query:
                promql = f"rate({promql}[5m])"
            elif 'avg(' in wql_query:
                promql = f"avg({promql})"
            elif 'sum(' in wql_query:
                promql = f"sum({promql})"
            elif 'max(' in wql_query:
                promql = f"max({promql})"
            elif 'min(' in wql_query:
                promql = f"min({promql})"
            
            return promql
        
        # If no pattern matches, return a placeholder
        return f"# TODO: Translate WQL: {wql_query}"
    
    @staticmethod
    def wql_to_influxql(wql_query: str) -> str:
        """
        Convert Wavefront Query Language to InfluxQL
        """
        # Extract metric and tags
        ts_pattern = r'ts\(([\w\.\-]+)(?:,\s*(.+))?\)'
        match = re.search(ts_pattern, wql_query)
        
        if match:
            metric = match.group(1)
            tags_str = match.group(2) if match.group(2) else ""
            
            # Parse tags for WHERE clause
            where_clause = ""
            if tags_str:
                tag_pattern = r'(\w+)="([^"]+)"'
                tag_matches = re.findall(tag_pattern, tags_str)
                if tag_matches:
                    conditions = [f'"{k}"=\'{v}\'' for k, v in tag_matches]
                    where_clause = f" WHERE {' AND '.join(conditions)}"
            
            # Build InfluxQL
            influxql = f'SELECT mean("value") FROM "{metric}"{where_clause}'
            
            # Handle aggregations
            if 'avg(' in wql_query:
                influxql = influxql.replace('mean("value")', 'mean("value")')
            elif 'sum(' in wql_query:
                influxql = influxql.replace('mean("value")', 'sum("value")')
            elif 'max(' in wql_query:
                influxql = influxql.replace('mean("value")', 'max("value")')
            elif 'min(' in wql_query:
                influxql = influxql.replace('mean("value")', 'min("value")')
            
            influxql += ' GROUP BY time($__interval) fill(null)'
            return influxql
        
        return f"-- TODO: Translate WQL: {wql_query}"
    
    @staticmethod
    def translate(wql_query: str, target: DataSourceType) -> str:
        """Main translation dispatcher"""
        if target == DataSourceType.PROMETHEUS:
            return QueryTranslator.wql_to_promql(wql_query)
        elif target == DataSourceType.INFLUXDB:
            return QueryTranslator.wql_to_influxql(wql_query)
        else:
            return f"# Unsupported target: {target.value}. Original WQL: {wql_query}"


class GrafanaDashboardBuilder:
    """Build Grafana dashboard JSON from Wavefront dashboard"""
    
    def __init__(self, datasource_type: DataSourceType, datasource_uid: str):
        self.datasource_type = datasource_type
        self.datasource_uid = datasource_uid
        self.panel_id_counter = 1
    
    def build_dashboard(self, wf_dashboard: Dict) -> Dict:
        """Convert Wavefront dashboard to Grafana format"""
        
        grafana_dashboard = {
            "dashboard": {
                "id": None,
                "uid": None,
                "title": wf_dashboard.get('name', 'Migrated Dashboard'),
                "tags": wf_dashboard.get('tags', []),
                "timezone": "browser",
                "schemaVersion": 39,
                "version": 1,
                "refresh": "30s",
                "time": {
                    "from": "now-6h",
                    "to": "now"
                },
                "panels": [],
                "annotations": {
                    "list": [
                        {
                            "builtIn": 1,
                            "datasource": "-- Grafana --",
                            "enable": True,
                            "hide": True,
                            "iconColor": "rgba(0, 211, 255, 1)",
                            "name": "Annotations & Alerts",
                            "type": "dashboard"
                        }
                    ]
                }
            },
            "overwrite": True
        }
        
        # Process sections and charts
        sections = wf_dashboard.get('sections', [])
        y_pos = 0
        
        for section in sections:
            section_name = section.get('name', 'Section')
            rows = section.get('rows', [])
            
            # Add section header as text panel
            if section_name:
                grafana_dashboard['dashboard']['panels'].append(
                    self._create_text_panel(section_name, y_pos)
                )
                y_pos += 2
            
            for row in rows:
                charts = row.get('charts', [])
                x_pos = 0
                max_height = 8
                
                for chart in charts:
                    panel = self._convert_chart_to_panel(chart, x_pos, y_pos)
                    if panel:
                        grafana_dashboard['dashboard']['panels'].append(panel)
                        x_pos += panel['gridPos']['w']
                        if x_pos >= 24:  # Grafana uses 24-column grid
                            x_pos = 0
                            y_pos += max_height
                
                if x_pos > 0:  # If row has content, move to next row
                    y_pos += max_height
        
        return grafana_dashboard
    
    def _convert_chart_to_panel(self, chart: Dict, x: int, y: int) -> Optional[Dict]:
        """Convert Wavefront chart to Grafana panel"""
        
        chart_type = chart.get('chartSettings', {}).get('type', 'line')
        
        # Map Wavefront chart types to Grafana panel types
        panel_type_map = {
            'line': 'timeseries',
            'area': 'timeseries',
            'column': 'barchart',
            'scatter': 'timeseries',
            'table': 'table',
            'single-stat': 'stat',
            'sparkline': 'sparkline'
        }
        
        panel_type = panel_type_map.get(chart_type, 'timeseries')
        
        panel = {
            "id": self.panel_id_counter,
            "type": panel_type,
            "title": chart.get('name', f'Panel {self.panel_id_counter}'),
            "gridPos": {
                "h": 8,
                "w": min(12, 24 - x),  # Ensure panel fits in remaining space
                "x": x,
                "y": y
            },
            "datasource": {
                "type": self.datasource_type.value,
                "uid": self.datasource_uid
            },
            "targets": []
        }
        
        self.panel_id_counter += 1
        
        # Convert queries
        sources = chart.get('sources', [])
        for idx, source in enumerate(sources):
            query = source.get('query', '')
            if query:
                translated_query = QueryTranslator.translate(query, self.datasource_type)
                
                target = {
                    "refId": chr(65 + idx),  # A, B, C, etc.
                    "datasource": {
                        "type": self.datasource_type.value,
                        "uid": self.datasource_uid
                    }
                }
                
                # Add query based on datasource type
                if self.datasource_type == DataSourceType.PROMETHEUS:
                    target["expr"] = translated_query
                    target["format"] = "time_series"
                elif self.datasource_type == DataSourceType.INFLUXDB:
                    target["query"] = translated_query
                    target["rawQuery"] = True
                
                panel["targets"].append(target)
        
        # Configure panel-specific options
        if panel_type == 'timeseries':
            panel["fieldConfig"] = {
                "defaults": {
                    "color": {"mode": "palette-classic"},
                    "custom": {
                        "axisLabel": "",
                        "axisPlacement": "auto",
                        "barAlignment": 0,
                        "drawStyle": "line" if chart_type == 'line' else "bars",
                        "fillOpacity": 10 if chart_type == 'area' else 0,
                        "gradientMode": "none",
                        "hideFrom": {"tooltip": False, "viz": False, "legend": False},
                        "lineInterpolation": "linear",
                        "lineWidth": 1,
                        "pointSize": 5,
                        "scaleDistribution": {"type": "linear"},
                        "showPoints": "never",
                        "spanNulls": True,
                        "stacking": {"group": "A", "mode": "none"},
                        "thresholdsStyle": {"mode": "off"}
                    },
                    "mappings": [],
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [{"color": "green", "value": None}]
                    },
                    "unit": "short"
                },
                "overrides": []
            }
        elif panel_type == 'stat':
            panel["fieldConfig"] = {
                "defaults": {
                    "color": {"mode": "thresholds"},
                    "mappings": [],
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {"color": "green", "value": None},
                            {"color": "red", "value": 80}
                        ]
                    },
                    "unit": "short"
                },
                "overrides": []
            }
            panel["options"] = {
                "colorMode": "value",
                "graphMode": "area",
                "justifyMode": "auto",
                "orientation": "auto",
                "reduceOptions": {
                    "values": False,
                    "fields": "",
                    "calcs": ["lastNotNull"]
                },
                "textMode": "auto"
            }
        
        return panel
    
    def _create_text_panel(self, text: str, y: int) -> Dict:
        """Create a text panel for section headers"""
        panel = {
            "id": self.panel_id_counter,
            "type": "text",
            "title": "",
            "gridPos": {"h": 2, "w": 24, "x": 0, "y": y},
            "options": {
                "mode": "markdown",
                "content": f"## {text}"
            }
        }
        self.panel_id_counter += 1
        return panel


class GrafanaAlertBuilder:
    """Build Grafana alerts from Wavefront alerts"""
    
    def __init__(self, datasource_type: DataSourceType, datasource_uid: str):
        self.datasource_type = datasource_type
        self.datasource_uid = datasource_uid
    
    def build_alert(self, wf_alert: Dict) -> Dict:
        """Convert Wavefront alert to Grafana alert rule"""
        
        # Translate the condition query
        condition = wf_alert.get('condition', '')
        translated_query = QueryTranslator.translate(condition, self.datasource_type)
        
        alert_rule = {
            "uid": None,
            "title": wf_alert.get('name', 'Migrated Alert'),
            "condition": "A",
            "data": [
                {
                    "refId": "A",
                    "relativeTimeRange": {
                        "from": 600,
                        "to": 0
                    },
                    "queryType": "",
                    "model": {
                        "expr": translated_query if self.datasource_type == DataSourceType.PROMETHEUS else "",
                        "query": translated_query if self.datasource_type == DataSourceType.INFLUXDB else "",
                        "refId": "A",
                        "datasource": {
                            "type": self.datasource_type.value,
                            "uid": self.datasource_uid
                        }
                    },
                    "datasourceUid": self.datasource_uid,
                    "conditions": [
                        {
                            "evaluator": {
                                "params": [self._extract_threshold(wf_alert)],
                                "type": "gt"
                            },
                            "operator": {"type": "and"},
                            "query": {"params": ["A"]},
                            "reducer": {"params": [], "type": "last"},
                            "type": "query"
                        }
                    ]
                }
            ],
            "noDataState": "NoData",
            "execErrState": "Alerting",
            "for": self._convert_duration(wf_alert.get('minutes', 5)),
            "annotations": {
                "description": wf_alert.get('additionalInformation', ''),
                "runbook_url": "",
                "summary": wf_alert.get('name', '')
            },
            "labels": {}
        }
        
# {
#     "apiVersion": 1,
#     "groups": [
#         {
#             "orgId": 1,
#             "name": "5-minutes",
#             "folder": "misc",
#             "interval": "5m",
#             "rules": [
#                 {
#                     "uid": "eb2f850d-822d-4ea3-b227-e11e89031bba",
#                     "title": "Test 1",
#                     "condition": "C",
#                     "data": [
#                         {
#                             "refId": "A",
#                             "relativeTimeRange": {
#                                 "from": 600,
#                                 "to": 0
#                             },
#                             "datasourceUid": "d3b773fb-9d60-4f8c-884d-0734feb77810",
#                             "model": {
#                                 "datasource": {
#                                     "type": "prometheus",
#                                     "uid": "d3b773fb-9d60-4f8c-884d-0734feb77810"
#                                 },
#                                 "disableTextWrap": false,
#                                 "editorMode": "builder",
#                                 "expr": ":node_memory_MemAvailable_bytes:sum",
#                                 "fullMetaSearch": false,
#                                 "hide": false,
#                                 "includeNullMetadata": true,
#                                 "instant": true,
#                                 "intervalMs": 1000,
#                                 "legendFormat": "__auto",
#                                 "maxDataPoints": 43200,
#                                 "range": false,
#                                 "refId": "A",
#                                 "useBackend": false
#                             }
#                         },
#                         {
#                             "refId": "B",
#                             "relativeTimeRange": {
#                                 "from": 600,
#                                 "to": 0
#                             },
#                             "datasourceUid": "__expr__",
#                             "model": {
#                                 "conditions": [
#                                     {
#                                         "evaluator": {
#                                             "params": [],
#                                             "type": "gt"
#                                         },
#                                         "operator": {
#                                             "type": "and"
#                                         },
#                                         "query": {
#                                             "params": [
#                                                 "B"
#                                             ]
#                                         },
#                                         "reducer": {
#                                             "params": [],
#                                             "type": "last"
#                                         },
#                                         "type": "query"
#                                     }
#                                 ],
#                                 "datasource": {
#                                     "type": "__expr__",
#                                     "uid": "__expr__"
#                                 },
#                                 "expression": "A",
#                                 "intervalMs": 1000,
#                                 "maxDataPoints": 43200,
#                                 "reducer": "last",
#                                 "refId": "B",
#                                 "type": "reduce"
#                             }
#                         },
#                         {
#                             "refId": "C",
#                             "relativeTimeRange": {
#                                 "from": 600,
#                                 "to": 0
#                             },
#                             "datasourceUid": "__expr__",
#                             "model": {
#                                 "conditions": [
#                                     {
#                                         "evaluator": {
#                                             "params": [
#                                                 0
#                                             ],
#                                             "type": "gt"
#                                         },
#                                         "operator": {
#                                             "type": "and"
#                                         },
#                                         "query": {
#                                             "params": [
#                                                 "C"
#                                             ]
#                                         },
#                                         "reducer": {
#                                             "params": [],
#                                             "type": "last"
#                                         },
#                                         "type": "query"
#                                     }
#                                 ],
#                                 "datasource": {
#                                     "type": "__expr__",
#                                     "uid": "__expr__"
#                                 },
#                                 "expression": "B",
#                                 "intervalMs": 1000,
#                                 "maxDataPoints": 43200,
#                                 "refId": "C",
#                                 "type": "threshold"
#                             }
#                         }
#                     ],
#                     "noDataState": "NoData",
#                     "execErrState": "Error",
#                     "for": "5m",
#                     "annotations": {},
#                     "labels": {},
#                     "isPaused": false
#                 }
#             ]
#         }
#     ]
# }
        # Add tags as labels
        if 'tags' in wf_alert:
            for tag in wf_alert.get('tags', []):
                alert_rule['labels'][f'tag_{tag}'] = tag
        
        return alert_rule
    
    def _extract_threshold(self, wf_alert: Dict) -> float:
        """Extract threshold value from Wavefront alert condition"""
        # This is simplified - you may need to parse the condition more carefully
        condition = wf_alert.get('condition', '')
        # Look for comparison operators
        import re
        match = re.search(r'[<>]=?\s*([\d.]+)', condition)
        if match:
            return float(match.group(1))
        return 0
    
    def _convert_duration(self, minutes: int) -> str:
        """Convert minutes to Grafana duration string"""
        if minutes < 60:
            return f"{minutes}m"
        elif minutes < 1440:
            return f"{minutes // 60}h"
        else:
            return f"{minutes // 1440}d"


class GrafanaImporter:
    """Import dashboards and alerts to Grafana"""
    
    def __init__(self, url: str, token: Optional[str] = None, username: Optional[str] = None, password: Optional[str] = None):
        self.url = url.rstrip('/')
        self.auth = None
        
        if token:
            # Token-based authentication
            self.headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
        elif username and password:
            # Basic authentication
            self.headers = {
                'Content-Type': 'application/json'
            }
            self.auth = (username, password)
        else:
            raise ValueError("Either token or username/password must be provided for Grafana authentication")
    
    def import_dashboard(self, dashboard_json: Dict) -> bool:
        """Import dashboard to Grafana"""
        try:
            response = requests.post(
                f"{self.url}/api/dashboards/db",
                headers=self.headers,
                auth=self.auth,
                json=dashboard_json
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"Successfully imported dashboard: {result.get('url')}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to import dashboard: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            return False
    
    def import_alert(self, alert_json: Dict) -> bool:
        """Import alert rule to Grafana"""
        try:
            response = requests.post(
                f"{self.url}/api/v1/provisioning/alert-rules",
                headers=self.headers,
                auth=self.auth,
                json=alert_json
            )
            response.raise_for_status()
            logger.info(f"Successfully imported alert: {alert_json.get('title')}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to import alert: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            return False


class MigrationOrchestrator:
    """Orchestrate the complete migration process"""
    
    def __init__(self, config: MigrationConfig):
        self.config = config
        self.extractor = WavefrontExtractor(config.wavefront_url, config.wavefront_token)
        self.dashboard_builder = GrafanaDashboardBuilder(
            config.target_datasource, 
            config.datasource_uid
        )
        self.alert_builder = GrafanaAlertBuilder(
            config.target_datasource,
            config.datasource_uid
        )
        self.importer = GrafanaImporter(
            config.grafana_url, 
            token=config.grafana_token,
            username=config.grafana_username,
            password=config.grafana_password
        )
    
    def migrate_dashboards(self, dashboard_ids: Optional[List[str]] = None):
        """Migrate dashboards from Wavefront to Grafana"""
        
        # Get dashboards to migrate
        if dashboard_ids:
            dashboards = []
            for dash_id in dashboard_ids:
                dash = self.extractor.get_dashboard_details(dash_id)
                if dash:
                    dashboards.append(dash)
        else:
            # Get all dashboards
            dashboard_list = self.extractor.get_all_dashboards()
            dashboards = []
            for dash_summary in dashboard_list:
                dash = self.extractor.get_dashboard_details(dash_summary['id'])
                if dash:
                    dashboards.append(dash)
        
        logger.info(f"Migrating {len(dashboards)} dashboards...")
        
        success_count = 0
        failed_dashboards = []
        
        for wf_dashboard in dashboards:
            try:
                logger.info(f"Processing dashboard: {wf_dashboard.get('name', 'Unknown')}")
                
                # Convert to Grafana format
                grafana_dashboard = self.dashboard_builder.build_dashboard(wf_dashboard)
                
                # Save to file for review
                filename = f"dashboard_{wf_dashboard.get('id', 'unknown')}.json"
                with open(filename, 'w') as f:
                    json.dump(grafana_dashboard, f, indent=2)
                logger.info(f"Saved dashboard JSON to {filename}")
                
                # Import to Grafana
                if self.importer.import_dashboard(grafana_dashboard):
                    success_count += 1
                else:
                    failed_dashboards.append(wf_dashboard.get('name', 'Unknown'))
                    
            except Exception as e:
                logger.error(f"Error processing dashboard {wf_dashboard.get('name')}: {e}")
                failed_dashboards.append(wf_dashboard.get('name', 'Unknown'))
        
        logger.info(f"Migration complete: {success_count}/{len(dashboards)} dashboards successful")
        if failed_dashboards:
            logger.warning(f"Failed dashboards: {', '.join(failed_dashboards)}")
    
    def migrate_alerts(self, alert_ids: Optional[List[str]] = None):
        """Migrate alerts from Wavefront to Grafana"""
        
        # Get alerts to migrate
        alerts = self.extractor.get_alerts()
        if alert_ids:
            alerts = [a for a in alerts if a['id'] in alert_ids]
        
        logger.info(f"Migrating {len(alerts)} alerts...")
        
        success_count = 0
        failed_alerts = []
        
        for wf_alert in alerts:
            try:
                logger.info(f"Processing alert: {wf_alert.get('name', 'Unknown')}")
                
                # Convert to Grafana format
                grafana_alert = self.alert_builder.build_alert(wf_alert)
                
                # Save to file for review
                filename = f"alert_{wf_alert.get('id', 'unknown')}.json"
                with open(filename, 'w') as f:
                    json.dump(grafana_alert, f, indent=2)
                logger.info(f"Saved alert JSON to {filename}")
                
                # Import to Grafana
                if self.importer.import_alert(grafana_alert):
                    success_count += 1
                else:
                    failed_alerts.append(wf_alert.get('name', 'Unknown'))
                    
            except Exception as e:
                logger.error(f"Error processing alert {wf_alert.get('name')}: {e}")
                failed_alerts.append(wf_alert.get('name', 'Unknown'))
        
        logger.info(f"Migration complete: {success_count}/{len(alerts)} alerts successful")
        if failed_alerts:
            logger.warning(f"Failed alerts: {', '.join(failed_alerts)}")


def main():
    parser = argparse.ArgumentParser(description='Migrate Wavefront dashboards and alerts to Grafana')
    parser.add_argument('--wavefront-url', required=True, help='Wavefront API URL')
    parser.add_argument('--wavefront-token', required=True, help='Wavefront API token')
    parser.add_argument('--grafana-url', required=True, help='Grafana API URL')
    # Grafana authentication - either token OR username/password
    auth_group = parser.add_mutually_exclusive_group(required=True)
    auth_group.add_argument('--grafana-token', help='Grafana API token')
    auth_group.add_argument('--grafana-credentials', nargs=2, metavar=('USERNAME', 'PASSWORD'), 
                           help='Grafana username and password')
    parser.add_argument('--datasource-type', required=True, 
                       choices=['prometheus', 'influxdb', 'elasticsearch', 'cloudwatch'],
                       help='Target datasource type in Grafana')
    parser.add_argument('--datasource-uid', required=True, help='Grafana datasource UID')
    parser.add_argument('--dashboards', nargs='*', help='Specific dashboard IDs to migrate')
    parser.add_argument('--alerts', nargs='*', help='Specific alert IDs to migrate')
    parser.add_argument('--skip-dashboards', action='store_true', help='Skip dashboard migration')
    parser.add_argument('--skip-alerts', action='store_true', help='Skip alert migration')
    
    args = parser.parse_args()
    
    # Parse Grafana authentication
    grafana_token = None
    grafana_username = None
    grafana_password = None
    
    if args.grafana_token:
        grafana_token = args.grafana_token
    elif args.grafana_credentials:
        grafana_username, grafana_password = args.grafana_credentials
    
    # Create configuration
    config = MigrationConfig(
        wavefront_url=args.wavefront_url,
        wavefront_token=args.wavefront_token,
        grafana_url=args.grafana_url,
        target_datasource=DataSourceType(args.datasource_type),
        datasource_uid=args.datasource_uid,
        grafana_token=grafana_token,
        grafana_username=grafana_username,
        grafana_password=grafana_password
    )
    
    # Run migration
    orchestrator = MigrationOrchestrator(config)
    
    if not args.skip_dashboards:
        orchestrator.migrate_dashboards(args.dashboards)
    
    if not args.skip_alerts:
        orchestrator.migrate_alerts(args.alerts)
    
    logger.info("Migration process completed!")


if __name__ == "__main__":
    main()
