import sys

from scripts.compare_prompts import main


def test_compare_prompts_dry_run_lists_benchmarks(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["compare_prompts.py", "v1", "v2", "--dry-run"])

    assert main() == 0

    out = capsys.readouterr().out
    assert "benchmark instance" in out
    assert "csv_quoting" in out
    assert "zero_division" in out


def test_compare_prompts_dry_run_supports_instance_filter(monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        ["compare_prompts.py", "v1", "v2", "--dry-run", "--instance", "csv_quoting"],
    )

    assert main() == 0

    out = capsys.readouterr().out
    assert "csv_quoting" in out
    assert "dict_merge_overwrite" not in out
