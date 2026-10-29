"""End-to-end smoke test: drives a real browser through the running portal.

This is deliberately *not* a pytest module (hence the name). It starts its own
server on a free port, opens Chromium, and exercises the interactive flows that
pytest cannot reach -- the payroll run-detail modal, paying a line with a
reference, the payslip stacking above the run modal, the compile guard, the
attendance history card, and the phone layout -- asserting on rendered DOM
rather than JSON. It also checks that the strict Content-Security-Policy
produces no console violations.

    py -m tests.browser_smoke               # or: py tests/browser_smoke.py
    py -m tests.browser_smoke --headed      # watch it run
    py -m tests.browser_smoke --artifacts .\\shots

Requires Playwright and its Chromium build, which are dev-only extras:

    pip install -r requirements-dev.txt
    python -m playwright install chromium

Exits 0 if every check passed, 1 if any failed, 2 if the environment is missing.
"""
from __future__ import annotations

import argparse
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent

OWNER = ("0771112222", "owner123")
SUPERVISOR = ("0773334444", "super123")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Report:
    def __init__(self) -> None:
        self.passed = 0
        self.failures: list[str] = []

    def check(self, label: str, condition: bool, detail: str = "") -> bool:
        if condition:
            self.passed += 1
            print(f"  PASS  {label}")
        else:
            self.failures.append(f"{label}{' -- ' + detail if detail else ''}")
            print(f"  FAIL  {label}{'  (' + detail + ')' if detail else ''}")
        return bool(condition)

    @property
    def total(self) -> int:
        return self.passed + len(self.failures)


def sign_in(page, base: str, credentials: tuple[str, str], report: Report) -> None:
    phone, password = credentials
    page.goto(base)
    page.fill("#login-phone", phone)
    page.fill("#login-password", password)
    page.click("#login-form button[type=submit]")
    page.wait_for_selector("#app-shell", state="visible")
    report.check(f"signed in as {phone}", True)


def text_of(page, selector: str) -> str:
    """Rendered text, folded to lower case.

    Playwright returns text *after* CSS transforms, and .badge / .data-table th
    are `text-transform: uppercase`, so every comparison goes through here.
    """
    return page.inner_text(selector).lower()


def expected_run_figures(db: Path) -> tuple[int, int, int]:
    """(line count, total salary, salary_id reset to Pending) for the newest run.

    Read from the database rather than hardcoded: the demo seed is anchored to
    today, so the figures move with the calendar.
    """
    conn = sqlite3.connect(db)
    line_count, total = conn.execute(
        """SELECT COUNT(*), SUM(s.total_salary)
             FROM salaries s JOIN payroll_runs r ON r.run_id = s.run_id
            WHERE r.run_id = (SELECT run_id FROM payroll_runs ORDER BY period_end DESC LIMIT 1)"""
    ).fetchone()
    salary_id = conn.execute("SELECT MIN(salary_id) FROM salaries").fetchone()[0]
    conn.close()
    return line_count, total, salary_id


