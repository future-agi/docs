"""tools/scan_local_stack.py with the Docker calls replaced: a failed read must never read as 'not found'."""
import importlib.util
import os
import subprocess
import sys

import pytest

TOOL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "scan_local_stack.py")


@pytest.fixture()
def scan(monkeypatch):
    spec = importlib.util.spec_from_file_location("scan_local_stack", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    return mod


def fake_stack(mod, monkeypatch, rows, fail_table=None):
    """rows: {clickhouse table: text}. Postgres has the project and no other rows."""
    def run(cmd):
        sql = cmd[-1]
        ok = lambda out="": subprocess.CompletedProcess(cmd, 0, out, "")  # noqa: E731
        if "docker" == cmd[0] and "psql" in cmd:
            if "from tracer_project" in sql:
                return ok("proj-1\n")
            if "information_schema.columns" in sql:
                return ok("tracer_trace\n")
            return ok("")
        if "system.tables" in sql:
            return ok("\n".join(rows) + "\n")
        for table, text in rows.items():
            if f"FROM {table} " in sql:
                if table == fail_table:
                    return subprocess.CompletedProcess(cmd, 241, "", "MEMORY_LIMIT_EXCEEDED")
                return ok(text)
        return ok("")
    monkeypatch.setattr(mod, "run", run)


def run_main(mod, monkeypatch, argv, capsys):
    monkeypatch.setattr(sys, "argv", ["scan_local_stack.py", *argv])
    code = mod.main()
    return code, capsys.readouterr().out


def test_absent_needle_passes_and_present_needle_fails(scan, monkeypatch, capsys):
    fake_stack(scan, monkeypatch, {"spans": '{"attrs":"hello"}\n'})
    code, out = run_main(scan, monkeypatch, ["--project", "p", "--needle", "SECRETMARKER"], capsys)
    assert code == 0 and "RESULT: PASS" in out
    fake_stack(scan, monkeypatch, {"spans": '{"attrs":"has SECRETMARKER inside"}\n'})
    code, out = run_main(scan, monkeypatch, ["--project", "p", "--needle", "SECRETMARKER"], capsys)
    assert code == 1 and "FOUND" in out


def test_expect_found_inverts_the_verdict(scan, monkeypatch, capsys):
    fake_stack(scan, monkeypatch, {"spans": '{"attrs":"has SECRETMARKER inside"}\n'})
    code, _ = run_main(scan, monkeypatch, ["--project", "p", "--expect-found", "--needle", "secretmarker", "--ignore-case"], capsys)
    assert code == 0


def test_a_table_that_cannot_be_read_is_no_verdict_not_a_pass(scan, monkeypatch, capsys):
    fake_stack(scan, monkeypatch, {"spans": '{"attrs":"hello"}\n', "end_users": '{"x":1}\n'}, fail_table="end_users")
    code, out = run_main(scan, monkeypatch, ["--project", "p", "--needle", "SECRETMARKER"], capsys)
    assert code == 3 and "SCAN INCOMPLETE" in out and "RESULT: PASS" not in out


def test_no_span_rows_is_exit_two(scan, monkeypatch, capsys):
    fake_stack(scan, monkeypatch, {"end_users": '{"x":1}\n'})
    code, out = run_main(scan, monkeypatch, ["--project", "p", "--needle", "x"], capsys)
    assert code == 2 and "no span rows" in out


def test_labelled_needles_never_print_their_value(scan, monkeypatch, capsys):
    fake_stack(scan, monkeypatch, {"spans": '{"attrs":"hello"}\n'})
    code, out = run_main(scan, monkeypatch, ["--project", "p", "--needle", "home=/Users/someone/private"], capsys)
    assert "home" in out and "/Users/someone/private" not in out


def test_wire_files_are_scanned_too(scan, monkeypatch, capsys, tmp_path):
    fake_stack(scan, monkeypatch, {"spans": '{"attrs":"hello"}\n'})
    wire = tmp_path / "wire.jsonl"
    wire.write_text('{"body":"WIREMARKER"}\n')
    code, out = run_main(scan, monkeypatch, ["--project", "p", "--needle", "WIREMARKER", "--wire", str(wire)], capsys)
    assert code == 1 and "wire.wire.jsonl" in out
