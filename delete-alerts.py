#!/usr/bin/env python3
"""
Grafana Alert Deletion Utility
Delete Grafana unified alert rules by UID(s) or from a JSON file containing an array of UIDs.
"""
import argparse
import json
import logging
from typing import List, Dict, Optional

import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class GrafanaClient:
    """Minimal Grafana client focused on alert rule deletion."""

    def __init__(self, base_url: str, token: Optional[str] = None,
                 username: Optional[str] = None, password: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.auth = None
        if token:
            self.headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        elif username and password:
            self.headers = {"Content-Type": "application/json"}
            self.auth = (username, password)
        else:
            raise ValueError("Provide either --grafana-token or --grafana-credentials")

    def get_alert(self, uid: str) -> Optional[Dict]:
        try:
            r = requests.get(
                f"{self.base_url}/api/v1/provisioning/alert-rules/{uid}",
                headers=self.headers,
                auth=self.auth,
                timeout=15
            )
            if r.status_code == 404:
                logger.warning(f"Alert UID ({uid}) not found!")
                return None
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            logger.error(f"Error retrieving alert {uid}: {e}")
            return None

    def delete_alert(self, uid: str) -> bool:
        try:
            if not self.get_alert(uid):  # Ensure alert exists before deleting
                return False

            r = requests.delete(
                f"{self.base_url}/api/v1/provisioning/alert-rules/{uid}",
                headers=self.headers,
                auth=self.auth,
                timeout=15
            )
            # logger.info(f"Response: {r}")
            if r.status_code in (200, 202, 204):
                logger.info(f"Deleted alert UID={uid}")
                return True
            if r.status_code == 404:
                logger.warning(f"Alert UID not found (delete): {uid}")
                return False
            logger.error(f"Failed deleting {uid}: {r.status_code} {r.text}")
            return False
        except requests.RequestException as e:
            logger.error(f"Request error deleting {uid}: {e}")
            return False


def delete_alerts(client: GrafanaClient, uids: List[str]) -> Dict[str, bool]:
    results: Dict[str, bool] = {}
    for uid in uids:
        logger.info(f"Processing deletion for UID: {uid}")
        results[uid] = client.delete_alert(uid)
    total = len(results)
    success = sum(1 for v in results.values() if v)
    logger.info(f"Summary: {success}/{total} alerts deleted successfully")
    return results


def delete_alerts_from_file(client: GrafanaClient, path: str) -> Dict[str, bool]:
    try:
        with open(path, "r") as f:
            payload = json.load(f)
    except Exception as e:
        logger.error(f"Failed reading file {path}: {e}")
        return {}
    if not isinstance(payload, list):
        logger.error("JSON file must be an array of UIDs or objects with 'uid'")
        return {}
    uids: List[str] = []
    for item in payload:
        if isinstance(item, str):
            uids.append(item)
        elif isinstance(item, dict) and isinstance(item.get("uid"), str):
            uids.append(item["uid"])
    if not uids:
        logger.warning("No valid alert UIDs found in file")
        return {}
    logger.info(f"Deleting {len(uids)} alerts from file {path}")
    return delete_alerts(client, uids)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Delete Grafana unified alert rules by UID.")
    p.add_argument("--grafana-url", required=True, help="Grafana base URL, e.g. http://localhost:3000")
    auth = p.add_mutually_exclusive_group(required=True)
    auth.add_argument("--grafana-token", help="Grafana API token")
    auth.add_argument("--grafana-credentials", nargs=2, metavar=("USERNAME", "PASSWORD"),
                      help="Grafana username and password")
    p.add_argument("--delete-alerts", nargs="*", help="List of alert UIDs to delete")
    p.add_argument("--delete-alerts-file", help="Path to JSON file with array of alert UIDs")
    return p


def main():
    args = build_arg_parser().parse_args()

    if not args.delete_alerts and not args.delete_alerts_file:
        logger.error("Provide --delete-alerts or --delete-alerts-file")
        return

    logger.info("Alert Deletions Started")

    if args.grafana_token:
        client = GrafanaClient(args.grafana_url, token=args.grafana_token)
    else:
        user, pwd = args.grafana_credentials
        client = GrafanaClient(args.grafana_url, username=user, password=pwd)

    if args.delete_alerts_file:
        delete_alerts_from_file(client, args.delete_alerts_file)

    if args.delete_alerts:
        delete_alerts(client, args.delete_alerts)

    logger.info("Alert Deletions Completed!")

if __name__ == "__main__":
    main()
