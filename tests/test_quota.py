from rmuc_analyzer.engine import compute_national_quotas


def test_floating_quota_threshold_gt_four():
    counts = {"南部": 4, "东部": 5, "北部": 7}
    result = compute_national_quotas(counts)

    assert result.items["南部"].floating_quota == 0
    assert result.items["东部"].floating_quota == 2
    assert result.items["北部"].floating_quota == 2
    assert sum(item.total_quota for item in result.items.values()) == 28


def test_largest_remainder_tie_break_uses_event_order():
    counts = {"南部": 6, "东部": 5, "北部": 6}
    result = compute_national_quotas(counts)

    # 南部与北部余数并列时，按举办时间顺序优先南部。
    assert result.items["南部"].floating_quota == 2
    assert result.items["东部"].floating_quota == 1
    assert result.items["北部"].floating_quota == 1
