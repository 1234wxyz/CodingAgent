"""Benchmark instance discovery and metadata parsing."""

import json

from scripts.benchmark import discover_instances


def test_discover_instances_finds_all():
    instances = discover_instances()
    assert len(instances) >= 12, f"Expected >=12 instances, found {len(instances)}"
    names = [instance.name for instance in instances]
    assert "dict_merge_overwrite" in names
    assert "csv_quoting" in names
    assert "regex_escape" in names
    assert "zero_division" in names
    assert "import_cycle" in names
    assert "free_shipping_threshold" in names
    assert "path_normalization" in names


def test_instance_json_has_required_fields():
    for instance in discover_instances():
        meta = json.loads((instance / "instance.json").read_text(encoding="utf-8"))
        assert "name" in meta, f"Missing 'name' in {instance.name}/instance.json"
        assert "description" in meta, f"Missing 'description' in {instance.name}/instance.json"
        assert "test_command" in meta, f"Missing 'test_command' in {instance.name}/instance.json"
        assert "target_paths" in meta, f"Missing 'target_paths' in {instance.name}/instance.json"
