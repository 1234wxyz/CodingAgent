"""
tests/test_benchmark.py — benchmark instance discovery and metadata parsing.
"""

import json
from pathlib import Path

from scripts.benchmark import discover_instances, BENCHMARKS_DIR


def test_discover_instances_finds_all():
    instances = discover_instances()
    assert len(instances) >= 5, f"Expected >=5 instances, found {len(instances)}"
    names = [d.name for d in instances]
    assert "dict_merge_overwrite" in names
    assert "csv_quoting" in names
    assert "regex_escape" in names


def test_instance_json_has_required_fields():
    for d in discover_instances():
        meta = json.loads((d / "instance.json").read_text(encoding="utf-8"))
        assert "name" in meta, f"Missing 'name' in {d.name}/instance.json"
        assert "description" in meta, f"Missing 'description' in {d.name}/instance.json"
        assert "test_command" in meta, f"Missing 'test_command' in {d.name}/instance.json"
        assert "target_paths" in meta, f"Missing 'target_paths' in {d.name}/instance.json"
