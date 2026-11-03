import os
import subprocess
import sys

import pytest

from verification.process import bounded_capture
from verification.runner import parse_junit


def test_excess_output_terminates_capture_without_unbounded_memory_or_disk():
    with pytest.raises(ValueError, match="capture limit"):
        bounded_capture(
            [sys.executable, "-c", "print('x'*100000)"], 5, {"PATH": os.environ.get("PATH", "")}, limit=1000
        )


def test_capture_deadline_terminates_stalled_process():
    with pytest.raises(subprocess.TimeoutExpired):
        bounded_capture(
            [sys.executable, "-c", "import time; time.sleep(10)"], 0.05, {"PATH": os.environ.get("PATH", "")}
        )


def test_test_reports_cannot_expand_declared_entities():
    malicious = '<!DOCTYPE testsuite [<!ENTITY x "expanded">]><testsuite><testcase name="&x;"/></testsuite>'
    with pytest.raises(ValueError, match="DTD and entity"):
        parse_junit(malicious)
    assert parse_junit('<testsuite><testcase name="test_safe"/></testsuite>') == {"test_safe": "passed"}
