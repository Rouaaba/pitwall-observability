#!/usr/bin/env python3
"""Pulls a dashboard from Grafana by UID, splits Business Charts getOption
scripts back into panels/*.js, and writes a normalized dashboard.json (no
server-managed runtime metadata, stable key order) so UI edits become clean
diffs.

This is the other half of build_dashboards.py: edit live in the Grafana UI,
run this script to pull the change back into git, review the diff, PR it.

Usage:
    GRAFANA_URL=https://rouaabenayed.grafana.net GRAFANA_AUTH=<token> \\
        python3 scripts/export_dashboards.py --uid roscr2t --name race-centre
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARDS_DIR = REPO_ROOT / "dashboards"

# Only these metadata fields are kept; everything else (resourceVersion,
# generation, creationTimestamp, labels, annotations) is server-managed
# runtime state that would cause spurious diffs on every export.
STABLE_METADATA_FIELDS = {"name", "namespace", "folder"}


def fetch_dashboard(grafana_url: str, auth_token: str, uid: str, namespace: str) -> dict:
    # The classic /api/dashboards/uid/<uid> endpoint translates v2-storage
    # dashboards DOWN to legacy classic JSON (schemaVersion/panels/
    # templating) for backward compatibility -- it does NOT return the real
    # v2 spec.elements/layout/variables shape. The App Platform API is the
    # only way to get the actual v2 resource back.
    resp = requests.get(
        f"{grafana_url}/apis/dashboard.grafana.app/v2/namespaces/{namespace}/dashboards/{uid}",
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def split_panels(dashboard_spec: dict, panels_dir: Path) -> None:
    panels_dir.mkdir(parents=True, exist_ok=True)
    elements = dashboard_spec.get("elements", {})
    for panel_key, element in elements.items():
        panel_spec = element.get("spec", {})
        title = panel_spec.get("title", "")
        options = (
            panel_spec.get("vizConfig", {}).get("spec", {}).get("options", {})
        )
        get_option = options.get("getOption")
        if not isinstance(get_option, str):
            continue
        js_path = panels_dir / f"{panel_key}.js"
        js_path.write_text(f"// Panel: {title} ({panel_key})\n{get_option}\n")
        options["getOption"] = f"__PANEL_JS__:{panel_key}"


def normalize_metadata(metadata: dict) -> dict:
    return {k: v for k, v in metadata.items() if k in STABLE_METADATA_FIELDS}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--uid", required=True, help="Dashboard UID")
    parser.add_argument(
        "--name", required=True, help="dashboards/<name>/ directory to write into"
    )
    parser.add_argument(
        "--grafana-url", default=os.environ.get("GRAFANA_URL"), required=False
    )
    parser.add_argument(
        "--grafana-auth", default=os.environ.get("GRAFANA_AUTH"), required=False
    )
    parser.add_argument(
        "--namespace",
        default=os.environ.get("GRAFANA_NAMESPACE", "stacks-1398043"),
        help="Grafana Cloud stack namespace, e.g. stacks-<instance_id>",
    )
    args = parser.parse_args()

    if not args.grafana_url or not args.grafana_auth:
        sys.exit("Set --grafana-url/--grafana-auth or GRAFANA_URL/GRAFANA_AUTH env vars")

    resource = fetch_dashboard(args.grafana_url, args.grafana_auth, args.uid, args.namespace)

    dashboard_dir = DASHBOARDS_DIR / args.name
    panels_dir = dashboard_dir / "panels"

    spec = resource.get("spec", resource)
    split_panels(spec, panels_dir)

    normalized = {
        "apiVersion": resource.get("apiVersion", "dashboard.grafana.app/v2"),
        "kind": resource.get("kind", "Dashboard"),
        "metadata": normalize_metadata(resource.get("metadata", {"name": args.uid})),
        "spec": spec,
    }

    dashboard_dir.mkdir(parents=True, exist_ok=True)
    (dashboard_dir / "dashboard.json").write_text(
        json.dumps(normalized, indent=2, sort_keys=True) + "\n"
    )
    print(f"[exported] {args.uid} -> {dashboard_dir}/dashboard.json + panels/*.js")


if __name__ == "__main__":
    main()
