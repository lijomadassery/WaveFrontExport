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
            
            # Handle complex WQL functions with proper nesting
            wql_lower = wql_query.lower()
            
            # Handle moving averages: mavg(1m, ts(...)) -> avg_over_time(...[1m])
            mavg_pattern = r'mavg\((\d+[smhd]),\s*ts\('
            if re.search(mavg_pattern, wql_lower):
                mavg_match = re.search(r'mavg\((\d+[smhd])', wql_lower)
                if mavg_match:
                    duration = mavg_match.group(1)
                    promql = f"avg_over_time({promql}[{duration}])"
            
            # Handle rate: rate(ts(...)) -> rate(...[5m])
            elif 'rate(' in wql_lower:
                # Extract rate duration if specified, default to 5m
                rate_pattern = r'rate\((\d+[smhd]),\s*ts\('
                rate_match = re.search(rate_pattern, wql_lower)
                duration = rate_match.group(1) if rate_match else '5m'
                promql = f"rate({promql}[{duration}])"
            
            # Handle percentiles: percentile(95, ts(...)) -> quantile(0.95, ...)
            elif 'percentile(' in wql_lower:
                percentile_match = re.search(r'percentile\((\d+)', wql_lower)
                if percentile_match:
                    percentile = float(percentile_match.group(1)) / 100
                    promql = f"quantile({percentile}, {promql})"
            
            # Handle standard aggregations
            elif 'avg(' in wql_lower:
                promql = f"avg({promql})"
            elif 'sum(' in wql_lower:
                promql = f"sum({promql})"
            elif 'max(' in wql_lower:
                promql = f"max({promql})"
            elif 'min(' in wql_lower:
                promql = f"min({promql})"
            elif 'count(' in wql_lower:
                promql = f"count({promql})"
            elif 'stddev(' in wql_lower:
                promql = f"stddev({promql})"
            
            # Handle derivatives: deriv(ts(...)) -> deriv(...[5m])
            elif 'deriv(' in wql_lower:
                promql = f"deriv({promql}[5m])"
            
            # Handle last: last(ts(...)) -> last_over_time(...[5m])
            elif 'last(' in wql_lower:
                promql = f"last_over_time({promql}[5m])"
            
            # Handle aliasMetric: aliasMetric(ts(...), "name") -> label_replace(..., "__name__", "name", "", "")
            alias_pattern = r'aliasMetric\(.*,\s*["\']([^"\']+)["\']'
            alias_match = re.search(alias_pattern, wql_query)
            if alias_match:
                new_name = alias_match.group(1)
                promql = f'label_replace({promql}, "__name__", "{new_name}", "", "")'
            
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
        
        # Parse the Wavefront condition for queries and thresholds
        condition = wf_alert.get('condition', '')
        queries, threshold_info = self._parse_wavefront_condition(condition)
        
        # Determine reducer type based on WQL functions
        reducer_type = self._determine_reducer_type(condition)
        
        # Build the data array with chained steps
        data = []
        
        # Step A: Main query
        if queries:
            # Handle both simple string queries and dict queries
            if isinstance(queries[0], dict):
                primary_query = queries[0]['query']
                threshold_info = {
                    'operator': self._map_operator(queries[0]['operator']),
                    'value': queries[0]['value']
                }
            else:
                primary_query = queries[0]
            
            translated_query = QueryTranslator.translate(primary_query, self.datasource_type)
            
            data.append({
                "refId": "A",
                "relativeTimeRange": {
                    "from": 600,
                    "to": 0
                },
                "datasourceUid": self.datasource_uid,
                "model": {
                    "datasource": {
                        "type": self.datasource_type.value,
                        "uid": self.datasource_uid
                    },
                    "expr": translated_query if self.datasource_type == DataSourceType.PROMETHEUS else "",
                    "query": translated_query if self.datasource_type == DataSourceType.INFLUXDB else "",
                    "instant": True,
                    "intervalMs": 1000,
                    "maxDataPoints": 43200,
                    "refId": "A"
                }
            })
            
            # Step B: Reduce expression (convert series to single value)
            data.append({
                "refId": "B",
                "relativeTimeRange": {
                    "from": 600,
                    "to": 0
                },
                "datasourceUid": "__expr__",
                "model": {
                    "conditions": [
                        {
                            "evaluator": {
                                "params": [],
                                "type": "gt"
                            },
                            "operator": {
                                "type": "and"
                            },
                            "query": {
                                "params": ["B"]
                            },
                            "reducer": {
                                "params": [],
                                "type": "last"
                            },
                            "type": "query"
                        }
                    ],
                    "datasource": {
                        "type": "__expr__",
                        "uid": "__expr__"
                    },
                    "expression": "A",
                    "intervalMs": 1000,
                    "maxDataPoints": 43200,
                    "reducer": reducer_type,
                    "refId": "B",
                    "type": "reduce"
                }
            })
            
            # Step C: Threshold evaluation
            data.append({
                "refId": "C",
                "relativeTimeRange": {
                    "from": 600,
                    "to": 0
                },
                "datasourceUid": "__expr__",
                "model": {
                    "conditions": [
                        {
                            "evaluator": {
                                "params": [threshold_info.get('value', 0)],
                                "type": threshold_info.get('operator', 'gt')
                            },
                            "operator": {
                                "type": "and"
                            },
                            "query": {
                                "params": ["C"]
                            },
                            "reducer": {
                                "params": [],
                                "type": "last"
                            },
                            "type": "query"
                        }
                    ],
                    "datasource": {
                        "type": "__expr__",
                        "uid": "__expr__"
                    },
                    "expression": "B",
                    "intervalMs": 1000,
                    "maxDataPoints": 43200,
                    "refId": "C",
                    "type": "threshold"
                }
            })
            
            # Handle additional queries for AND/OR conditions
            if len(queries) > 1:
                # Add support for multiple query conditions
                current_ref = "C"
                
                for i, query_item in enumerate(queries[1:], start=1):
                    prev_ref = current_ref
                    query_ref = chr(68 + i * 3)  # D, G, J, etc.
                    reduce_ref = chr(69 + i * 3)  # E, H, K, etc.
                    threshold_ref = chr(70 + i * 3)  # F, I, L, etc.
                    
                    # Extract query and threshold from dict or string
                    if isinstance(query_item, dict):
                        query = query_item['query']
                        query_threshold = {
                            'operator': self._map_operator(query_item['operator']),
                            'value': query_item['value']
                        }
                    else:
                        query = query_item
                        query_threshold = threshold_info
                    
                    # Add query step
                    translated_query = QueryTranslator.translate(query, self.datasource_type)
                    data.append({
                        "refId": query_ref,
                        "relativeTimeRange": {"from": 600, "to": 0},
                        "datasourceUid": self.datasource_uid,
                        "model": {
                            "datasource": {
                                "type": self.datasource_type.value,
                                "uid": self.datasource_uid
                            },
                            "expr": translated_query if self.datasource_type == DataSourceType.PROMETHEUS else "",
                            "query": translated_query if self.datasource_type == DataSourceType.INFLUXDB else "",
                            "instant": True,
                            "intervalMs": 1000,
                            "maxDataPoints": 43200,
                            "refId": query_ref
                        }
                    })
                    
                    # Add reduce step
                    data.append({
                        "refId": reduce_ref,
                        "relativeTimeRange": {"from": 600, "to": 0},
                        "datasourceUid": "__expr__",
                        "model": {
                            "datasource": {"type": "__expr__", "uid": "__expr__"},
                            "expression": query_ref,
                            "reducer": reducer_type,
                            "type": "reduce",
                            "refId": reduce_ref
                        }
                    })
                    
                    # Add threshold step
                    data.append({
                        "refId": threshold_ref,
                        "relativeTimeRange": {"from": 600, "to": 0},
                        "datasourceUid": "__expr__",
                        "model": {
                            "conditions": [{
                                "evaluator": {
                                    "params": [query_threshold.get('value', 0)],
                                    "type": query_threshold.get('operator', 'gt')
                                },
                                "operator": {"type": "and"},
                                "query": {"params": [threshold_ref]},
                                "reducer": {"params": [], "type": "last"},
                                "type": "query"
                            }],
                            "datasource": {"type": "__expr__", "uid": "__expr__"},
                            "expression": reduce_ref,
                            "type": "threshold",
                            "refId": threshold_ref
                        }
                    })
                    
                    # Add math expression to combine conditions
                    combine_ref = chr(71 + i * 3)  # G, J, M, etc.
                    operator = self._extract_logical_operator(condition, i)
                    math_expr = f"${prev_ref} {operator} ${threshold_ref}"
                    
                    data.append({
                        "refId": combine_ref,
                        "relativeTimeRange": {"from": 600, "to": 0},
                        "datasourceUid": "__expr__",
                        "model": {
                            "datasource": {"type": "__expr__", "uid": "__expr__"},
                            "expression": math_expr,
                            "type": "math",
                            "refId": combine_ref
                        }
                    })
                    
                    current_ref = combine_ref
                
                # Update final condition reference
                alert_rule["condition"] = current_ref
        
        alert_rule = {
            "uid": None,
            "title": wf_alert.get('name', 'Migrated Alert'),
            "condition": "C",  # Final step is the condition
            "data": data,
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
       
        # Add tags as labels
        if 'tags' in wf_alert:
            for tag in wf_alert.get('tags', []):
                alert_rule['labels'][f'tag_{tag}'] = tag
        
        return alert_rule
    
    def _parse_wavefront_condition(self, condition: str) -> tuple:
        """Parse Wavefront condition to extract queries and threshold info"""
        import re
        
        queries = []
        threshold_info = {'operator': 'gt', 'value': 0}
        
        # Handle complex conditions with AND/OR
        # Split by AND/OR while preserving the operators
        parts = re.split(r'\s+(AND|OR)\s+', condition, flags=re.IGNORECASE)
        
        for part in parts:
            if part.upper() in ['AND', 'OR']:
                continue
                
            # Extract ts() queries from this part
            ts_pattern = r'ts\([^)]+\)'
            ts_matches = re.findall(ts_pattern, part)
            
            if ts_matches:
                # Each ts() with its condition is a separate query
                for ts_match in ts_matches:
                    # Find the threshold for this specific query
                    remaining = part.replace(ts_match, '').strip()
                    threshold_match = re.search(r'([<>]=?|=)\s*([\d.]+)', remaining)
                    
                    if threshold_match:
                        queries.append({
                            'query': ts_match,
                            'operator': threshold_match.group(1),
                            'value': float(threshold_match.group(2))
                        })
                    else:
                        queries.append({
                            'query': ts_match,
                            'operator': '>',
                            'value': 0
                        })
        
        # If no structured queries found, fall back to simple parsing
        if not queries:
            ts_pattern = r'ts\([^)]+\)'
            ts_matches = re.findall(ts_pattern, condition)
            
            if ts_matches:
                # Simple case with one threshold for all
                threshold_pattern = r'([<>]=?|=)\s*([\d.]+)'
                threshold_match = re.search(threshold_pattern, condition)
                
                if threshold_match:
                    operator_map = {
                        '>': 'gt',
                        '>=': 'gte',
                        '<': 'lt',
                        '<=': 'lte',
                        '=': 'eq'
                    }
                    operator = threshold_match.group(1)
                    value = float(threshold_match.group(2))
                    
                    threshold_info = {
                        'operator': operator_map.get(operator, 'gt'),
                        'value': value
                    }
                
                queries = ts_matches
            elif condition.strip():
                queries = [condition.strip()]
        
        return queries, threshold_info
    
    def _map_operator(self, operator: str) -> str:
        """Map comparison operators to Grafana format"""
        operator_map = {
            '>': 'gt',
            '>=': 'gte',
            '<': 'lt',
            '<=': 'lte',
            '=': 'eq',
            '==': 'eq',
            '!=': 'neq'
        }
        return operator_map.get(operator, 'gt')
    
    def _extract_logical_operator(self, condition: str, position: int) -> str:
        """Extract AND/OR operator at given position"""
        import re
        
        # Split by AND/OR
        parts = re.split(r'\s+(AND|OR)\s+', condition, flags=re.IGNORECASE)
        
        # Find the operator at the given position
        operator_count = 0
        for i, part in enumerate(parts):
            if part.upper() in ['AND', 'OR']:
                if operator_count == position - 1:
                    return '&&' if part.upper() == 'AND' else '||'
                operator_count += 1
        
        # Default to AND
        return '&&'
    
    def _determine_reducer_type(self, condition: str) -> str:
        """Determine the appropriate reducer type based on WQL functions"""
        condition_lower = condition.lower()
        
        # Map WQL functions to Grafana reducer types
        if 'avg(' in condition_lower or 'mavg(' in condition_lower:
            return 'mean'
        elif 'sum(' in condition_lower:
            return 'sum'
        elif 'max(' in condition_lower:
            return 'max'
        elif 'min(' in condition_lower:
            return 'min'
        elif 'count(' in condition_lower:
            return 'count'
        elif 'stddev(' in condition_lower:
            return 'stdDev'
        elif 'last(' in condition_lower:
            return 'last'
        elif 'median(' in condition_lower:
            return 'median'
        elif 'first(' in condition_lower:
            return 'first'
        else:
            # Default to 'last' for most recent value
            return 'last'
    
    def _extract_threshold(self, wf_alert: Dict) -> float:
        """Extract threshold value from Wavefront alert condition"""
        # This is kept for backward compatibility but now uses the new parser
        condition = wf_alert.get('condition', '')
        _, threshold_info = self._parse_wavefront_condition(condition)
        return threshold_info.get('value', 0)
    
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
        """Import alert rule to Grafana (legacy method for individual rules)"""
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
    
    def import_alert_group(self, alert_group_json: Dict) -> bool:
        """Import alert rule group to Grafana"""
        try:
            # First, ensure the folder exists
            folder_name = alert_group_json.get('groups', [{}])[0].get('folder', 'Wavefront Migration')
            self.ensure_folder_exists(folder_name)
            
            # Import the alert rule group
            response = requests.post(
                f"{self.url}/api/v1/provisioning/alert-rules",
                headers=self.headers,
                auth=self.auth,
                json=alert_group_json
            )
            response.raise_for_status()
            logger.info(f"Successfully imported alert group with {len(alert_group_json.get('groups', [{}])[0].get('rules', []))} rules")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to import alert group: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            return False
    
    def ensure_folder_exists(self, folder_name: str) -> Optional[str]:
        """Ensure a folder exists in Grafana, create if not"""
        try:
            # Check if folder exists
            response = requests.get(
                f"{self.url}/api/folders",
                headers=self.headers,
                auth=self.auth
            )
            response.raise_for_status()
            
            folders = response.json()
            for folder in folders:
                if folder.get('title') == folder_name:
                    logger.info(f"Folder '{folder_name}' already exists")
                    return folder.get('uid')
            
            # Create folder if it doesn't exist
            folder_data = {
                "title": folder_name,
                "uid": folder_name.lower().replace(' ', '-')
            }
            
            response = requests.post(
                f"{self.url}/api/folders",
                headers=self.headers,
                auth=self.auth,
                json=folder_data
            )
            response.raise_for_status()
            logger.info(f"Created folder: {folder_name}")
            return response.json().get('uid')
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to ensure folder exists: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            return None
    
    def delete_alert(self, alert_uid: str) -> bool:
        """Delete an alert rule from Grafana by its UID"""

        # Read & display the json object before deleting it
        try:
            response = requests.get(
                f"{self.url}/api/v1/provisioning/alert-rules/{alert_uid}",
                headers=self.headers,
                auth=self.auth
            )
            response.raise_for_status()
            logger.info(f"Successfully read alert with UID: {alert_uid}")
            logger.info(f"alert: {response.json()}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to read alert {alert_uid}: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            return False

        # Now delete the alert
        try:
            response = requests.delete(
                f"{self.url}/api/v1/provisioning/alert-rules/{alert_uid}",
                headers=self.headers,
                auth=self.auth
            )
            response.raise_for_status()
            logger.info(f"Successfully deleted alert with UID: {alert_uid}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to delete alert {alert_uid}: {e}")
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
    
    def migrate_alerts(self, alert_ids: Optional[List[str]] = None, group_name: str = "Wavefront Alerts", 
                      folder_name: str = "Wavefront Migration", evaluation_interval: str = "60s"):
        """Migrate alerts from Wavefront to Grafana as an alert rule group"""
        
        # Get alerts to migrate
        alerts = self.extractor.get_alerts()
        if alert_ids:
            alerts = [a for a in alerts if a['id'] in alert_ids]
        
        logger.info(f"Migrating {len(alerts)} alerts...")
        
        if not alerts:
            logger.warning("No alerts to migrate")
            return
        
        # Build individual alert rules
        alert_rules = []
        failed_alerts = []
        
        for wf_alert in alerts:
            try:
                logger.info(f"Processing alert: {wf_alert.get('name', 'Unknown')}")
                
                # Convert to Grafana format
                grafana_alert = self.alert_builder.build_alert(wf_alert)
                
                # Add a unique UID for each alert
                grafana_alert['uid'] = f"wf_{wf_alert.get('id', '')}"[:40]  # Grafana UID limit
                
                alert_rules.append(grafana_alert)
                
            except Exception as e:
                logger.error(f"Error processing alert {wf_alert.get('name')}: {e}")
                failed_alerts.append(wf_alert.get('name', 'Unknown'))
        
        if not alert_rules:
            logger.error("No alerts were successfully converted")
            return
        
        # Create alert rule group structure
        alert_group = {
            "apiVersion": 1,
            "groups": [{
                "orgId": 1,
                "name": group_name,
                "folder": folder_name,
                "interval": evaluation_interval,
                "rules": alert_rules
            }]
        }
        
        # Save complete group to file for review
        group_filename = f"alert_group_{group_name.lower().replace(' ', '_')}.json"
        with open(group_filename, 'w') as f:
            json.dump(alert_group, f, indent=2)
        logger.info(f"Saved alert group JSON to {group_filename}")
        
        # Save individual alert files for review
        for i, rule in enumerate(alert_rules):
            filename = f"alert_{rule.get('uid', i)}.json"
            with open(filename, 'w') as f:
                json.dump(rule, f, indent=2)
        
        # Import the alert group to Grafana
        if self.importer.import_alert_group(alert_group):
            logger.info(f"Successfully imported alert group with {len(alert_rules)} rules")
        else:
            logger.error("Failed to import alert group")
        
        logger.info(f"Migration complete: {len(alert_rules)}/{len(alerts)} alerts successful")
        if failed_alerts:
            logger.warning(f"Failed alerts: {', '.join(failed_alerts)}")
    
    def delete_alert(self, alert_uid: str) -> bool:
        """Delete an alert from Grafana by its UID"""
        return self.importer.delete_alert(alert_uid)
    
    def delete_alerts(self, alert_uids: List[str]) -> Dict[str, bool]:
        """Delete multiple alerts from Grafana by their UIDs
        
        Returns:
            Dict mapping alert UIDs to success status
        """
        results = {}
        for alert_uid in alert_uids:
            logger.info(f"Deleting alert: {alert_uid}")
            results[alert_uid] = self.delete_alert(alert_uid)
        
        success_count = sum(1 for success in results.values() if success)
        logger.info(f"Deletion complete: {success_count}/{len(alert_uids)} alerts successfully deleted")
        
        return results


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
    parser.add_argument('--delete-alerts', nargs='*', help='Alert UIDs to delete from Grafana')
    
    # Alert group configuration options
    parser.add_argument('--alert-group-name', default='Wavefront Alerts', 
                       help='Name for the alert rule group (default: Wavefront Alerts)')
    parser.add_argument('--alert-folder', default='Wavefront Migration', 
                       help='Folder name for alerts in Grafana (default: Wavefront Migration)')
    parser.add_argument('--alert-interval', default='60s', 
                       help='Evaluation interval for alerts (default: 60s)')
    
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
    
    # Handle alert deletion if requested
    if args.delete_alerts:
        logger.info(f"Deleting {len(args.delete_alerts)} alerts...")
        orchestrator.delete_alerts(args.delete_alerts)
        logger.info("Alert deletion process completed!")
        return
    
    if not args.skip_dashboards:
        orchestrator.migrate_dashboards(args.dashboards)
    
    if not args.skip_alerts:
        orchestrator.migrate_alerts(
            alert_ids=args.alerts,
            group_name=args.alert_group_name,
            folder_name=args.alert_folder,
            evaluation_interval=args.alert_interval
        )
    
    logger.info("Migration process completed!")


if __name__ == "__main__":
    main()
