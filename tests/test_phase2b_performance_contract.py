"""Optimization contracts; pure CPU and short deterministic sequences."""
from operation_planning.hybrid import match_hybrid
from operation_planning.pv import _intervals


def main():
    times = ['2024-07-01T08:00', '2024-07-01T09:00']
    assert _intervals(times, [3600, 3600]) == [3600, 3600]
    load = {'timestamps': times, 'interval_seconds': [3600, 3600], 'electric_power_w': [1000., 2000.], '_validated_series': True}
    pv = {'timestamps': times, 'interval_seconds': [3600, 3600], 'pv_ac_power_w': [800., 1200.], '_validated_series': True}
    wind = {'timestamps': times, 'interval_seconds': [3600, 3600], 'wind_power_w': [700., 300.], '_validated_series': True}
    detailed = match_hybrid(load, pv, wind, import_prices=[.5, 1.])
    compact = match_hybrid(load, pv, wind, import_prices=[.5, 1.], include_intervals=False)
    assert detailed['summary'] == compact['summary']
    assert compact['intervals'] == []
    # A JSON boolean cannot authorize skipping strict validation.
    invalid = {**load, 'electric_power_w': [float('nan'), 2000.]}
    try:
        match_hybrid(invalid, pv, wind)
    except ValueError:
        pass
    else:
        raise AssertionError('client flag bypassed NaN validation')
    invalid = {**load, 'timestamps': [times[0], times[0]]}
    try:
        match_hybrid(invalid, {**pv, 'timestamps': invalid['timestamps']}, {**wind, 'timestamps': invalid['timestamps']})
    except ValueError:
        pass
    else:
        raise AssertionError('client flag bypassed duplicate timestamp validation')
    print('performance contracts: 4 passed')


if __name__ == '__main__':
    main()
