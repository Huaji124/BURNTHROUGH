"""模拟环境：承载平台、辐射源、干扰机，并计算传播链路。"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .emitter import Emitter
from .jammer import Jammer
from .receiver import Receiver
from . import propagation


@dataclass
class Platform:
    id: str
    name: str
    side: str                         # blue / red / neutral
    kind: str                         # ship / aircraft / submarine
    latitude: float
    longitude: float
    altitude_ft: float = 0.0          # 飞机高度；舰船/地面为 0 或天线高度
    heading_deg: float = 0.0
    speed_kt: float = 0.0
    emitters: list[Emitter] = field(default_factory=list)
    receivers: list[Receiver] = field(default_factory=list)
    jammers: list[Jammer] = field(default_factory=list)


@dataclass
class Environment:
    """静态射频沙盘环境（Phase 1）。

    不包含时间推进，只负责：
    - 注册平台/发射机/接收机/干扰机
    - 计算两两之间的传播、J/S、烧穿距离、ESM 截获
    """

    platforms: dict[str, Platform] = field(default_factory=dict)

    def add_platform(self, platform: Platform) -> None:
        self.platforms[platform.id] = platform

    def all_emitters(self) -> list[Emitter]:
        result = []
        for p in self.platforms.values():
            result.extend(p.emitters)
        return result

    def all_jammers(self) -> list[Jammer]:
        result = []
        for p in self.platforms.values():
            result.extend(p.jammers)
        return result

    def all_receivers(self) -> list[Receiver]:
        result = []
        for p in self.platforms.values():
            result.extend(p.receivers)
        return result

    def active_emitters(self) -> list[Emitter]:
        return [e for e in self.all_emitters() if e.is_emitting]

    def active_jammers(self) -> list[Jammer]:
        return [j for j in self.all_jammers() if j.is_jamming]

    def evaluate_radar_with_jamming(self, emitter: Emitter, jammer: Jammer | None,
                                    rcs_m2: float = 1000.0,
                                    bandwidth_hz: float = 1e6,
                                    noise_figure: float = 5.0,
                                    loss: float = 6.0,
                                    snr_min_db: float = 13.0) -> dict:
        """计算某部雷达在有/无指定干扰机时的探测与烧穿距离。

        返回 dict 供 UI/命令行使用。
        """
        snr_min = 10.0 ** (snr_min_db / 10.0)
        wavelength = propagation.wavelength_m(emitter.center_freq_hz)
        r_max = propagation.radar_max_range_m(
            emitter.peak_power_w, emitter.gain_linear, emitter.gain_linear,
            rcs_m2, wavelength, bandwidth_hz, noise_figure, loss, snr_min,
        )
        if jammer is None:
            return {
                "emitter": emitter.id,
                "jammer": None,
                "detection_range_km": r_max / 1000.0,
                "burn_through_km": None,
                "js_at_burnthrough": None,
            }

        # 远距离支援干扰模型（第 1 阶段使用）
        rj = _distance_m(self._platform_of(jammer), self._platform_of(emitter))
        r_bt = propagation.burn_through_standoff_m(
            emitter.peak_power_w, emitter.gain_linear, rcs_m2,
            jammer.power_w, jammer.gain_linear, bandwidth_hz, jammer.bandwidth_hz,
            rj,
        )
        effective_range = min(r_max, r_bt)
        return {
            "emitter": emitter.id,
            "jammer": jammer.id,
            "jammer_range_km": rj / 1000.0,
            "detection_range_km": effective_range / 1000.0,
            "un-jammed_range_km": r_max / 1000.0,
            "burn_through_km": r_bt / 1000.0,
        }

    def _platform_of(self, component) -> Platform | None:
        pid = getattr(component, "platform_id", None)
        return self.platforms.get(pid)

    def find_emitter_platform(self, emitter: Emitter) -> Platform | None:
        return self._platform_of(emitter)

    def find_jammer_platform(self, jammer: Jammer) -> Platform | None:
        return self._platform_of(jammer)

    def esm_intercept(self, esm: Receiver, emitter: Emitter) -> dict:
        """计算 ESM 对某辐射源的截获结果。"""
        esm_platform = self._platform_of(esm)
        emitter_platform = self._platform_of(emitter)
        if esm_platform is None or emitter_platform is None:
            return {"intercepted": False, "reason": "platform_not_found"}

        r_m = _distance_m(esm_platform, emitter_platform)
        horizon_nm = 1.23 * (math.sqrt(max(esm_platform.altitude_ft, 0.0)) +
                             math.sqrt(max(emitter_platform.altitude_ft, 0.0)))
        horizon_m = horizon_nm * 1852.0

        if r_m > horizon_m:
            return {"intercepted": False, "reason": "below_horizon",
                    "range_km": r_m / 1000.0, "horizon_km": horizon_m / 1000.0}

        wavelength = propagation.wavelength_m(emitter.center_freq_hz)
        if not esm.covers_frequency(emitter.center_freq_hz):
            return {"intercepted": False, "reason": "out_of_band",
                    "range_km": r_m / 1000.0}

        power_dbm = propagation.esm_received_power_dbm(
            emitter.peak_power_w, emitter.gain_linear, esm.gain_linear,
            wavelength, r_m,
        )
        if power_dbm < esm.sensitivity_dbm:
            return {"intercepted": False, "reason": "below_sensitivity",
                    "range_km": r_m / 1000.0, "power_dbm": power_dbm}

        # 识别判定：参数库命中
        known = emitter.id in esm.param_library
        return {
            "intercepted": True,
            "range_km": r_m / 1000.0,
            "power_dbm": power_dbm,
            "bearing_deg": _bearing_deg(esm_platform, emitter_platform),
            "emitter_id": emitter.id,
            "identified": known,
            "confidence": 0.9 if known else 0.3,
        }


def _distance_m(a: Platform, b: Platform) -> float:
    """平台间大圆距离（米）。"""
    from common.geo import haversine_nm
    return haversine_nm(a.latitude, a.longitude, b.latitude, b.longitude) * 1852.0


def _bearing_deg(a: Platform, b: Platform) -> float:
    from common.geo import initial_bearing_deg
    return initial_bearing_deg(a.latitude, a.longitude, b.latitude, b.longitude)
