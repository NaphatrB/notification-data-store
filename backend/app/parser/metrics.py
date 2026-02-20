"""Prometheus metrics for the parser service."""

import logging
import threading

from prometheus_client import Counter, Gauge, Histogram, start_http_server

logger = logging.getLogger(__name__)

METRICS_PORT = 9090

# Counters
processed_total = Counter(
    "parser_processed_total",
    "Total number of events processed by the parser",
)

failed_total = Counter(
    "parser_failed_total",
    "Total number of events that failed parsing (LLM or validation error)",
)

dead_letter_total = Counter(
    "parser_dead_letter_total",
    "Total number of events sent to dead-letter table",
)

# Histogram
batch_latency = Histogram(
    "parser_batch_latency_seconds",
    "Time taken to process a batch of events",
    buckets=[0.5, 1, 2, 5, 10, 30, 60, 120, 300],
)

# Gauge
oldest_unprocessed = Gauge(
    "parser_oldest_unprocessed_seconds",
    "Age in seconds of the oldest unprocessed event",
)


def start_metrics_server() -> None:
    """Start Prometheus metrics HTTP server on a background thread."""
    try:
        start_http_server(METRICS_PORT)
        logger.info("Prometheus metrics server started on port %d", METRICS_PORT)
    except OSError as e:
        logger.error("Failed to start metrics server: %s", e)
