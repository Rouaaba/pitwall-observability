"""Sends one test metric through local Alloy to confirm the OTLP pipeline reaches Grafana Cloud."""

import time

from dotenv import load_dotenv
from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

load_dotenv()

resource = Resource.create({"service.name": "pitwall-setup-check"})
exporter = OTLPMetricExporter(endpoint="localhost:4317", insecure=True)
reader = PeriodicExportingMetricReader(exporter, export_interval_millis=2000)
provider = MeterProvider(resource=resource, metric_readers=[reader])
metrics.set_meter_provider(provider)

meter = metrics.get_meter("pitwall.setup")
counter = meter.create_counter("pitwall_setup_check_total")

counter.add(1, {"stage": "phase0"})
print("Sent test metric pitwall_setup_check_total. Waiting for export...")
time.sleep(5)
provider.shutdown()
print("Done. Check Grafana Cloud Explore for 'pitwall_setup_check_total'.")
