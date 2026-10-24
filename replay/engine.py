"""Runs the clock loop: paces the event stream and dispatches each event to a metric."""

import logging
import time
from collections.abc import Iterator

from .clock import ReplayClock
from .events import Event, EventKind
from .metrics import PitwallMetrics

logger = logging.getLogger(__name__)

MAX_SLEEP_CHUNK_SECONDS = 0.5

# OpenF1's car_data sector flags: 0/None absent, else duration lives under this key per sector.
SECTOR_FIELDS = {
    1: "duration_sector_1",
    2: "duration_sector_2",
    3: "duration_sector_3",
}


class ReplayEngine:
    def __init__(
        self,
        clock: ReplayClock,
        metrics: PitwallMetrics,
        driver_labels: dict[int, dict[str, str]],
    ) -> None:
        self.clock = clock
        self.metrics = metrics
        self.driver_labels = driver_labels

    def _attrs(self, driver_number: int | None) -> dict:
        if driver_number is None:
            return {}
        fallback = {"driver": str(driver_number), "team": "unknown"}
        return self.driver_labels.get(driver_number, fallback)

    def run(self, event_stream: Iterator[Event]) -> None:
        for event in event_stream:
            self._wait_until(event.event_time)
            self._dispatch(event)
            self.metrics.record_event_processed(event.kind.name)
            lag = (self.clock.scheduled_race_time() - event.event_time).total_seconds()
            self.metrics.record_lag(max(lag, 0.0))

    def _wait_until(self, target_race_time) -> None:
        while True:
            remaining = self.clock.seconds_until(target_race_time)
            if remaining <= 0:
                return
            time.sleep(min(remaining, MAX_SLEEP_CHUNK_SECONDS))

    def _dispatch(self, event: Event) -> None:
        attrs = self._attrs(event.driver_number)
        payload = event.payload

        if event.kind is EventKind.LAP:
            self._dispatch_lap(attrs, payload)
        elif event.kind is EventKind.STINT_START:
            self._dispatch_stint(attrs, payload)
        elif event.kind is EventKind.PIT:
            self._dispatch_pit(attrs, payload)
        elif event.kind is EventKind.INTERVAL:
            self._dispatch_interval(attrs, payload)
        elif event.kind is EventKind.POSITION:
            self._dispatch_position(attrs, payload)
        elif event.kind is EventKind.CAR_DATA:
            self._dispatch_car_data(attrs, payload)
        elif event.kind in (EventKind.LOCATION, EventKind.RACE_CONTROL):
            pass  # loaded for stream realism/self-observability only, no metric defined yet

    def _dispatch_lap(self, attrs: dict, payload: dict) -> None:
        lap_duration = payload.get("lap_duration")
        if lap_duration is not None:
            self.metrics.record_lap_time(attrs, lap_duration)
        for sector, field in SECTOR_FIELDS.items():
            duration = payload.get(field)
            if duration is not None:
                self.metrics.record_sector_time(attrs, sector, duration)

    def _dispatch_stint(self, attrs: dict, payload: dict) -> None:
        compound = payload.get("compound", "UNKNOWN")
        age = payload.get("tyre_age_at_start")
        if age is not None:
            self.metrics.record_tyre_age(attrs, compound, age)

    def _dispatch_pit(self, attrs: dict, payload: dict) -> None:
        self.metrics.record_pit_stop(attrs)
        duration = payload.get("pit_duration")
        if duration is not None:
            self.metrics.record_pit_duration(attrs, duration)

    def _dispatch_interval(self, attrs: dict, payload: dict) -> None:
        # Lapped cars report strings like "+1 LAP" instead of a numeric gap.
        gap_to_leader = payload.get("gap_to_leader")
        if isinstance(gap_to_leader, (int, float)):
            self.metrics.record_gap_to_leader(attrs, gap_to_leader)
        interval = payload.get("interval")
        if isinstance(interval, (int, float)):
            self.metrics.record_interval(attrs, interval)

    def _dispatch_position(self, attrs: dict, payload: dict) -> None:
        position = payload.get("position")
        if position is not None:
            self.metrics.record_position(attrs, position)

    def _dispatch_car_data(self, attrs: dict, payload: dict) -> None:
        self.metrics.record_car_telemetry(
            attrs,
            speed=payload.get("speed"),
            throttle=payload.get("throttle"),
            brake=payload.get("brake"),
            n_gear=payload.get("n_gear"),
        )
