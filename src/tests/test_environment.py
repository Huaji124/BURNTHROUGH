"""Phase 2 环境与 ESM 截获测试。"""

from core.demo import build_demo_environment
from core.environment import triangulate_bearings


def test_triangulate_bearings_basic():
    # 两条垂直测向线：交点应接近参考点
    # 平台1 (0,0) 方位 90° -> 向东；平台2 (1,1) 方位 270° -> 向西? 实际方向向量相交
    lat, lon = triangulate_bearings([(0.0, 0.0, 90.0), (1.0, 1.0, 225.0)])
    assert lat is not None and lon is not None
    # 交点在参考点附近（此处为原点附近）
    assert abs(lat) < 1.0
    assert abs(lon) < 1.0


def test_esm_detects_active_jammer_and_crossfixes():
    env = build_demo_environment()
    for _ in range(20):
        env.step(dt_s=1.0)
    assert "red_ddg" in env.contacts
    assert "ecm_pod_rkz" in env.contacts["red_ddg"]
    contact = env.contacts["red_ddg"]["ecm_pod_rkz"]
    assert contact.bearing_deg is not None
    assert contact.latitude is not None and contact.longitude is not None


def test_jammer_off_contact_goes_memory():
    env = build_demo_environment()
    for _ in range(20):
        env.step(dt_s=1.0)
    for jammer in env.all_jammers():
        jammer.emcon_state = "off"
    for _ in range(int(env.memory_ttl_s) + 5):
        env.step(dt_s=1.0)
    contact = env.contacts["red_ddg"]["ecm_pod_rkz"]
    assert contact.is_memory
