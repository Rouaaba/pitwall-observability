"""Maps driver_number to low-cardinality OTel attributes (driver acronym + team name)."""

import json
from pathlib import Path


def load_driver_labels(session_dir: Path) -> dict[int, dict[str, str]]:
    drivers = json.loads((session_dir / "drivers.json").read_text())
    return {
        driver["driver_number"]: {
            "driver": driver["name_acronym"],
            "team": driver["team_name"],
        }
        for driver in drivers
    }
