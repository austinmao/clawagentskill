"""Security scanner suite for clawagentskill.

Provides four built-in scanners (prefilter, permission, config, injection)
plus an optional Snyk wrapper, all dispatched concurrently via the runner.
"""

from clawagentskill.scan.config import scan_config
from clawagentskill.scan.injection import scan_injection
from clawagentskill.scan.permission import scan_permission
from clawagentskill.scan.prefilter import scan_prefilter
from clawagentskill.scan.runner import run_scanners
from clawagentskill.scan.snyk import scan_snyk

__all__ = [
    "run_scanners",
    "scan_config",
    "scan_injection",
    "scan_permission",
    "scan_prefilter",
    "scan_snyk",
]
