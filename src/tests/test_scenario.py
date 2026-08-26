"""想定保存/加载测试。"""

from core.demo import build_demo_environment
from core.scenario import env_from_dict, env_to_dict


def test_scenario_roundtrip():
    env = build_demo_environment()
    env.time_s = 12.0
    env.add_move_order('red_ffg', 22.5, 120.6, append=True)
    env2 = env_from_dict(env_to_dict(env))
    assert set(env2.platforms) == set(env.platforms)
    assert env2.time_s == 12.0
    assert env2.waypoints['red_ffg'] == [(22.5, 120.6)]
    assert env2.platforms['blue_ew'].jammers[0].current_mode == 'spot_noise'


def test_loaded_env_can_run():
    env = build_demo_environment()
    env2 = env_from_dict(env_to_dict(env))
    env2.add_attack_order('red_ddg', 'blue_ew')
    for _ in range(200):
        env2.step(1.0)
        if any(m.result in ('hit', 'miss', 'lost_lock') for m in env2.missiles):
            break
    assert any(m.result == 'hit' for m in env2.missiles)
    assert env2.platforms['blue_ew'].alive is False
