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
from pathlib import Path  # <-- added

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
ALERT_IDS_FILE = "alert_ids.json"

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
        logger.info("Fetch all alerts from Wavefront")
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

    def get_alert(self, id: str) -> Dict:
        logger.info(f"Fetch alert {id} from Wavefront")
        try:
            response = requests.get(
                f"{self.url}/api/v2/alert/{id}",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json().get('response', {})
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch alert {id}: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            return {}


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
                # tag_pattern = r'(\w+)="([^"]+)"'
                # tag_matches = re.findall(tag_pattern, tags_str)
                # tags = {k: v for k, v in tag_matches}
                tags = tags_str
            
            # Build PromQL
            # logger.info("tags: %s", tags)
            if tags:
                # tag_str = ', '.join([f'{k}="{v}"' for k, v in tags.items()])
                tag_str = tags_str
                promql = f"{metric}{{{tag_str}}}"
            else:
                promql = metric

            # logger.info("promql: %s", promql)

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
    
    def build_alert(self, wf_alert: Dict, folder_uid: str, rule_group: str) -> Optional[Dict]:
        """
        Convert a Wavefront alert into a single Grafana unified alert rule.

        Requirements mapping:
          - Skip building if wf_alert.status == "SNOOZED" (status may be a string or list).
          - Each element in wf_alert['alertSources'] becomes one Grafana data[] element.
              * Its refId is assigned sequentially starting with 'A'.
              * If its query is a variable reference like ${VarName}, create an expression
                step (datasource __expr__) whose expression is the refId of VarName.
              * Otherwise create a datasource query step (Prometheus expr / Influx query).
          - Each entry in wf_alert['conditions'] (warn, severe, etc.) becomes a Grafana
            data[] element whose model.type == "threshold".
              * Parse pattern: ${VarName} <op> <number>
              * Link threshold step's expression to the referenced VarName refId.
              * Evaluator operator maps to Grafana evaluator type (gt, ge, lt, le, eq, ne).
          - Final rule.condition points to the "most severe" threshold refId:
              * Prefer severe if present, else warn, else last threshold added.
          - Multiple queries & thresholds supported; no additional reduce steps are
            injected per the stated requirement (1:1 mapping).
        """
        # 1. Skip snoozed alerts
        status_val = wf_alert.get('status')
        if (isinstance(status_val, str) and status_val.upper() == "SNOOZED") or \
           (isinstance(status_val, list) and any(s.upper() == "SNOOZED" for s in status_val)):
            logger.info(f"Skipping snoozed alert: {wf_alert.get('uid', 'null')}: {wf_alert.get('name', 'Unnamed')}")
            return None

        alert_sources: List[Dict] = wf_alert.get('alertSources', [])
        conditions_dict: Dict[str, str] = wf_alert.get('conditions', {}) or {}

        if not alert_sources and not conditions_dict:
            return None  # Nothing to build

        # 2. Assign refIds sequentially for queries (alertSources)
        #    Keep name -> refId map (variable & condition sources both have 'name')
        name_ref_map: Dict[str, str] = {}
        data: List[Dict] = []
        next_ref_ord = ord('A')

        def next_ref_id() -> str:
            nonlocal next_ref_ord
            ref_id = chr(next_ref_ord)
            next_ref_ord += 1
            return ref_id

        # Build a preliminary name->query map for variable substitution
        var_query_map: Dict[str, str] = {}
        for src in alert_sources:
            name = src.get('name')
            query = src.get('query', '')
            if name and query:
                var_query_map[name] = query

        # Helper: expand ${Var} inside query strings (single pass; nested uncommon)
        import re
        var_pattern = re.compile(r'\$\{([^}]+)\}')

        def expand_variables(q: str) -> str:
            def repl(m):
                key = m.group(1)
                return var_query_map.get(key, m.group(0))
            return var_pattern.sub(repl, q)

        # 3. Create data steps for each alertSource
        for src in alert_sources:
            name = src.get('name')
            raw_query = src.get('query', '') or ''
            ref_id = next_ref_id()
            if name:
                name_ref_map[name] = ref_id

            # Variable reference pattern: entire query exactly "${VarName}"
            m_var_only = re.fullmatch(r'\$\{([^}]+)\}', raw_query.strip())
            if m_var_only:
                referenced = m_var_only.group(1)
                referenced_ref = name_ref_map.get(referenced)
                # If referenced ref not yet defined, fall back to expression "0"
                expression = referenced_ref if referenced_ref else "0"
                data.append({
                    "refId": ref_id,
                    "relativeTimeRange": {"from": 600, "to": 0},
                    "datasourceUid": "__expr__",
                    "model": {
                        "datasource": {"type": "__expr__", "uid": "__expr__"},
                        "expression": f"${{{expression}}}",
                        "type": "math",      # simple expression pass-through
                        "refId": ref_id
                    }
                })
                continue

            # Otherwise treat as real source query
            expanded_query = expand_variables(raw_query)
            # logger.info("Expanded query: %s", expanded_query)

            translated = QueryTranslator.translate(expanded_query, self.datasource_type)
            # logger.info("Translated query: %s", translated)

            model = {
                "datasource": {
                    "type": self.datasource_type.value,
                    "uid": self.datasource_uid
                },
                "expr": translated if self.datasource_type == DataSourceType.PROMETHEUS else "",
                "query": translated if self.datasource_type == DataSourceType.INFLUXDB else "",
                "instant": True,
                "intervalMs": 1000,
                "maxDataPoints": 43200,
                "refId": ref_id
            }
            data.append({
                "refId": ref_id,
                "relativeTimeRange": {"from": 600, "to": 0},
                "datasourceUid": self.datasource_uid,
                "model": model
            })

        last_non_threshold_ref_id = ref_id

        # 4. Threshold steps from conditions
        # Maintain ordering but capture severe/warn refIds for final condition preference
        threshold_ref_ids: Dict[str, str] = {}
        operator_regex = re.compile(r'^\s*\$\{([^}]+)\}\s*([<>]=?|==|!=)\s*([-+]?\d+(?:\.\d+)?)\s*$')

        for level, expr in conditions_dict.items():
            ref_id = next_ref_id()
            var_name = None
            op = None
            value = None

            m = operator_regex.match(expr)
            if m:
                var_name, op, value = m.group(1), m.group(2), float(m.group(3))
            else:
                # Attempt partial parse (fallback)
                m2 = re.search(r'\$\{([^}]+)\}', expr)
                if m2:
                    var_name = m2.group(1)
                # operator/value fallback
                m3 = re.search(r'([<>]=?|==|!=)\s*([-+]?\d+(?:\.\d+)?)', expr)
                if m3:
                    op = m3.group(1)
                    value = float(m3.group(2))
            if not op:
                op = '>'  # default
            if value is None:
                value = 0.0

            mapped_op = self._map_operator(op)
            referenced_ref = name_ref_map.get(var_name) if var_name else None
            if not referenced_ref and data:
                # fallback to first query step
                # referenced_ref = data[0]['refId']
                # Use the last non-threshold ref_id
                referenced_ref = last_non_threshold_ref_id if data else "A"

            data.append({
                "refId": ref_id,
                "relativeTimeRange": {"from": 600, "to": 0},
                "datasourceUid": "__expr__",
                "model": {
                    "conditions": [{
                        "evaluator": {
                            "params": [value],
                            "type": mapped_op
                        },
                        "operator": {"type": "and"},
                        "query": {"params": [ref_id]},
                        "reducer": {"params": [], "type": "last"},
                        "type": "query"
                    }],
                    "datasource": {"type": "__expr__", "uid": "__expr__"},
                    "expression": referenced_ref or "0",
                    "type": "threshold",
                    "refId": ref_id
                }
            })
            threshold_ref_ids[level] = ref_id

        # 5. Determine final condition refId
        if threshold_ref_ids:
            if 'severe' in threshold_ref_ids:
                final_condition = threshold_ref_ids['severe']
            elif 'warn' in threshold_ref_ids:
                final_condition = threshold_ref_ids['warn']
            else:
                # any threshold
                final_condition = list(threshold_ref_ids.values())[-1]
        else:
            # No thresholds; choose last query step
            final_condition = data[-1]['refId'] if data else "A"

        # 6. Assemble rule
        alert_rule = {
            "uid": f"wf_{wf_alert.get('id', '')}"[:40],
            "title": wf_alert.get('name', 'Migrated Alert'),
            "condition": final_condition,
            "data": data,
            "ruleGroup": rule_group,
            "folderUID": folder_uid,
            "orgID": 1,
            "noDataState": "NoData",
            "execErrState": "Error",
            "for": self._convert_duration(wf_alert.get('minutes', 5)),
            "annotations": {
                "description": wf_alert.get('additionalInformation', ''),
                "summary": wf_alert.get('name', ''),
                "wavefront_original_conditions": json.dumps(conditions_dict)
            },
            "labels": {
                "wavefront_severity": wf_alert.get('severity', 'UNKNOWN')
            },
            "isPaused": False
        }

        # Add tags
        for tag in wf_alert.get('tags', {}).get('customerTags', []):
            alert_rule['labels'][f"tag_{tag}"] = tag

        return alert_rule
    
    def _parse_wavefront_condition(self, condition: str) -> tuple:
        """Parse Wavefront condition to extract queries and threshold info"""
        import re
        
        queries = []
        threshold_info = {'operator': 'gt', 'value': 0}
        
        # Handle complex conditions with AND/OR
        # Split by AND/OR while preserving the operators
        parts = re.split(r'\s+(AND|OR)\s+', condition, flags=re.IGNORECASE)
        # logger.info("parts: %s", parts)
        
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

                # Strip out operators and everything after it to give a clean query
                condition = condition.split('>')[0]
                condition = condition.split('<')[0]
                condition = condition.split('=')[0]
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
                'Content-Type': 'application/json',
                'X-Disable-Provenance': 'true'
            }
        elif username and password:
            # Basic authentication
            self.headers = {
                'Content-Type': 'application/json',
                'X-Disable-Provenance': 'true'
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
    
    
    def import_alert_rule(self, alert_rule: Dict) -> bool:
        """Import a single alert rule to Grafana"""
        try:
            # Display the alert before posting
            # logger.info(f"self.headers: {json.dumps(self.headers, indent=2)}")
            # logger.info("Alert to be posted:")
            # logger.info(json.dumps(alert_rule, indent=2))

            # Import the alert rule
            response = requests.post(
                f"{self.url}/api/v1/provisioning/alert-rules",
                headers=self.headers,
                auth=self.auth,
                json=alert_rule
            )
            response.raise_for_status()
            logger.info(f"Successfully imported alert: {alert_rule.get('title')}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to import alert: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            return False
    
    def get_or_create_folder(self, folder_name: str) -> Optional[str]:
        """Get folder UID, create folder if it doesn't exist"""
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
                    logger.info(f"Folder '{folder_name}' exists with UID: {folder.get('uid')}")
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
            folder_uid = response.json().get('uid')
            logger.info(f"Created folder '{folder_name}' with UID: {folder_uid}")
            return folder_uid
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get/create folder: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            return None


class MigrationOrchestrator:
    """Orchestrate the complete migration process"""
    
    def __init__(self, config: MigrationConfig, alert_ids_file: str = ALERT_IDS_FILE):
        self.config = config
        self.alert_ids_file = alert_ids_file
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
        """Migrate alerts from Wavefront to Grafana"""
        
        # Get alerts to migrate
        if alert_ids:
            alerts = []
            # Fetch each alert by ID
            logger.info(f"Fetching specific alerts from Wavefront")
            for alert_id in alert_ids:
                alert = self.extractor.get_alert(alert_id)
                if alert:
                    alerts.append(alert)
            # alerts = [a for a in alerts if a['id'] in alert_ids]
        else:
            alerts = self.extractor.get_alerts()

        logger.info(f"Migrating {len(alerts)} alerts...")
        
        if not alerts:
            logger.warning("No alerts to migrate")
            return
        
        # Get or create folder and get its UID
        folder_uid = self.importer.get_or_create_folder(folder_name)
        if not folder_uid:
            logger.error(f"Failed to get/create folder '{folder_name}'")
            return
        
        logger.info(f"Using folder '{folder_name}' with UID: {folder_uid}")
        
        # Process each alert individually
        success_count = 0
        failed_alerts = []
        
        for wf_alert in alerts:
            try:
                logger.info(f"Processing alert: {wf_alert.get('name', 'Unknown')}")
                
                # Convert to Grafana format with folder and group info
                grafana_alert = self.alert_builder.build_alert(
                    wf_alert, 
                    folder_uid=folder_uid,
                    rule_group=group_name
                )

                # Skip alert if not valid
                if not grafana_alert:
                    continue

                # Save individual alert file for review
                filename = f"alert_{grafana_alert.get('uid', 'unknown')}.json"
                with open(filename, 'w') as f:
                    json.dump(grafana_alert, f, indent=2)
                logger.info(f"Saved alert JSON to {filename}")
                
                # Import the alert to Grafana
                if self.importer.import_alert_rule(grafana_alert):
                    success_count += 1
                    # Record the successfully created alert UID
                    if grafana_alert.get("uid"):
                        self._append_alert_uid(grafana_alert["uid"])  # <-- added
                else:
                    failed_alerts.append(wf_alert.get('name', 'Unknown'))
                
            except Exception as e:
                logger.error(f"Error processing alert {wf_alert.get('name')}: {e}")
                failed_alerts.append(wf_alert.get('name', 'Unknown'))
        
        logger.info(f"Migration complete: {success_count}/{len(alerts)} alerts successful")
        if failed_alerts:
            logger.warning(f"Failed alerts: {', '.join(failed_alerts)}")
    
    def _append_alert_uid(self, uid: str):  # <-- added helper
        """Append a created Grafana alert UID to the tracking JSON file."""
        try:
            path = Path(self.alert_ids_file)
            if not path.exists():
                path.write_text("[]")
            try:
                data = json.loads(path.read_text() or "[]")
                if not isinstance(data, list):
                    data = []
            except Exception:
                data = []
            data.append(uid)
            path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.warning(f"Failed to record alert UID {uid} to {self.alert_ids_file}: {e}")


def main():
    parser = argparse.ArgumentParser(description='Migrate Wavefront dashboards and alerts to Grafana')
    
    parser.add_argument('--grafana-url', required=True, help='Grafana API URL')
    # Grafana authentication - either token OR username/password
    auth_group = parser.add_mutually_exclusive_group(required=True)
    auth_group.add_argument('--grafana-token', help='Grafana API token')
    auth_group.add_argument('--grafana-credentials', nargs=2, metavar=('USERNAME', 'PASSWORD'), 
                           help='Grafana username and password')
    
    # Migration-specific arguments (not required for deletion)
    parser.add_argument('--wavefront-url', help='Wavefront API URL')
    parser.add_argument('--wavefront-token', help='Wavefront API token')
    parser.add_argument('--datasource-type', 
                       choices=['prometheus', 'influxdb', 'elasticsearch', 'cloudwatch'],
                       help='Target datasource type in Grafana')
    parser.add_argument('--datasource-uid', help='Grafana datasource UID')
    parser.add_argument('--dashboards', nargs='*', help='Specific dashboard IDs to migrate')
    parser.add_argument('--alerts', nargs='*', help='Specific alert IDs to migrate')
    parser.add_argument('--skip-dashboards', action='store_true', help='Skip dashboard migration')
    parser.add_argument('--skip-alerts', action='store_true', help='Skip alert migration')
    
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
    
    if not args.wavefront_url or not args.wavefront_token:
        parser.error("Migration requires --wavefront-url and --wavefront-token")
    if not args.datasource_type or not args.datasource_uid:
        parser.error("Migration requires --datasource-type and --datasource-uid")
    
    logger.info("Migration Process Started")

    # Create configuration for migration
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
    
    if not args.skip_alerts:
        try:
            path = Path(ALERT_IDS_FILE)
            if path.exists():
                path.unlink()
            path.write_text("[]")
            logger.info(f"Initialized alert ID tracking file: {ALERT_IDS_FILE}")
        except Exception as e:
            logger.warning(f"Could not initialize {ALERT_IDS_FILE}: {e}")
    
    # Run migration
    orchestrator = MigrationOrchestrator(config, alert_ids_file=ALERT_IDS_FILE)  # <-- pass file
    
    if not args.skip_dashboards:
        orchestrator.migrate_dashboards(args.dashboards)
    
    if not args.skip_alerts:
        orchestrator.migrate_alerts(
            alert_ids=args.alerts,
            group_name=args.alert_group_name,
            folder_name=args.alert_folder,
            evaluation_interval=args.alert_interval
        )
    
    logger.info("Migration Process Completed!")


if __name__ == "__main__":
    main()
