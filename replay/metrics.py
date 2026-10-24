"""OpenTelemetry instrument definitions and the meter provider wired to Alloy."""

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import Meter, MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource

# F1-realistic lap time buckets (seconds); OTel's default buckets are tuned for
# sub-second latencies and would bucket every lap time into one bin.
LAP_TIME_BUCKETS = [70, 75, 80, 85, 90, 95, 100, 110, 120, 140, 180]


def build_meter_provider(
    otlp_endpoint: str,
    export_interval_seconds: float,
    session_key: int,
) -> MeterProvider:
    resource = Resource.create(
        {
            "service.name": "pitwall-replay",
            "pitwall.session_key": session_key,
        }
    )
    exporter = OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True)
    reader = PeriodicExportingMetricReader(
        exporter, export_interval_millis=export_interval_seconds * 1000
    )
    lap_time_view = View(
        instrument_name="pitwall_lap_time_distribution_seconds",
        aggregation=ExplicitBucketHistogramAggregation(LAP_TIME_BUCKETS),
    )
    return MeterProvider(resource=resource, metric_readers=[reader], views=[lap_time_view])


class PitwallMetrics:
    def __init__(self, meter: Meter) -> None:
        self._lap_time = meter.create_gauge(
            "pitwall_lap_time_seconds", unit="s", description="Last completed lap time"
        )
        self._sector_time = meter.create_gauge(
            "pitwall_sector_time_seconds", unit="s", description="Last completed sector time"
        )
        self._lap_time_distribution = meter.create_histogram(
            "pitwall_lap_time_distribution_seconds", unit="s", description="Lap time distribution"
        )
        self._position = meter.create_gauge(
            "pitwall_position", description="Current race position"
        )
        self._gap_to_leader = meter.create_gauge(
            "pitwall_gap_to_leader_seconds", unit="s", description="Gap to race leader"
        )
        self._interval = meter.create_gauge(
            "pitwall_interval_seconds", unit="s", description="Interval to car ahead"
        )
        self._tyre_age = meter.create_gauge(
            "pitwall_tyre_age_laps", description="Tyre age in laps for the current stint"
        )
        self._pit_stops = meter.create_counter(
            "pitwall_pit_stops_total", description="Pit stops completed"
        )
        self._pit_duration = meter.create_gauge(
            "pitwall_pit_duration_seconds", unit="s", description="Last pit stop duration"
        )
        self._car_speed = meter.create_gauge(
            "pitwall_car_speed_kph", unit="km/h", description="Car speed"
        )
        self._car_throttle = meter.create_gauge(
            "pitwall_car_throttle_pct", unit="%", description="Throttle position"
        )
        self._car_brake = meter.create_gauge(
            "pitwall_car_brake_pct", unit="%", description="Brake position"
        )
        self._car_gear = meter.create_gauge("pitwall_car_gear", description="Current gear")

        self._replay_events_total = meter.create_counter(
            "pitwall_replay_events_total", description="Replay events processed, by kind"
        )
        self._replay_lag = meter.create_gauge(
            "pitwall_replay_lag_seconds",
            unit="s",
            description="How far behind schedule the replay is",
        )
        self._build_info = meter.create_gauge(
            "pitwall_build_info", description="Replay build/run info, value is always 1"
        )

    def record_lap_time(self, attrs: dict, lap_time_s: float) -> None:
        self._lap_time.set(lap_time_s, attrs)
        self._lap_time_distribution.record(lap_time_s, attrs)

    def record_sector_time(self, attrs: dict, sector: int, duration_s: float) -> None:
        self._sector_time.set(duration_s, {**attrs, "sector": str(sector)})

    def record_position(self, attrs: dict, position: int) -> None:
        self._position.set(position, attrs)

    def record_gap_to_leader(self, attrs: dict, gap_s: float) -> None:
        self._gap_to_leader.set(gap_s, attrs)

    def record_interval(self, attrs: dict, interval_s: float) -> None:
        self._interval.set(interval_s, attrs)

    def record_tyre_age(self, attrs: dict, compound: str, age_laps: int) -> None:
        self._tyre_age.set(age_laps, {**attrs, "compound": compound})

    def record_pit_stop(self, attrs: dict) -> None:
        self._pit_stops.add(1, attrs)

    def record_pit_duration(self, attrs: dict, duration_s: float) -> None:
        self._pit_duration.set(duration_s, attrs)

    def record_car_telemetry(
        self, attrs: dict, speed: float | None, throttle: float | None,
        brake: float | None, n_gear: int | None,
    ) -> None:
        if speed is not None:
            self._car_speed.set(speed, attrs)
        if throttle is not None:
            self._car_throttle.set(throttle, attrs)
        if brake is not None:
            self._car_brake.set(brake, attrs)
        if n_gear is not None:
            self._car_gear.set(n_gear, attrs)

    def record_event_processed(self, kind: str) -> None:
        self._replay_events_total.add(1, {"event_kind": kind})

    def record_lag(self, lag_seconds: float) -> None:
        self._replay_lag.set(lag_seconds)

    def set_build_info(self, version: str, session_key: int, speed: int) -> None:
        self._build_info.set(
            1, {"version": version, "session_key": str(session_key), "speed": str(speed)}
        )


def create_metrics(provider: MeterProvider) -> PitwallMetrics:
    metrics.set_meter_provider(provider)
    meter = provider.get_meter("pitwall.replay")
    return PitwallMetrics(meter)
