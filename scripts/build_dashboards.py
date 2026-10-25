#!/usr/bin/env python3
"""Injects dashboards/<name>/panels/*.js into dashboards/<name>/dashboard.json's
__PANEL_JS__:<panel-key> placeholders and writes terraform/grafana/build/<name>.json
for Terraform to read.

The output lives inside terraform/grafana/ (not the repo root) because HCP
Terraform's remote execution only uploads the Terraform config directory
itself as "configuration source" -- a file:() reference to anything outside
it (e.g. a repo-root build/) fails with "no file exists" on remote runs,
even though it works fine locally.

Usage: python3 scripts/build_dashboards.py [--out-dir DIR]
"""

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARDS_DIR = REPO_ROOT / "dashboards"
DEFAULT_BUILD_DIR = REPO_ROOT / "terraform" / "grafana" / "build"

PLACEHOLDER_RE = re.compile(r"^__PANEL_JS__:(.+)$")

# Each panel-N.js starts with a "// Panel: <title> (<key>)" comment line,
# which documents the file for humans but isn't part of the getOption body.
LEADING_COMMENT_RE = re.compile(r"^//.*\n")


def load_panel_js(panels_dir: Path, panel_key: str) -> str:
    path = panels_dir / f"{panel_key}.js"
    if not path.exists():
        raise SystemExit(f"Missing panel JS file: {path}")
    text = path.read_text()
    return LEADING_COMMENT_RE.sub("", text, count=1).strip()


def inject_panel_js(node, panels_dir: Path) -> None:
    """Walks the dashboard JSON, replacing every __PANEL_JS__:<key> string
    with the matching panels/<key>.js file's contents."""
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str):
                match = PLACEHOLDER_RE.match(value)
                if match:
                    node[key] = load_panel_js(panels_dir, match.group(1))
            else:
                inject_panel_js(value, panels_dir)
    elif isinstance(node, list):
        for item in node:
            inject_panel_js(item, panels_dir)


def build_dashboard(dashboard_dir: Path) -> dict:
    dashboard = json.loads((dashboard_dir / "dashboard.json").read_text())
    inject_panel_js(dashboard, dashboard_dir / "panels")
    return dashboard


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_BUILD_DIR,
        help=f"Where to write built dashboard JSON (default: {DEFAULT_BUILD_DIR})",
    )
    args = parser.parse_args()

    if not DASHBOARDS_DIR.exists():
        sys.exit(f"No dashboards/ directory at {DASHBOARDS_DIR}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    built = []
    for dashboard_dir in sorted(DASHBOARDS_DIR.iterdir()):
        if not dashboard_dir.is_dir() or not (dashboard_dir / "dashboard.json").exists():
            continue
        dashboard = build_dashboard(dashboard_dir)
        out_path = args.out_dir / f"{dashboard_dir.name}.json"
        out_path.write_text(json.dumps(dashboard, indent=2, sort_keys=True))
        built.append(out_path)
        print(f"[built] {dashboard_dir.name} -> {out_path}")

    if not built:
        sys.exit("No dashboard.json files found under dashboards/*/")


if __name__ == "__main__":
    main()