def check_run_modal(page, db: Path, artifacts: Path, report: Report, salary_id: int,
                    line_count: int, total: int) -> None:
    print("\n== owner: payroll run detail modal ==")
    page.click("#menu-salary")
    page.wait_for_selector("#runs-table-body tr")

    if not report.check(
        "run history offers a View button", page.locator('[data-action="view-run"]').count() > 0
    ):
        return

    page.click('[data-action="view-run"]')
    page.wait_for_selector("#run-modal.active")
    report.check("modal opens", page.is_visible("#run-modal"))

    rows = page.locator("#run-modal-body table.data-table tbody tr")
    report.check("modal lists every line", rows.count() == line_count, f"{rows.count()} of {line_count}")

    body = text_of(page, "#run-modal-body")
    report.check("modal shows the run total", f"{total:,}" in body, f"expected {total:,}")
    report.check("modal shows the rate snapshot", "above_80" in body)
    report.check("modal marks the reset line Pending", "pending" in body)
    report.check(
        "modal offers a payment reference field",
        page.locator("#run-modal-payment-ref").count() == 1,
    )
    page.fill("#run-modal-payment-ref", "CHQ-1001")

    if report.check(
        "pending line offers a Pay button",
        page.locator('[data-action="run-detail-pay"]').count() == 1,
    ):
        page.click('[data-action="run-detail-pay"]')
        page.wait_for_timeout(1500)
        report.check("modal stays open after paying", page.is_visible("#run-modal.active"))
        report.check(
            "row flips to Paid without reopening", "pending" not in text_of(page, "#run-modal-body")
        )

        paid = sqlite3.connect(db).execute(
            "SELECT status, payment_method, payment_ref FROM salaries WHERE salary_id=?",
            (salary_id,),
        ).fetchone()
        report.check("database records the payment", paid[0] == "Paid", str(paid))
        # Regression guard: the dropdown used to *display* the first method while
        # sending null, so the visible selection lied about what was recorded.
        report.check(
            "the displayed default payment method is the one sent",
            paid[1] == "Cash",
            f"recorded {paid[1]!r}, dropdown showed Cash",
        )
        report.check(
            "the payment reference is recorded",
            paid[2] == "CHQ-1001",
            f"recorded {paid[2]!r}",
        )

    page.screenshot(path=str(artifacts / "1-run-modal.png"))

    # Target the line that was just paid; other lines carry no reference.
    page.click(f'#run-modal-body [data-action="view-payslip"][data-id="{salary_id}"]')
    page.wait_for_selector("#payslip-modal.active")
    report.check("payslip opens from the run modal", page.is_visible("#payslip-modal"))
    report.check("payslip has a Paid via row", "paid via" in text_of(page, "#payslip-body"))
    report.check("payslip shows the recorded reference", "chq-1001" in text_of(page, "#payslip-body"))

    payslip_z = int(page.evaluate("getComputedStyle(document.getElementById('payslip-modal')).zIndex") or 0)
    run_z = int(page.evaluate("getComputedStyle(document.getElementById('run-modal')).zIndex") or 0)
    report.check(
        "payslip paints above the run modal",
        payslip_z > run_z,
        f"payslip z={payslip_z}, run z={run_z}",
    )
    page.screenshot(path=str(artifacts / "2-payslip.png"))

    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    report.check("Escape closes the payslip", not page.is_visible("#payslip-modal.active"))
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # Compiling is only valid for a finished 10-day window.
    today = date.today()
    page.fill("#salary-start-date", (today - timedelta(days=3)).isoformat())
    page.fill("#salary-end-date", today.isoformat())
    page.wait_for_timeout(1200)
    report.check(
        "compile is disabled for a short/in-progress range",
        page.is_disabled("#compile-run-btn"),
    )


def check_supervisor_sections(page, artifacts: Path, report: Report) -> None:
    print("\n== owner: supervisor multi-section assignment ==")
    report.check("desktop hides the hamburger", not page.is_visible("#mobile-toggle"))

    page.click("#menu-supervisors")
    page.wait_for_selector("#supervisors-table-body tr")
    row = page.locator("#supervisors-table-body tr", has_text="Kamal Silva")
    text = row.inner_text().lower()
    report.check(
        "seeded supervisor lists both assigned sections",
        "tea field a" in text and "tea field b" in text,
        text[:160],
    )

    page.click('[data-action="edit-user"][data-id="201"]')
    page.wait_for_selector("#user-modal.active")
    boxes = page.locator("#user-sections input[type=checkbox]")
    checked = page.locator("#user-sections input[type=checkbox]:checked")
    report.check("section picker offers every operational area", boxes.count() == 4, f"{boxes.count()} boxes")
    report.check("existing assignments are pre-selected", checked.count() == 2, f"{checked.count()} checked")

    page.uncheck('#user-sections input[value="Tea Field B"]')
    page.check('#user-sections input[value="Factory Processing"]')
    page.screenshot(path=str(artifacts / "6-supervisor-sections.png"))
    page.click("#user-form button[type=submit]")
    page.wait_for_timeout(1400)

    report.check("section modal closes after save", not page.is_visible("#user-modal.active"))
    text = page.locator("#supervisors-table-body tr", has_text="Kamal Silva").inner_text().lower()
    report.check("added section is displayed", "factory processing" in text, text[:160])
    report.check("removed section is gone", "tea field b" not in text, text[:160])


