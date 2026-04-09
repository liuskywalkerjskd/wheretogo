from rmuc_analyzer.engine import compute_national_quotas, estimate_resurrection_quotas


def test_estimate_resurrection_quota_sum_and_bounds():
    national = compute_national_quotas({"南部": 5, "东部": 7, "北部": 3})
    region_counts = {"南部": 22, "东部": 26, "北部": 17}

    resurrection = estimate_resurrection_quotas(national, region_counts)

    assert sum(resurrection.values()) == 16

    for region, value in resurrection.items():
        assert value >= 0
        total = national.items[region].total_quota + value
        assert total <= 16
        assert total >= 8
