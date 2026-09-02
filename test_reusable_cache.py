from logistics_agent import run_pipeline, AddressResolver, DistanceMatrixCache, LogisticsAgent


def test_backward_compatible_single_call():
    """Old call style (no resolver/cache args) must still work exactly as before."""
    result = run_pipeline([{"id": "X-1", "customer_name": "A", "address": "1 Rd, Chennai, TN"}])
    assert result["records"][0].resolution_status.value == "resolved"
    print("PASS: run_pipeline(source) still works with no extra args")


def test_shared_resolver_across_two_calls():
    resolver = AddressResolver()
    distance_cache = DistanceMatrixCache()

    batch1 = [{"id": "A-1", "customer_name": "A", "address": "1 Rd, Chennai, TN"}]
    batch2 = [{"id": "A-2", "customer_name": "B", "address": "1 Rd, Chennai, TN"}]  # same address

    run_pipeline(batch1, resolver=resolver, distance_cache=distance_cache)
    assert resolver.cache_misses == 1 and resolver.cache_hits == 0

    run_pipeline(batch2, resolver=resolver, distance_cache=distance_cache)
    # Second call re-resolves the identical raw address string -> should hit cache.
    assert resolver.cache_hits == 1, "resolver cache should persist and be hit across separate run_pipeline calls"
    print("PASS: AddressResolver cache persists across multiple run_pipeline calls")


def test_logistics_agent_wrapper_reuses_state():
    agent = LogisticsAgent()
    same_address_batch = [{"id": "Z-1", "customer_name": "A", "address": "1 Rd, Delhi, DL"}]

    agent.process(same_address_batch)
    agent.process(same_address_batch)  # identical raw address again

    assert agent.resolver.cache_hits >= 1, "LogisticsAgent should reuse its resolver across .process() calls"
    print("PASS: LogisticsAgent wrapper reuses resolver/cache across .process() calls")


if __name__ == "__main__":
    test_backward_compatible_single_call()
    test_shared_resolver_across_two_calls()
    test_logistics_agent_wrapper_reuses_state()
    print("\nALL REUSABLE-CACHE TESTS PASSED")