def check_attendance_history(page, artifacts: Path, report: Report) -> None:
    print("\n== supervisor: attendance history ==")
    page.click('[data-action="logout"]')
    page.wait_for_selector("#auth-view", state="visible")
    sign_in(page, page.url, SUPERVISOR, report)

    page.click("#menu-attendance")
    page.wait_for_selector("#history-table-body tr")
    report.check(
        "history table is populated",
        page.locator("#history-table-body tr").count() > 0,
        f"{page.locator('#history-table-body tr').count()} rows",
    )
    report.check(
        "date range defaults to the current cycle",
        bool(page.input_value("#history-start-date")) and bool(page.input_value("#history-end-date")),
        f'{page.input_value("#history-start-date")} .. {page.input_value("#history-end-date")}',
    )
    report.check("no summary chip for 'All servants'", page.inner_text("#history-summary").strip() == "")
    page.screenshot(path=str(artifacts / "3-attendance-history.png"))

    report.check(
        "servant filter is populated",
        page.locator("#history-servant option").count() > 1,
        f"{page.locator('#history-servant option').count()} options",
    )
    page.select_option("#history-servant", index=1)

    # Poll instead of page.wait_for_function: the CSP forbids 'unsafe-eval', so
    # Playwright cannot evaluate a JS predicate string on this page.
    for _ in range(25):
        if page.inner_text("#history-summary").strip():
            break
        page.wait_for_timeout(200)

    chip = page.inner_text("#history-summary").lower()
    report.check("summary chip appears for one servant", "present" in chip and "%" in chip, chip.strip())
    report.check("table narrows to that servant", page.locator("#history-table-body tr").count() > 0)
    page.screenshot(path=str(artifacts / "4-summary-chip.png"))

    page.select_option("#history-servant", index=0)
    page.fill("#history-start-date", "2020-01-01")
    page.click('[data-action="attendance-history-cycle"]')
    page.wait_for_timeout(800)
    report.check(
        "'Current Cycle' resets the range",
        page.input_value("#history-start-date") != "2020-01-01",
        page.input_value("#history-start-date"),
    )

    page.set_viewport_size({"width": 375, "height": 900})
    page.click("#mobile-toggle")
    page.click("#menu-weights")
    page.wait_for_timeout(600)
    columns = page.evaluate(
        "getComputedStyle(document.querySelector('.grid-weights')).gridTemplateColumns"
    )
    report.check(
        "two-column forms stack on a phone",
        len(columns.split()) == 1,
        columns,
    )
    page.screenshot(path=str(artifacts / "5-mobile-weights.png"))


