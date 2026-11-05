#!/usr/bin/env python3
"""Print Charge Sentinel’s normalized capability result for this computer."""

from __future__ import annotations

import json

from charge_sentinel_capabilities import detect_current_platform


if __name__ == '__main__':
    print(json.dumps(detect_current_platform().to_dict(), indent=2, sort_keys=True))
