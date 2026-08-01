# Guard test: no workspace-specific / customer-specific IDs in source code.
#
# Regex design choices:
#   mas-[0-9a-f]{8}-endpoint  — catches real leaked MAS endpoint slugs like
#                                "mas-3a71922a-endpoint" or "mas-1a0aee60-endpoint".
#                                Does NOT match variable names (model_endpoint_name)
#                                or DAB var references (${var.model_endpoint_name}).
#   01ef[0-9a-f]{6,}          — catches real Genie space IDs (e.g. 01ef8a2c3d4e5f6a).
#                                Requires 6+ hex chars after "01ef" so the short
#                                placeholder "01efabc" (3 chars) used in test fixtures
#                                does NOT match — and tests/ is excluded anyway.
#   alaska.airlines            — catches any hardcoded "Alaska Airlines" / "alaska-airlines"
#                                customer reference, case-insensitive. Does NOT match
#                                generic placeholder strings or DAB variable names.
#
# Only scans src/app/**/*.py (NOT tests/) so regex literals here don't self-match.
import pathlib
import re


def test_no_hardcoded_endpoint_or_space():
    root = pathlib.Path(__file__).resolve().parents[1]
    bad = re.compile(
        r"mas-[0-9a-f]{8}-endpoint|01ef[0-9a-f]{6,}|alaska.airlines",
        re.IGNORECASE,
    )
    hits = []
    for p in root.rglob("*.py"):
        if "tests" in p.parts:
            continue
        if bad.search(p.read_text(encoding="utf-8", errors="ignore")):
            hits.append(str(p))
    assert not hits, f"hardcoded ids in: {hits}"