def check_mobile_navigation(page, base: str, db: Path, artifacts: Path, report: Report) -> None:
    print("\n== supervisor: mobile drawer, logout, and retail weighing ==")
    page.set_viewport_size({"width": 375, "height": 700})
    # A distinct query string guarantees a real history entry, so go_back()
    # after logout exercises the bfcache/reload path instead of about:blank.
    page.goto(base + "/?mobile=1")
    page.wait_for_selector("#app-shell", state="visible")

    toggle = page.locator("#mobile-toggle")
    report.check("hamburger is visible on a phone", toggle.is_visible())
    box = toggle.bounding_box()
    report.check(
        "hamburger is a 40px+ tap target",
        bool(box) and box["width"] >= 40 and box["height"] >= 40,
        str(box),
    )
    report.check(
        "hamburger carries an accessible menu label",
        toggle.get_attribute("aria-label") == "Open navigation menu",
        str(toggle.get_attribute("aria-label")),
    )
    overflow = page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    report.check("phone layout has no horizontal page scroll", overflow <= 1, f"{overflow}px")
    report.check("decorative clock is hidden on a phone", not page.is_visible(".page-actions"))
    page.screenshot(path=str(artifacts / "7-mobile-closed.png"))

    toggle.click()
    page.wait_for_timeout(450)
    report.check("drawer opens", page.is_visible("#sidebar-nav"))
    report.check(
        "toggle swaps to the close icon",
        page.locator("#mobile-toggle svg.feather-x").count() == 1,
    )
    report.check(
        "toggle announces the open state",
        toggle.get_attribute("aria-label") == "Close navigation menu"
        and toggle.get_attribute("aria-expanded") == "true",
    )

    logout = page.locator("#logout-btn")
    report.check("logout is visible in the drawer", logout.is_visible())
    logout_box = logout.bounding_box()
    report.check(
        "logout stays inside the phone viewport",
        bool(logout_box) and logout_box["y"] + logout_box["height"] <= 700,
        str(logout_box),
    )
    report.check("logout has a visible text label", "sign out" in logout.inner_text().lower())
    report.check(
        "profile shows the signed-in name and role",
        page.locator("#user-display-name").inner_text().strip() != ""
        and page.locator("#user-display-role").inner_text().strip().lower() == "supervisor",
    )
    page.screenshot(path=str(artifacts / "8-mobile-drawer.png"))

    # Click the dimmed area to the right of the 280px drawer.
    page.mouse.click(355, 350)
    page.wait_for_timeout(400)
    report.check("clicking outside closes the drawer", not page.is_visible("#sidebar-nav"))
    report.check(
        "toggle resets to the open label",
        toggle.get_attribute("aria-label") == "Open navigation menu"
        and toggle.get_attribute("aria-expanded") == "false",
    )

    toggle.click()
    page.wait_for_timeout(400)
    page.click("#menu-weights")
    page.wait_for_timeout(800)
    report.check("choosing a menu link closes the drawer", not page.is_visible("#sidebar-nav"))

    # Smallest common phone width: still no sideways scroll, and the sign-out
    # control must remain on screen inside a short 320x568 viewport.
    page.set_viewport_size({"width": 320, "height": 568})
    page.wait_for_timeout(300)
    narrow_overflow = page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    report.check(
        "320px layout has no horizontal page scroll", narrow_overflow <= 1, f"{narrow_overflow}px"
    )
    toggle.click()
    page.wait_for_timeout(450)
    logout_box = page.locator("#logout-btn").bounding_box()
    report.check(
        "logout stays on-screen at 320x568",
        bool(logout_box) and logout_box["y"] + logout_box["height"] <= 568,
        str(logout_box),
    )
    page.mouse.click(305, 300)
    page.wait_for_timeout(350)
    page.set_viewport_size({"width": 375, "height": 700})
    page.wait_for_timeout(300)

    options = page.locator("#weight-servant-select option")
    labels = [options.nth(index).inner_text() for index in range(options.count())]
    report.check(
        "retail workers are selectable in weight entry",
        any("Pathum Nissanka" in label and "Retail Worker" in label for label in labels),
        str(labels),
    )

    page.select_option("#weight-servant-select", "303")
    page.fill("#weight-original", "60")
    page.select_option("#weight-area-select", "Packaging Section")
    day = page.input_value("#weight-date")
    page.click('#weight-entry-form button[type="submit"]')
    page.wait_for_timeout(1600)

    log_text = page.inner_text("#daily-weights-table-body").lower()
    report.check(
        "retail weighing appears in the weight log",
        "pathum nissanka" in log_text and "60" in log_text,
        log_text[:200],
    )
    saved = (
        sqlite3.connect(db)
        .execute(
            """SELECT original_weight, adjusted_weight, rainy_day, area
                 FROM weights WHERE servant_id = 303 AND work_date = ?""",
            (day,),
        )
        .fetchall()
    )
    report.check(
        "retail weighing stored with the rainy rule untouched",
        saved == [(60.0, 60.0, 0, "Packaging Section")],
        str(saved),
    )
    page.screenshot(path=str(artifacts / "9-mobile-retail-weight.png"))

    toggle.click()
    page.wait_for_timeout(400)
    page.click("#logout-btn")
    page.wait_for_selector("#auth-view", state="visible")
    report.check("mobile logout returns to the sign-in screen", page.is_visible("#auth-view"))
    report.check("signed-in shell is hidden after logout", not page.is_visible("#app-shell"))

    status = page.evaluate(
        "fetch('/api/auth/me', {credentials: 'same-origin'}).then((response) => response.status)"
    )
    report.check("session is invalid after logout", status == 401, f"status {status}")

    page.go_back(wait_until="load")
    for _ in range(20):
        if page.is_visible("#auth-view"):
            break
        page.wait_for_timeout(250)
    report.check(
        "browser Back after logout cannot reveal the portal",
        page.is_visible("#auth-view") and not page.is_visible("#app-shell"),
        f"url={page.url} auth={page.is_visible('#auth-view')} shell={page.is_visible('#app-shell')}",
    )
    page.screenshot(path=str(artifacts / "10-mobile-after-logout.png"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--headed", action="store_true", help="Show the browser window.")
    parser.add_argument("--artifacts", default=None, help="Where to write screenshots.")
    parser.add_argument("--port", type=int, default=0, help="Port for the test server (0 = pick one).")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Playwright is not installed.\n"
            "  pip install -r requirements-dev.txt\n"
            "  python -m playwright install chromium",
            file=sys.stderr,
        )
        return 2

    # The server is started with sys.executable, so whichever interpreter is
    # running this script must also be able to run the app. Fail loudly rather
    # than letting a bare "No module named flask" surface from a child process.
    import importlib.util

    missing = [name for name in ("flask", "waitress") if importlib.util.find_spec(name) is None]
    if missing:
        print(
            f"{sys.executable} cannot import: {', '.join(missing)}.\n"
            "Run this with the project virtualenv, e.g.\n"
            "  .venv\\Scripts\\python.exe -m tests.browser_smoke",
            file=sys.stderr,
        )
        return 2

    work = Path(tempfile.mkdtemp(prefix="tea-factory-smoke-"))
    db = work / "smoke.sqlite3"
    artifacts = Path(args.artifacts).resolve() if args.artifacts else work
    artifacts.mkdir(parents=True, exist_ok=True)
    port = args.port or free_port()
    base = f"http://127.0.0.1:{port}"

    env = {**os.environ, "TEA_FACTORY_DB": str(db)}
    flask = [sys.executable, "-m", "flask", "--app", "app"]

    print(f"== preparing database ({db}) ==")
    result = subprocess.run([*flask, "init-db", "--seed"], cwd=PROJECT, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout, result.stderr, file=sys.stderr)
        return 2
    print("  " + result.stdout.strip().splitlines()[-2])

    line_count, total, salary_id = expected_run_figures(db)

    # The seed leaves the previous cycle fully paid, so nothing would be payable.
    # Reset one line to Pending to give the modal's per-line Pay button work to do.
    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE salaries SET status='Pending', paid_at=NULL, paid_by=NULL WHERE salary_id=?",
        (salary_id,),
    )
    conn.commit()
    conn.close()
    print(f"  line {salary_id} reset to Pending (run has {line_count} lines, Rs {total:,})")

    print(f"\n== starting server on {base} ==")
    server = subprocess.Popen(
        [sys.executable, "-m", "waitress", "--host=127.0.0.1", f"--port={port}", "app:app"],
        cwd=PROJECT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    report = Report()
    try:
        for _ in range(40):
            try:
                urllib.request.urlopen(base, timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            print("server did not start", file=sys.stderr)
            return 2

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not args.headed)
            page = browser.new_page(viewport={"width": 1600, "height": 1000})

            console_errors: list[str] = []
            page_errors: list[str] = []
            page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: page_errors.append(str(e)))

            print("\n== owner: sign in ==")
            sign_in(page, base, OWNER, report)

            check_run_modal(page, db, artifacts, report, salary_id, line_count, total)
            check_supervisor_sections(page, artifacts, report)
            check_attendance_history(page, artifacts, report)
            check_mobile_navigation(page, base, db, artifacts, report)

            print("\n== console hygiene ==")
            csp = [e for e in console_errors if "Content Security Policy" in e or "Refused" in e]
            report.check("no CSP violations", not csp, str(csp[:2]))
            report.check("no uncaught JS errors", not page_errors, str(page_errors[:2]))

            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    print("\n" + "=" * 60)
    print(f"{report.passed}/{report.total} checks passed")
    if report.failures:
        print("\nFAILURES:")
        for failure in report.failures:
            print("  -", failure)
    print(f"screenshots: {artifacts}")
    return 1 if report.failures else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
