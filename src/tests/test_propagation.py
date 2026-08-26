"""电磁传播公式测试。"""

import math

from core import propagation


def test_radar_max_range_order_of_magnitude():
    # 1 MW, 40 dB 增益, RCS 1000 m², 10 GHz 雷达 -> 数百 km 量级
    gt = 10 ** (40 / 10)
    lam = propagation.wavelength_m(10e9)
    r = propagation.radar_max_range_m(1e6, gt, gt, 1000.0, lam,
                                      1e6, 5.0, 6.0, 10 ** (13 / 10))
    assert 300_000 < r < 500_000  # 300~500 km


def test_burn_through_self_screen_reduces_range():
    gt = 10 ** (40 / 10)
    gj = 10 ** (20 / 10)
    r_bt = propagation.burn_through_self_screen_m(1e6, gt, 1000.0, 100.0, gj,
                                                  1e6, 20e6)
    assert 30_000 < r_bt < 60_000  # 约 40 km


def test_js_self_screen_increases_with_range():
    gt = 10 ** (40 / 10)
    gj = 10 ** (20 / 10)
    js_near = propagation.js_self_screen(100.0, gj, 20e3, 1e6, gt, 1000.0, 1e6, 20e6)
    js_far = propagation.js_self_screen(100.0, gj, 100e3, 1e6, gt, 1000.0, 1e6, 20e6)
    assert js_far > js_near


def test_esm_received_power_decreases_with_range():
    gt = 10 ** (40 / 10)
    lam = propagation.wavelength_m(10e9)
    p1 = propagation.esm_received_power_dbm(1e6, gt, 1.0, lam, 100e3)
    p2 = propagation.esm_received_power_dbm(1e6, gt, 1.0, lam, 200e3)
    assert p1 > p2
