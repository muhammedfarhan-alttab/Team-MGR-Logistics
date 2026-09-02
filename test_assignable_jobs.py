"""
Tests for the additive AssignableJob / pickup+drop job architecture.
Covers the three official Task 1 verification requirements:
  1. A known queue returns the correct job count.
  2. A known short route is costed lower than a known long route.
  3. A job with an unresolvable address is flagged rather than force-assigned.
Run directly: `python3 test_assignable_jobs.py`
"""

from logistics_agent import run_pipeline, ResolutionStatus


def test_correct_job_count():
    """One job per input item -- resolved, flagged, or malformed alike."""
    batch = [
        {
            "id": "J-1",
            "customer_name": "A",
            "pickup_address": "1 Rd, Chennai, TN",
            "address": "1 Rd, Chennai, TN",
        },
        {"id": "J-2", "customer_name": "B", "address": "1 Rd, Delhi, DL"},  # no pickup -> flagged, still a job
        "not a record",  # malformed -> still a job
        {"id": "J-3", "customer_name": "C"},  # no address fields at all -> flagged, still a job
    ]
    result = run_pipeline(batch)
    assert len(result["jobs"]) == len(batch), (
        f"expected {len(batch)} jobs for a queue of {len(batch)}, got {len(result['jobs'])}"
    )
    print(f"PASS: correct job count ({len(result['jobs'])} jobs for {len(batch)} input records)")


def test_short_route_costed_lower_than_long_route():
    """A same-city pickup/drop pair must cost less than a cross-country pair."""
    batch = [
        {
            "id": "SHORT",
            "customer_name": "Short Hop",
            "pickup_address": "1 Rd, Chennai, TN",
            "address": "2 Rd, Chennai, TN",
        },
        {
            "id": "LONG",
            "customer_name": "Long Haul",
            "pickup_address": "1 Rd, Chennai, TN",
            "address": "1 Rd, Delhi, DL",
        },
    ]
    result = run_pipeline(batch)
    jobs = {j.job_id: j for j in result["jobs"]}
    short_job, long_job = jobs["SHORT"], jobs["LONG"]

    assert short_job.assignable and long_job.assignable, "both jobs should have fully resolved pickup+drop legs"
    assert short_job.distance_km is not None and long_job.distance_km is not None, (
        "distance_km should be populated for fully-resolved jobs"
    )
    assert short_job.distance_km < long_job.distance_km, (
        f"expected short route ({short_job.distance_km} km) to cost less than "
        f"long route ({long_job.distance_km} km)"
    )
    print(
        f"PASS: short route ({short_job.distance_km} km) costed lower than "
        f"long route ({long_job.distance_km} km)"
    )


def test_unresolvable_address_flagged_not_assigned():
    """Bad drop, bad pickup, and missing pickup all must flag, never fabricate data."""
    batch = [
        {
            "id": "BAD-DROP",
            "customer_name": "Bad Drop",
            "pickup_address": "1 Rd, Chennai, TN",
            "address": "asdkjfh not a real place 000",
        },
        {
            "id": "BAD-PICKUP",
            "customer_name": "Bad Pickup",
            "pickup_address": "asdkjfh not a real place 000",
            "address": "1 Rd, Chennai, TN",
        },
        {
            "id": "NO-PICKUP",
            "customer_name": "No Pickup At All",
            "address": "1 Rd, Chennai, TN",
            # no pickup field, and no default_pickup_address configured below
        },
    ]
    result = run_pipeline(batch)
    jobs = {j.job_id: j for j in result["jobs"]}

    for jid in ("BAD-DROP", "BAD-PICKUP", "NO-PICKUP"):
        job = jobs[jid]
        assert job.assignable is False, f"{jid} should be flagged, not assignable"
        assert job.flag_reason, f"{jid} should have a non-empty flag_reason"
        assert job.distance_km is None, f"{jid} should never have a fabricated distance"

    assert jobs["BAD-DROP"].drop_status != ResolutionStatus.RESOLVED
    assert jobs["BAD-PICKUP"].pickup_status != ResolutionStatus.RESOLVED
    assert jobs["NO-PICKUP"].pickup_status == ResolutionStatus.EMPTY
    print("PASS: unresolvable pickup/drop addresses are flagged, never force-assigned")


def test_default_pickup_address_used_only_when_missing():
    """default_pickup_address fills in only when no per-record pickup exists at all."""
    batch_no_pickup_field = [
        {"id": "DEP-1", "customer_name": "Depot User", "address": "1 Rd, Chennai, TN"}
    ]
    result = run_pipeline(batch_no_pickup_field, default_pickup_address="1 Rd, Chennai, TN")
    job = result["jobs"][0]
    assert job.pickup_status == ResolutionStatus.RESOLVED
    assert job.assignable is True
    print("PASS: default_pickup_address is used when no per-record pickup field is present")

    # An explicit (even unresolvable) pickup must NOT be silently overridden by the default.
    batch_explicit_bad_pickup = [
        {
            "id": "DEP-2",
            "customer_name": "Explicit Bad Pickup",
            "pickup_address": "asdkjfh not a real place 000",
            "address": "1 Rd, Chennai, TN",
        }
    ]
    result2 = run_pipeline(batch_explicit_bad_pickup, default_pickup_address="1 Rd, Chennai, TN")
    job2 = result2["jobs"][0]
    assert job2.pickup_status != ResolutionStatus.RESOLVED, (
        "an explicit unresolvable pickup must not be silently replaced by default_pickup_address"
    )
    assert job2.assignable is False
    print("PASS: default_pickup_address never overrides an explicit pickup field")


def test_travel_time_and_capacity_are_seams_not_fabrications():
    """travel_time_minutes must stay None (never a hidden estimate); capacity is passthrough only."""
    batch = [
        {
            "id": "SEAM-1",
            "customer_name": "Seam Check",
            "pickup_address": "1 Rd, Chennai, TN",
            "address": "1 Rd, Delhi, DL",
            "vehicle_capacity_required": "2 pallets",
        }
    ]
    result = run_pipeline(batch)
    job = result["jobs"][0]
    assert job.travel_time_minutes is None, "travel_time_minutes must not be estimated/fabricated"
    assert "official Distance Matrix Cache travel-time interface" in job.travel_time_notes
    assert job.vehicle_capacity_required == "2 pallets", "capacity must be passed through verbatim"
    assert "NOT a live Fleet Watcher lookup" in job.vehicle_capacity_notes
    print("PASS: travel_time_minutes stays None and capacity is passthrough-only, per pending integrations")


if __name__ == "__main__":
    test_correct_job_count()
    test_short_route_costed_lower_than_long_route()
    test_unresolvable_address_flagged_not_assigned()
    test_default_pickup_address_used_only_when_missing()
    test_travel_time_and_capacity_are_seams_not_fabrications()
    print("\nALL ASSIGNABLE JOB TESTS PASSED")
