"""Real PHPUnit execution against a wordpress-develop checkout.

Two things make this more than a subprocess call.

First, we read results from JUnit XML rather than scraping stdout. Text
output changes between PHPUnit versions and tells us nothing per test; the
XML gives us every case by name, which is what quarantine and the audit
trail need.

Second, an empty or unrunnable selection is never a pass. If no tests
matched, or the suite could not start, the oracle has no evidence and the
bug goes to a human.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_TIMEOUT = int(os.environ.get("DF_PHPUNIT_TIMEOUT", "900"))

# WordPress names its test files humanTimeDiff.php, not humanTimeDiffTest.php.
# PHPUnit's default suffix for a directory argument is Test.php, so without
# this a directory selector runs ZERO tests and still exits 0 - a silent
# green on no evidence at all, which is the one outcome this whole pipeline
# exists to prevent.
BASE_ARGS = ("--test-suffix", ".php")


@dataclass(slots=True)
class TestCase:
    classname: str
    name: str
    status: str  # passed | failed | error | skipped
    time: float = 0.0
    message: str = ""

    @property
    def id(self) -> str:
        return f"{self.classname}::{self.name}"


@dataclass(slots=True)
class SuiteResult:
    ok: bool
    ran: bool
    tests: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0
    warnings: int = 0
    duration: float = 0.0
    cases: list[TestCase] = field(default_factory=list)
    command: str = ""
    exit_code: int = 0
    reason: str = ""
    output_tail: str = ""

    @property
    def failed_ids(self) -> list[str]:
        return [c.id for c in self.cases if c.status in ("failed", "error")]

    def summary(self) -> str:
        if not self.ran:
            return self.reason
        return (
            f"{self.tests} tests, {self.failures} failures, {self.errors} errors, "
            f"{self.warnings} warnings, {self.skipped} skipped in {self.duration:.1f}s"
        )


class PhpUnitRunner:
    """Runs the WordPress core suite.

    Backends, in the order `auto` tries them:

      local  <repo>/vendor/bin/phpunit            needs PHP + a MySQL the
                                                  tests config points at
      npm    npm run test:php -- <args>           needs Docker
      custom $DF_PHPUNIT_CMD with a {args} slot   e.g. a Nebius Sandbox

    The custom slot is the escape hatch: when nothing runs on this machine,
    point it at a sandbox and nothing else in the pipeline changes.
    """

    def __init__(
        self,
        repo: str | Path = "wp",
        backend: str = "auto",
        timeout: int = DEFAULT_TIMEOUT,
        extra_args: tuple[str, ...] = (),
    ) -> None:
        self.repo = Path(repo)
        self.timeout = timeout
        self.extra_args = list(extra_args)
        self.backend = backend if backend != "auto" else self._detect()

    # -- backend selection ------------------------------------------------

    def _detect(self) -> str:
        if os.environ.get("DF_PHPUNIT_CMD"):
            return "custom"
        if (self.repo / "vendor" / "bin" / "phpunit").exists() and shutil.which("php"):
            return "local"
        if (self.repo / "package.json").exists() and shutil.which("docker"):
            return "npm"
        return "none"

    def availability(self) -> tuple[bool, str]:
        """Why the runner cannot run, in words a teammate can act on."""
        if self.backend == "custom":
            return True, f"custom command: {os.environ['DF_PHPUNIT_CMD']}"
        if self.backend == "local":
            return True, f"local phpunit at {self.repo}/vendor/bin/phpunit"
        if self.backend == "npm":
            return True, "npm run test:php (docker)"
        if not self.repo.exists():
            return False, (
                f"no checkout at {self.repo}/ - "
                "git clone --depth 50 https://github.com/WordPress/wordpress-develop.git wp"
            )
        if not (self.repo / "vendor" / "bin" / "phpunit").exists():
            return False, (
                f"no phpunit in {self.repo}/vendor - run 'composer install' there, "
                "or install Docker and use the npm backend"
            )
        return False, "no usable PHPUnit backend; set DF_PHPUNIT_CMD to run elsewhere"

    # -- command construction ---------------------------------------------

    def _command(self, args: list[str]) -> list[str]:
        if self.backend == "custom":
            tpl = os.environ["DF_PHPUNIT_CMD"]
            import shlex

            return shlex.split(tpl.replace("{args}", " ".join(shlex.quote(a) for a in args)))
        if self.backend == "local":
            return ["./vendor/bin/phpunit", *args]
        if self.backend == "npm":
            return ["npm", "run", "test:php", "--", *args]
        raise RuntimeError("no PHPUnit backend available")

    # -- execution --------------------------------------------------------

    def run_detailed(self, selectors: list[str]) -> SuiteResult:
        """Run every selector and merge the results.

        PHPUnit 9 honours only the first positional target and silently
        ignores the rest, so passing the whole selection in one invocation
        runs a subset while still exiting 0. One run per selector costs a
        second of bootstrap each and cannot quietly skip anything.
        """
        available, why = self.availability()
        if not available:
            return SuiteResult(ok=False, ran=False, reason=why)

        if not selectors:
            return SuiteResult(
                ok=False, ran=False,
                reason="no tests were selected, so there is no evidence either way",
            )

        merged = SuiteResult(ok=True, ran=True, reason="suite completed")
        commands: list[str] = []
        started = time.monotonic()

        for selector in selectors:
            part = self._run_one(selector)
            commands.append(part.command)
            if not part.ran:
                # One selector that produced nothing invalidates the whole
                # set: we cannot tell a passing run from an absent one.
                part.command = " && ".join(commands)
                part.duration = time.monotonic() - started
                return part
            merged.tests += part.tests
            merged.failures += part.failures
            merged.errors += part.errors
            merged.warnings += part.warnings
            merged.skipped += part.skipped
            merged.cases += part.cases
            merged.ok = merged.ok and part.ok
            merged.exit_code = merged.exit_code or part.exit_code
            merged.output_tail = part.output_tail

        merged.command = " && ".join(commands)
        merged.duration = time.monotonic() - started

        if merged.tests == 0:
            merged.ok, merged.ran = False, False
            merged.reason = "the selection matched zero tests"
        return merged

    def _run_one(self, selector: str) -> SuiteResult:
        # Written inside the repo so a containerised run can see it too.
        rel = Path("build") / f"junit-{uuid.uuid4().hex[:8]}.xml"
        junit = self.repo / rel
        junit.parent.mkdir(parents=True, exist_ok=True)

        args = ["--log-junit", str(rel), *BASE_ARGS, *self.extra_args, selector]
        cmd = self._command(args)

        started = time.monotonic()
        try:
            proc = subprocess.run(
                cmd, cwd=self.repo, capture_output=True, text=True, timeout=self.timeout
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            code = proc.returncode
        except subprocess.TimeoutExpired:
            junit.unlink(missing_ok=True)
            return SuiteResult(
                ok=False, ran=False, command=" ".join(cmd), exit_code=-1,
                duration=time.monotonic() - started,
                reason=f"{selector} did not finish within {self.timeout}s",
            )

        duration = time.monotonic() - started

        if not junit.exists():
            return SuiteResult(
                ok=False, ran=False, command=" ".join(cmd), exit_code=code,
                duration=duration, output_tail=out[-1500:],
                reason=f"PHPUnit produced no JUnit report for {selector}, so it never ran",
            )

        result = self._parse(junit)
        junit.unlink(missing_ok=True)

        result.command = " ".join(cmd)
        result.exit_code = code
        result.duration = duration
        result.output_tail = out[-1500:]

        if result.tests == 0:
            result.ok, result.ran = False, False
            result.reason = f"{selector} matched zero tests"
        return result

    @staticmethod
    def _parse(path: Path) -> SuiteResult:
        root = ET.parse(path).getroot()
        cases: list[TestCase] = []

        for node in root.iter("testcase"):
            status, message = "passed", ""
            for kind, label in (
                ("failure", "failed"), ("error", "error"),
                ("warning", "warning"), ("skipped", "skipped"),
            ):
                child = node.find(kind)
                if child is not None:
                    status = label
                    message = (child.get("message") or child.text or "").strip()
                    break
            cases.append(
                TestCase(
                    classname=node.get("classname", ""),
                    name=node.get("name", ""),
                    status=status,
                    time=float(node.get("time") or 0),
                    message=message[:500],
                )
            )

        failures = sum(c.status == "failed" for c in cases)
        errors = sum(c.status == "error" for c in cases)
        skipped = sum(c.status == "skipped" for c in cases)
        warnings = sum(c.status == "warning" for c in cases)

        return SuiteResult(
            ok=(failures == 0 and errors == 0),
            ran=True,
            tests=len(cases),
            failures=failures,
            errors=errors,
            skipped=skipped,
            warnings=warnings,
            cases=cases,
            reason="suite completed",
        )

    # -- TestRunner protocol ----------------------------------------------

    def run(self, repo: str, selectors: list[str]) -> tuple[bool, str]:
        r = self.run_detailed(selectors)
        return r.ok, r.summary()
