"""Confirms every PitwallMetrics.record_* call carries season/race/session,
including the metrics that don't go through ReplayEngine._attrs() (lag,
events_total, build_info) and were historically easy to miss."""

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from pipeline.metrics import PitwallMetrics

RACE_LABELS = {"season": "2023", "race": "qatar", "session": "R"}


def make_metrics():
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    meter = provider.get_meter("test")
    return PitwallMetrics(meter, RACE_LABELS), reader


def _all_attributes(reader) -> list[dict]:
    data = reader.get_metrics_data()
    attrs = []
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                for point in metric.data.data_points:
                    attrs.append((metric.name, dict(point.attributes)))
    return attrs


def test_lap_time_carries_race_labels():
    metrics, reader = make_metrics()
    metrics.record_lap_time({"driver": "VER"}, 91.0)
    points = _all_attributes(reader)
    lap_time_attrs = next(a for name, a in points if name == "pitwall_lap_time_seconds")
    assert lap_time_attrs["season"] == "2023"
    assert lap_time_attrs["race"] == "qatar"
    assert lap_time_attrs["session"] == "R"


def test_replay_lag_carries_race_labels():
    metrics, reader = make_metrics()
    metrics.record_lag(1.5)
    points = _all_attributes(reader)
    lag_attrs = next(a for name, a in points if name == "pitwall_replay_lag_seconds")
    assert lag_attrs == RACE_LABELS


def test_replay_events_total_carries_race_labels_and_event_kind():
    metrics, reader = make_metrics()
    metrics.record_event_processed("LAP")
    points = _all_attributes(reader)
    events_attrs = next(a for name, a in points if name == "pitwall_replay_events_total")
    assert events_attrs["event_kind"] == "LAP"
    assert events_attrs["season"] == "2023"
    assert events_attrs["race"] == "qatar"
    assert events_attrs["session"] == "R"


def test_build_info_carries_race_labels():
    metrics, reader = make_metrics()
    metrics.set_build_info("0.1.0", 9221, 10)
    points = _all_attributes(reader)
    build_info_attrs = next(a for name, a in points if name == "pitwall_build_info")
    assert build_info_attrs["season"] == "2023"
    assert build_info_attrs["race"] == "qatar"
    assert build_info_attrs["session"] == "R"
    assert build_info_attrs["session_key"] == "9221"


def test_car_position_carries_race_labels():
    metrics, reader = make_metrics()
    metrics.record_car_position({"driver": "VER"}, x=100.0, y=200.0)
    points = _all_attributes(reader)
    x_attrs = next(a for name, a in points if name == "pitwall_car_x")
    assert x_attrs["season"] == "2023"
