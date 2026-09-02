"""
Asserted tests for genuinely empty / missing data sources.
Run directly: `python3 test_empty_sources.py`
Exits non-zero (via AssertionError) if any check fails.
"""

import json
import os
import tempfile

from logistics_agent import run_pipeline, load_delivery_data


def test_empty_list_source():
    result = run_pipeline([])
    assert result["records"] == [], "empty list source should produce zero records"
    assert result["distance_matrix"] == {}, "empty list source should produce an empty distance matrix"
    assert result["report"]["total_records"] == 0
    assert result["report"]["status_counts"] == {}
    print("PASS: empty list source")


def test_missing_json_file():
    missing_path = "/tmp/this_file_does_not_exist_12345.json"
    assert not os.path.exists(missing_path), "test setup assumption broken: file unexpectedly exists"
    result = run_pipeline(missing_path)
    assert result["records"] == [], "missing .json file should produce zero records, not raise"
    assert result["report"]["total_records"] == 0
    print("PASS: missing .json file")


def test_missing_csv_file():
    missing_path = "/tmp/this_file_does_not_exist_12345.csv"
    assert not os.path.exists(missing_path)
    result = run_pipeline(missing_path)
    assert result["records"] == [], "missing .csv file should produce zero records, not raise"
    print("PASS: missing .csv file")


def test_empty_json_file_content():
    """A .json file that exists but contains an empty array."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump([], f)
        path = f.name
    try:
        result = run_pipeline(path)
        assert result["records"] == [], "a JSON file containing [] should produce zero records"
        assert result["report"]["total_records"] == 0
    finally:
        os.remove(path)
    print("PASS: empty JSON file content ([])")


def test_empty_csv_file_content():
    """A .csv file that exists but has only a header row, no data rows."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
        f.write("id,customer_name,address\n")
        path = f.name
    try:
        result = run_pipeline(path)
        assert result["records"] == [], "a CSV with only a header row should produce zero records"
        assert result["report"]["total_records"] == 0
    finally:
        os.remove(path)
    print("PASS: empty CSV file content (header only)")


def test_truly_empty_csv_file():
    """A .csv file that exists but is completely empty (no header, no rows)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
        pass  # write nothing at all
    path = f.name
    try:
        result = run_pipeline(path)
        assert result["records"] == [], "a completely empty CSV file should produce zero records, not raise"
    finally:
        os.remove(path)
    print("PASS: completely empty CSV file (no header)")


def test_malformed_json_file_does_not_crash():
    """Bonus: a .json file with invalid JSON syntax should degrade, not raise."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{ this is not valid json ][")
        path = f.name
    try:
        result = run_pipeline(path)
        assert result["records"] == [], "malformed JSON should degrade to zero records, not raise"
    finally:
        os.remove(path)
    print("PASS: malformed JSON file content does not crash the pipeline")


def test_load_delivery_data_directly_returns_list():
    """Sanity check on the loader itself, independent of run_pipeline."""
    assert load_delivery_data([]) == []
    assert load_delivery_data("/tmp/definitely_missing_xyz.json") == []
    assert load_delivery_data("/tmp/definitely_missing_xyz.csv") == []
    assert load_delivery_data(12345) == []  # not a list, not a string -> []
    print("PASS: load_delivery_data direct edge cases")


if __name__ == "__main__":
    test_empty_list_source()
    test_missing_json_file()
    test_missing_csv_file()
    test_empty_json_file_content()
    test_empty_csv_file_content()
    test_truly_empty_csv_file()
    test_malformed_json_file_does_not_crash()
    test_load_delivery_data_directly_returns_list()
    print("\nALL EMPTY-SOURCE TESTS PASSED")
