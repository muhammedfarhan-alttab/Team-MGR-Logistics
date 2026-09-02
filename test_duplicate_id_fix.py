"""
Regression test for the critical bug: two malformed (non-dict) records in the
same batch used to be assigned the identical generated id, because seen_ids
was never updated for that branch. Run directly: `python3 test_duplicate_id_fix.py`
"""

from logistics_agent import run_pipeline


def test_multiple_malformed_records_get_unique_ids():
    batch = [
        {"id": "OK-1", "customer_name": "Fine", "address": "1 Rd, Chennai, TN"},
        "not a record",
        12345,
        ["also", "not", "a", "record"],
        None,
    ]
    result = run_pipeline(batch)
    ids = [r.record_id for r in result["records"]]
    assert len(ids) == len(batch), "every input item should produce exactly one record"
    assert len(ids) == len(set(ids)), f"record_ids must all be unique, got: {ids}"
    print(f"PASS: {len(batch) - 1} malformed records all received unique ids: {ids}")


def test_falsy_but_legitimate_id_is_preserved():
    """id=0 previously got silently discarded by the `or`-chain fallback."""
    batch = [{"id": 0, "customer_name": "Zero Id Customer", "address": "1 Rd, Chennai, TN"}]
    result = run_pipeline(batch)
    record = result["records"][0]
    assert record.record_id == "0", f"expected record_id '0', got {record.record_id!r}"
    print("PASS: id=0 is preserved instead of being discarded")


def test_falsy_but_legitimate_customer_name_is_preserved():
    """An explicitly blank customer_name should stay blank, not be silently
    overridden by a later fallback key or 'Unknown Customer', since it is
    genuinely present in the source data."""
    batch = [{
        "id": "C-1",
        "customer_name": "",
        "customer": "Should Not Be Used",
        "address": "1 Rd, Chennai, TN",
    }]
    result = run_pipeline(batch)
    record = result["records"][0]
    assert record.customer_name == "", f"expected blank customer_name, got {record.customer_name!r}"
    print("PASS: explicitly blank customer_name is preserved, not overridden by fallback key")


if __name__ == "__main__":
    test_multiple_malformed_records_get_unique_ids()
    test_falsy_but_legitimate_id_is_preserved()
    test_falsy_but_legitimate_customer_name_is_preserved()
    print("\nALL DUPLICATE-ID / FALLBACK TESTS PASSED")
