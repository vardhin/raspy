"""System telemetry readers for the Raspberry Pi.

Every reader is *defensive*: it returns ``None`` (or a partial dict) when its
source isn't available, so the same code runs on the Pi (where ``vcgencmd``,
``/sys/class/thermal`` and ``/proc`` all exist) and degrades cleanly elsewhere
(dev laptop, CI) without raising. The attachment treats ``None`` as "unsupported"
and the UI simply hides that metric.

No third-party deps: everything comes from ``/proc``, ``/sys``, ``os.statvfs``
and the ``vcgencmd`` CLI — exactly what a Pi exposes.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

# --- low-level helpers ------------------------------------------------------


def _read_text(path: str) -> str | None:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def _vcgencmd(*args: str) -> str | None:
    """Run ``vcgencmd <args>`` and return stdout, or None if unavailable."""
    exe = shutil.which("vcgencmd")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, *args], capture_output=True, text=True, timeout=2.0
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


# --- temperature ------------------------------------------------------------


def cpu_temp_c() -> float | None:
    """CPU/SoC temperature in °C. Prefers vcgencmd, falls back to thermal zone."""
    raw = _vcgencmd("measure_temp")  # e.g. "temp=48.3'C"
    if raw:
        m = re.search(r"([-\d.]+)", raw)
        if m:
            return round(float(m.group(1)), 1)
    # Fallback: /sys/class/thermal/thermal_zone0/temp is in milli-°C.
    milli = _read_text("/sys/class/thermal/thermal_zone0/temp")
    if milli and milli.lstrip("-").isdigit():
        return round(int(milli) / 1000.0, 1)
    return None


# --- voltage & clocks (Pi-only, via vcgencmd) -------------------------------


def core_voltage_v() -> float | None:
    raw = _vcgencmd("measure_volts", "core")  # "volt=0.8625V"
    if raw:
        m = re.search(r"([-\d.]+)", raw)
        if m:
            return round(float(m.group(1)), 4)
    return None


def arm_clock_hz() -> int | None:
    raw = _vcgencmd("measure_clock", "arm")  # "frequency(48)=1500398464"
    if raw and "=" in raw:
        val = raw.split("=", 1)[1].strip()
        if val.isdigit():
            return int(val)
    # Fallback: current scaling freq is in kHz.
    khz = _read_text("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
    if khz and khz.isdigit():
        return int(khz) * 1000
    return None


# --- throttling / health (the real "is my Pi ok?" signal) -------------------

# Bit meanings of `vcgencmd get_throttled`. Low bits = currently active,
# high bits (>=16) = "has occurred since boot".
_THROTTLE_BITS = {
    0: ("under_voltage", "Under-voltage detected"),
    1: ("freq_capped", "ARM frequency capped"),
    2: ("throttled", "Currently throttled"),
    3: ("soft_temp_limit", "Soft temperature limit active"),
    16: ("under_voltage_occurred", "Under-voltage has occurred"),
    17: ("freq_capped_occurred", "ARM frequency capping has occurred"),
    18: ("throttled_occurred", "Throttling has occurred"),
    19: ("soft_temp_limit_occurred", "Soft temperature limit has occurred"),
}


def throttle_state() -> dict[str, Any] | None:
    raw = _vcgencmd("get_throttled")  # "throttled=0x0"
    if not raw or "=" not in raw:
        return None
    try:
        value = int(raw.split("=", 1)[1].strip(), 16)
    except ValueError:
        return None
    flags = {name: bool(value & (1 << bit)) for bit, (name, _) in _THROTTLE_BITS.items()}
    active = [
        desc
        for bit, (name, desc) in _THROTTLE_BITS.items()
        if bit < 16 and (value & (1 << bit))
    ]
    occurred = [
        desc
        for bit, (name, desc) in _THROTTLE_BITS.items()
        if bit >= 16 and (value & (1 << bit))
    ]
    return {
        "raw": f"0x{value:x}",
        "ok": value == 0,
        "flags": flags,
        "active": active,
        "occurred": occurred,
    }


# --- CPU load ---------------------------------------------------------------


def _cpu_times() -> tuple[int, int] | None:
    """Return (idle, total) jiffies from /proc/stat's aggregate cpu line."""
    line = _read_text("/proc/stat")
    if not line:
        return None
    first = line.splitlines()[0]
    if not first.startswith("cpu "):
        return None
    parts = [int(x) for x in first.split()[1:]]
    if len(parts) < 5:
        return None
    idle = parts[3] + (parts[4] if len(parts) > 4 else 0)  # idle + iowait
    total = sum(parts)
    return idle, total


