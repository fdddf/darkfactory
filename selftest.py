#!/usr/bin/env python3
"""Proves the PHPUnit runner works without needing WordPress or MySQL.

Builds a throwaway checkout whose vendor/bin/phpunit is a shell script that
emits JUnit XML, then checks the three things the oracle depends on:
selection resolves real paths, the XML is parsed per test, and quarantined
failures are suppressed rather than silently dropped.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from darkfactory import oracle
from darkfactory.policy import Policy
from darkfactory.runners import PhpUnitRunner
from darkfactory.schema import Decision, Patch

FAKE_PHPUNIT = r'''#!/bin/sh
# Stand-in for vendor/bin/phpunit. Emits JUnit XML like the real thing.
out=""
while [ $# -gt 0 ]; do
  case "$1" in
    --log-junit) out="$2"; shift 2 ;;
    *) shift ;;
  esac
done
mkdir -p "$(dirname "$out")"
cat > "$out" <<XML
<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="selected" tests="4" failures="2" errors="0">
    <testcase classname="Tests_Formatting_HumanTimeDiff" name="test_sub_minute_rounds_up" time="0.01"/>
    <testcase classname="Tests_Formatting_HumanTimeDiff" name="test_hours" time="0.01"/>
    <testcase classname="Tests_Date_Timezones" name="test_dst_boundary" time="0.40">
      <failure message="Failed asserting that 2 matches expected 1.">flaky under load</failure>
    </testcase>
    <testcase classname="Tests_Admin_Misc" name="test_save_user_setting" time="0.02">
      <failure message="Failed asserting that false is true.">genuine regression</failure>
    </testcase>
  </testsuite>
</testsuites>
XML
exit 1
'''

PATCH = Patch(
    diff="""diff --git a/wp-includes/formatting.php b/wp-includes/formatting.php
@@ -1,3 +1,3 @@
-	$mins = 0;
+	$mins = 1;
""",
    produced_by="selftest",
)

failures = []


def check(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r}")
        failures.append(label)


def main() -> int:
    repo = Path(tempfile.mkdtemp(prefix="df-selftest-"))
    try:
        (repo / "vendor/bin").mkdir(parents=True)
        php = repo / "vendor/bin/phpunit"
        php.write_text(FAKE_PHPUNIT)
        php.chmod(0o755)
        # Only formatting/ exists; formatting.php does not. Selection must
        # keep the first and drop the second rather than handing PHPUnit a
        # path that does not resolve.
        (repo / "tests/phpunit/tests/formatting").mkdir(parents=True)
        (repo / "tests/phpunit/tests/basic.php").write_text("<?php")

        print("\nselection")
        selected, strategy, missing = oracle.select_tests(PATCH, repo)
        check("resolves only paths that exist", selected,
              ["tests/phpunit/tests/basic.php", "tests/phpunit/tests/formatting"])
        check("always includes the smoke test", "tests/phpunit/tests/basic.php" in selected, True)
        check("reports unresolved candidates", missing, ["tests/phpunit/tests/formatting.php"])
        check("names its strategy", strategy, "path-heuristic-v1")

        print("\nbackend")
        runner = PhpUnitRunner(repo)
        check("detects the local backend", runner.backend, "local")
        check("reports available", runner.availability()[0], True)

        print("\njunit parsing")
        suite = runner.run_detailed(["tests/phpunit/tests/formatting"])
        check("ran", suite.ran, True)
        check("counted every case", suite.tests, 4)
        check("counted failures", suite.failures, 2)
        check("named the failures", suite.failed_ids, [
            "Tests_Date_Timezones::test_dst_boundary",
            "Tests_Admin_Misc::test_save_user_setting",
        ])
        check("kept a failure message", "Failed asserting" in suite.cases[2].message, True)
        check("cleaned up its report", list((repo / "build").glob("junit-*.xml")), [])

        print("\nper-selector execution")
        # PHPUnit 9 ignores every positional target but the first, so the
        # runner has to invoke it once per selector and merge.
        both = runner.run_detailed(selected)
        check("merges both selectors", both.tests, 8)
        check("records both commands", both.command.count("&&"), 1)
        check("passes --test-suffix", "--test-suffix" in both.command, True)

        print("\nquarantine")
        policy = Policy.load()
        policy.raw["quarantined_tests"] = ["Tests_Date_Timezones::*"]
        real, suppressed = oracle.partition_failures(suite.failed_ids, policy)
        check("suppresses the flaky one", suppressed, ["Tests_Date_Timezones::test_dst_boundary"])
        check("keeps the real one", real, ["Tests_Admin_Misc::test_save_user_setting"])

        print("\nsrc/ normalisation")
        from darkfactory.inspection import deterministic
        from darkfactory.schema import Decision as D
        src_patch = Patch(
            diff="diff --git a/src/wp-includes/pluggable.php b/src/wp-includes/pluggable.php\n"
                 "@@ -1,2 +1,2 @@\n-	$a = 1;\n+	$a = 2;\n",
            produced_by="selftest")
        hit = deterministic.inspect(src_patch, Policy.load())
        check("src/ prefix still hits a protected path", hit.decision, D.REJECT)
        check("and names the rule", hit.findings[0].rule, "protected_path")

        print("\noracle verdict")
        res = oracle.run(PATCH, policy, runner, repo=repo, repro_test="tests/phpunit/tests/formatting")
        check("rejects on a real failure", res.decision, Decision.REJECT)

        policy.raw["quarantined_tests"] = ["Tests_Date_Timezones::*", "Tests_Admin_Misc::*"]
        res = oracle.run(PATCH, policy, runner, repo=repo, repro_test="tests/phpunit/tests/formatting")
        check("suppressing every failure clears it", res.decision, Decision.ALLOW)
        check("but records what was suppressed", len(res.quarantine_suppressed), 2)

        print("\nno evidence is not good evidence")
        empty = oracle.run(PATCH, policy, runner, repo=repo, repro_test=None)
        check("missing repro test rejects", empty.decision, Decision.REJECT)
        check("empty selection escalates", runner.run_detailed([]).ran, False)

        print()
        if failures:
            print(f"{len(failures)} check(s) failed")
            return 1
        print("all checks passed")
        return 0
    finally:
        shutil.rmtree(repo, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
