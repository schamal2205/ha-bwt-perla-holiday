"""Constants for the BWT Perla Holiday Mode integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "bwt_perla_holiday"
MANUFACTURER = "BWT"

CONF_CODE = "code"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 30  # seconds; the device API is rate limited
MIN_SCAN_INTERVAL = 10
DEFAULT_SCAN = timedelta(seconds=DEFAULT_SCAN_INTERVAL)

# After switching via the display, poll the API until it reflects the change.
VERIFY_ATTEMPTS = 6
VERIFY_DELAY = 2.0