# Module-level sample so successive calls compute a delta (busy % since last call).
_last_cpu: dict[str, int] = {}


def cpu_percent() -> float | None:
    sample = _cpu_times()
    if sample is None:
        return None
    idle, total = sample
    prev_idle = _last_cpu.get("idle")
    prev_total = _last_cpu.get("total")
    _last_cpu["idle"], _last_cpu["total"] = idle, total
    if prev_idle is None or prev_total is None:
        return None  # need two samples; first call primes it
    d_total = total - prev_total
    d_idle = idle - prev_idle
    if d_total <= 0:
        return None
    return round(100.0 * (1.0 - d_idle / d_total), 1)


def load_average() -> list[float] | None:
    raw = _read_text("/proc/loadavg")
    if not raw:
        return None
    parts = raw.split()
    if len(parts) < 3:
        return None
    try:
        return [float(parts[0]), float(parts[1]), float(parts[2])]
    except ValueError:
        return None


def cpu_count() -> int:
    return os.cpu_count() or 1


# --- memory -----------------------------------------------------------------


def memory() -> dict[str, int] | None:
    raw = _read_text("/proc/meminfo")
    if not raw:
        return None
    vals: dict[str, int] = {}
    for line in raw.splitlines():
        m = re.match(r"(\w+):\s+(\d+)\s*kB", line)
        if m:
            vals[m.group(1)] = int(m.group(2)) * 1024  # kB -> bytes
    total = vals.get("MemTotal")
    if total is None:
        return None
    available = vals.get("MemAvailable", vals.get("MemFree", 0))
    used = total - available
    swap_total = vals.get("SwapTotal", 0)
    swap_free = vals.get("SwapFree", 0)
    return {
        "total": total,
        "available": available,
        "used": used,
        "percent": round(100.0 * used / total, 1) if total else 0.0,
        "swap_total": swap_total,
        "swap_used": swap_total - swap_free,
    }


# --- storage ----------------------------------------------------------------


def _disk_usage(path: str) -> dict[str, Any] | None:
    try:
        st = os.statvfs(path)
    except OSError:
        return None
    total = st.f_blocks * st.f_frsize
    free = st.f_bavail * st.f_frsize
    used = total - (st.f_bfree * st.f_frsize)
    if total == 0:
        return None
    return {
        "mount": path,
        "total": total,
        "used": used,
        "free": free,
        "percent": round(100.0 * used / total, 1),
    }


def storage() -> list[dict[str, Any]]:
    """Usage for the real filesystems backing the OS. Root always; /boot if present."""
    seen: set[tuple[int, int]] = set()
    out: list[dict[str, Any]] = []
    for candidate in ("/", "/boot", "/boot/firmware"):
        if not os.path.isdir(candidate):
            continue
        try:
            dev = os.stat(candidate).st_dev
        except OSError:
            continue
        key = (dev, 0)
        if key in seen:
            continue
        seen.add(key)
        u = _disk_usage(candidate)
        if u:
            out.append(u)
    return out


# --- uptime & misc ----------------------------------------------------------


def uptime_seconds() -> float | None:
    raw = _read_text("/proc/uptime")
    if not raw:
        return None
    try:
        return float(raw.split()[0])
    except (ValueError, IndexError):
        return None


def model() -> str | None:
    # Raspberry Pi exposes its model string here.
    name = _read_text("/sys/firmware/devicetree/base/model") or _read_text(
        "/proc/device-tree/model"
    )
    if name:
        return name.replace("\x00", "").strip()
    return None


# --- aggregate snapshot -----------------------------------------------------


def snapshot() -> dict[str, Any]:
    """One full reading of every metric. Missing sources are omitted/None."""
    return {
        "time": time.time(),
        "model": model(),
        "uptime": uptime_seconds(),
        "temp_c": cpu_temp_c(),
        "voltage_v": core_voltage_v(),
        "arm_hz": arm_clock_hz(),
        "throttle": throttle_state(),
        "cpu_percent": cpu_percent(),
        "cpu_count": cpu_count(),
        "load": load_average(),
        "memory": memory(),
        "storage": storage(),
    }
