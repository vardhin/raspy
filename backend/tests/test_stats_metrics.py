"""Tests for the System Stats metric readers.

These exercise the parsing/decoding logic deterministically by monkeypatching the
two raw sources (``vcgencmd`` output and ``/proc``-style file reads), so they pass
on any OS — the dev laptop and CI included, not just a Pi. They also assert the
*graceful degradation* contract: when a source is missing, the reader returns
``None`` instead of raising.
"""

from __future__ import annotations

import pytest

from raspy.attachments.stats import metrics


@pytest.fixture(autouse=True)
def _reset_cpu_sample():
    metrics._last_cpu.clear()
    yield
    metrics._last_cpu.clear()


# --- temperature ------------------------------------------------------------


def test_temp_from_vcgencmd(monkeypatch):
    monkeypatch.setattr(metrics, "_vcgencmd", lambda *a: "temp=48.3'C")
    assert metrics.cpu_temp_c() == 48.3


def test_temp_falls_back_to_thermal_zone(monkeypatch):
    monkeypatch.setattr(metrics, "_vcgencmd", lambda *a: None)
    monkeypatch.setattr(
        metrics, "_read_text", lambda p: "52123" if "thermal" in p else None
    )
    assert metrics.cpu_temp_c() == 52.1


def test_temp_none_when_no_source(monkeypatch):
    monkeypatch.setattr(metrics, "_vcgencmd", lambda *a: None)
    monkeypatch.setattr(metrics, "_read_text", lambda p: None)
    assert metrics.cpu_temp_c() is None


# --- voltage & clock --------------------------------------------------------


def test_core_voltage(monkeypatch):
    monkeypatch.setattr(metrics, "_vcgencmd", lambda *a: "volt=0.8625V")
    assert metrics.core_voltage_v() == 0.8625


def test_arm_clock(monkeypatch):
    monkeypatch.setattr(metrics, "_vcgencmd", lambda *a: "frequency(48)=1500398464")
    assert metrics.arm_clock_hz() == 1500398464


# --- throttle decoding (the core health signal) -----------------------------


def test_throttle_all_clear(monkeypatch):
    monkeypatch.setattr(metrics, "_vcgencmd", lambda *a: "throttled=0x0")
    t = metrics.throttle_state()
    assert t is not None
    assert t["ok"] is True
    assert t["active"] == []
    assert t["occurred"] == []


def test_throttle_active_undervoltage(monkeypatch):
    # bit 0 set = currently under-voltage
    monkeypatch.setattr(metrics, "_vcgencmd", lambda *a: "throttled=0x1")
    t = metrics.throttle_state()
    assert t["ok"] is False
    assert t["flags"]["under_voltage"] is True
    assert "Under-voltage detected" in t["active"]


def test_throttle_occurred_since_boot(monkeypatch):
    # bit 16 set = under-voltage has occurred (but not currently active)
    monkeypatch.setattr(metrics, "_vcgencmd", lambda *a: "throttled=0x10000")
    t = metrics.throttle_state()
    assert t["ok"] is False
    assert t["active"] == []
    assert "Under-voltage has occurred" in t["occurred"]
    assert t["flags"]["under_voltage"] is False
    assert t["flags"]["under_voltage_occurred"] is True


def test_throttle_none_off_pi(monkeypatch):
    monkeypatch.setattr(metrics, "_vcgencmd", lambda *a: None)
    assert metrics.throttle_state() is None


# --- cpu --------------------------------------------------------------------


def test_cpu_percent_needs_two_samples(monkeypatch):
    samples = iter([(100, 200), (110, 400)])  # (idle, total)
    monkeypatch.setattr(metrics, "_cpu_times", lambda: next(samples))
    # first call primes, returns None
    assert metrics.cpu_percent() is None
    # second: d_idle=10, d_total=200 -> busy = 1 - 10/200 = 95%
    assert metrics.cpu_percent() == 95.0


def test_load_average(monkeypatch):
    monkeypatch.setattr(metrics, "_read_text", lambda p: "0.52 0.41 0.30 1/523 12345")
    assert metrics.load_average() == [0.52, 0.41, 0.30]


# --- memory -----------------------------------------------------------------


def test_memory_parsing(monkeypatch):
    meminfo = (
        "MemTotal:        4000000 kB\n"
        "MemFree:          500000 kB\n"
        "MemAvailable:    1000000 kB\n"
        "SwapTotal:        100000 kB\n"
        "SwapFree:          80000 kB\n"
    )
    monkeypatch.setattr(metrics, "_read_text", lambda p: meminfo)
    m = metrics.memory()
    assert m["total"] == 4000000 * 1024
    assert m["available"] == 1000000 * 1024
    assert m["used"] == (4000000 - 1000000) * 1024
    assert m["percent"] == 75.0
    assert m["swap_total"] == 100000 * 1024
    assert m["swap_used"] == 20000 * 1024


def test_memory_none_when_absent(monkeypatch):
    monkeypatch.setattr(metrics, "_read_text", lambda p: None)
    assert metrics.memory() is None


# --- uptime -----------------------------------------------------------------


def test_uptime(monkeypatch):
    monkeypatch.setattr(metrics, "_read_text", lambda p: "123456.78 98765.43")
    assert metrics.uptime_seconds() == 123456.78


# --- aggregate snapshot never raises ----------------------------------------


def test_snapshot_is_safe_without_any_source(monkeypatch):
    monkeypatch.setattr(metrics, "_vcgencmd", lambda *a: None)
    monkeypatch.setattr(metrics, "_read_text", lambda p: None)
    snap = metrics.snapshot()  # must not raise
    assert "time" in snap
    assert snap["temp_c"] is None
    assert snap["throttle"] is None
    # storage() uses os.statvfs on real dirs; it returns a list regardless.
    assert isinstance(snap["storage"], list)
    assert snap["cpu_count"] >= 1
