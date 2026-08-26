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


def test_move_order_restores_speed_and_stops_at_destination():
    env = build_demo_environment()
    ddg = env.platforms['red_ddg']
    env.add_move_order('red_ddg', 22.1, 120.0, append=False)
    assert ddg.speed_kt == 20.0
    env.step_motion(dt_s=3600)  # 20 节 x 1 小时 = 20 海里 > 6 海里
    assert ddg.latitude == 22.1 and ddg.longitude == 120.0
    assert ddg.speed_kt == 0.0
    assert 'red_ddg' not in env.waypoints


def test_aircraft_loiters_after_final_waypoint():
    env = build_demo_environment()
    blue = env.platforms['blue_ew']
    # 给飞机设一个很近的航路点
    env.add_move_order('blue_ew', blue.latitude, blue.longitude + 0.05, append=False)
    env.step_motion(dt_s=3600)
    assert 'blue_ew' not in env.waypoints
    assert blue.orbit_center_lat is not None
    assert blue.orbit_radius_km is not None
    assert blue.speed_kt == blue.cruise_speed_kt


def test_arm_hits_emitting_target():
    env = build_demo_environment()
    env.add_attack_order('red_ddg', 'blue_ew')
    for _ in range(200):
        env.step(1.0)
        if any(m.result in ('hit', 'miss', 'lost_lock') for m in env.missiles):
            break
    assert env.platforms['blue_ew'].alive is False
    assert any(m.result == 'hit' for m in env.missiles)


def test_arm_loses_lock_after_jammer_off():
    env = build_demo_environment()
    env.add_attack_order('red_ddg', 'blue_ew')
    env.step(1.0)
    for jammer in env.all_jammers():
        jammer.emcon_state = 'off'
    for _ in range(30):
        env.step(1.0)
        if any(m.result in ('lost_lock', 'miss', 'hit') for m in env.missiles):
            break
    assert env.platforms['blue_ew'].alive is True
    assert any(m.result == 'lost_lock' for m in env.missiles)


def test_jammer_mode_bandwidth():
    env = build_demo_environment()
    jammer = env.all_jammers()[0]
    assert jammer.current_mode == 'spot_noise'
    spot_bw = jammer.bandwidth_hz
    jammer.set_mode('barrage_noise')
    assert jammer.bandwidth_hz > spot_bw


def test_deception_creates_false_targets():
    env = build_demo_environment()
    env.rng.seed(42)
    for jammer in env.all_jammers():
        jammer.set_technique("false_target")
    for _ in range(30):
        env.step(dt_s=1.0)
    false_count = sum(len(v) for v in env.false_contacts.values())
    assert false_count > 0


def test_eccm_reduces_deception_success_probability():
    from core.emitter import Emitter
    emitter = Emitter(
        id="test", name="test", role="search_radar", band="S",
        freq_min_hz=2e9, freq_max_hz=4e9, peak_power_w=1e6,
        antenna_gain_db=40,
    )
    # 建立临时环境
    env = build_demo_environment()
    p_base = env._deception_success_probability(emitter)
    emitter.frequency_agility = True
    emitter.sidelobe_cancellation = True
    emitter.pulse_compression_gain_db = 20.0
    p_eccm = env._deception_success_probability(emitter)
    assert p_eccm < p_base


def test_missile_can_be_decoyed_by_false_target():
    env = build_demo_environment()
    blue = env.platforms["blue_ew"]
    jammer = blue.jammers[0]
    jammer.set_technique("false_target")
    # 先产生一个假目标
    env.rng.seed(1)
    for _ in range(30):
        env.step(dt_s=1.0)
    assert env.false_contacts

    env.add_attack_order("red_ddg", "blue_ew")
    env.process_attack_orders()
    missile = env.missiles[0]
    # 强制随机数命中诱骗判定
    env.rng.random = lambda: 0.0  # type: ignore[method-assign]
    decoyed = env._try_decoy_missile(missile, blue)
    assert decoyed
    assert missile.decoyed
    assert (missile.last_locked_lat, missile.last_locked_lon) != (blue.latitude, blue.longitude)
