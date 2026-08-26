"""地理计算测试。"""

import math

from common.geo import haversine_nm, initial_bearing_deg, radar_horizon_nm


def test_haversine_known_distance():
    # 赤道上 1 度经度约 60 海里
    d = haversine_nm(0, 0, 0, 1)
    assert math.isclose(d, 60.0, rel_tol=0.05)


def test_initial_bearing_due_east():
    b = initial_bearing_deg(0, 0, 0, 1)
    assert math.isclose(b, 90.0, rel_tol=0.01)


def test_radar_horizon():
    # 1 英尺天线对海面目标视距约 1.23 海里
    h = radar_horizon_nm(1, 0)
    assert math.isclose(h, 1.23, rel_tol=0.01)


def test_radar_horizon_two_heights():
    # 100 英尺对 100 英尺：1.23 * (10 + 10) = 24.6 海里
    h = radar_horizon_nm(100, 100)
    assert math.isclose(h, 24.6, rel_tol=0.01)
