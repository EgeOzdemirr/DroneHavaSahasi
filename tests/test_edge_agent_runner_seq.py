from __future__ import annotations

from edge_agent.config import EdgeAgentSettings
from edge_agent.runner import EdgeAgentRunner


def _settings(tmp_path) -> EdgeAgentSettings:
    return EdgeAgentSettings(
        target="api",
        ingest_url="http://localhost:8000/v1/telemetry/ingest",
        drone_uid="DRN-001",
        device_id=None,
        shared_secret="secret-1",
        bridge_token="",
        input_mode="udp-json",
        udp_host="0.0.0.0",
        udp_port=15000,
        mavlink_device="/dev/ttyTHS1",
        mavlink_baud=57600,
        timeout_seconds=0.1,
        tls_ca_file=None,
        tls_client_cert_file=None,
        tls_client_key_file=None,
        tls_insecure_skip_verify=False,
        rate_hz=1.0,
        spool_db_path=str(tmp_path / "spool.db"),
        retry_max_attempts=3,
        retry_backoff_seconds=1.0,
        retry_backoff_max_seconds=5.0,
        queue_max=100,
        flush_batch_size=10,
        log_every=10,
    )


def test_seq_counter_increments_only_on_successful_normalization(tmp_path):
    settings = _settings(tmp_path)
    runner = EdgeAgentRunner(settings)

    captured: list[int] = []

    def fake_stream():
        yield {"lon": 29.0}  # invalid (missing lat)
        yield {"lat": 41.0, "lon": 29.0}  # valid -> seq 1
        yield {"lat": 41.1, "lon": 29.1}  # valid -> seq 2

    runner._stream = fake_stream  # type: ignore[method-assign]

    def fake_enqueue(payload):
        captured.append(int(payload["seq"]))
        if len(captured) >= 2:
            raise KeyboardInterrupt

    runner._enqueue_payload = fake_enqueue  # type: ignore[method-assign]
    runner._flush_once = lambda: None  # type: ignore[method-assign]

    # Force sampling gate open in tests.
    runner.sample_interval_seconds = 0.0

    try:
        runner.run()
    except KeyboardInterrupt:
        pass

    assert captured == [1, 2]
    assert runner.seq_counter == 2
