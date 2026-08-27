"""电磁传播与雷达/干扰方程。

内部计算统一使用：
- 功率：W
- 距离：米
- 增益：线性倍数值
- 波长：米
- 带宽：Hz
- RCS：平方米
"""

from __future__ import annotations

import math

BOLTZMANN = 1.380649e-23  # k, J/K
REF_TEMP = 290.0          # T0, K
C_LIGHT = 299_792_458.0   # m/s


def wavelength_m(freq_hz: float) -> float:
    return C_LIGHT / freq_hz


def radar_max_range_m(peak_power_w: float, gain_tx: float, gain_rx: float,
                      rcs_m2: float, wavelength: float, bandwidth_hz: float,
                      noise_figure: float, loss: float, snr_min: float) -> float:
    """无干扰雷达最大探测距离（米）。

    Rmax = [ Pt*Gt*Gr*σ*λ^2 / ((4π)^3*k*T0*B*F*L*SNRmin) ]^(1/4)
    """
    denom = ((4 * math.pi) ** 3) * BOLTZMANN * REF_TEMP * bandwidth_hz * noise_figure * loss * snr_min
    return (peak_power_w * gain_tx * gain_rx * rcs_m2 * wavelength ** 2 / denom) ** 0.25


def js_self_screen(jammer_power_w: float, jammer_gain: float, range_m: float,
                   radar_power_w: float, radar_gain: float, rcs_m2: float,
                   radar_bw_hz: float, jammer_bw_hz: float) -> float:
    """自卫干扰（SSJ）信干比 J/S（线性）。

    干扰机位于目标平台上，干扰功率单程到达雷达；
    目标回波为双程。J/S = (Pj*Gj*4π*R^2) / (Pt*Gt*σ) * (Br/Bj)
    """
    return (jammer_power_w * jammer_gain * 4.0 * math.pi * range_m ** 2) / \
           (radar_power_w * radar_gain * rcs_m2) * (radar_bw_hz / jammer_bw_hz)


def js_standoff(jammer_power_w: float, jammer_gain: float, jammer_range_m: float,
                target_range_m: float, radar_power_w: float, radar_gain: float,
                rcs_m2: float, radar_bw_hz: float, jammer_bw_hz: float) -> float:
    """远距离支援干扰（SOJ）信干比 J/S（线性）。

    干扰机与雷达距离 Rj，目标与雷达距离 R。
    J/S = (Pj*Gj*4π*R^4) / (Pt*Gt*σ*Rj^2) * (Br/Bj)
    """
    return (jammer_power_w * jammer_gain * 4.0 * math.pi * target_range_m ** 4) / \
           (radar_power_w * radar_gain * rcs_m2 * jammer_range_m ** 2) * \
           (radar_bw_hz / jammer_bw_hz)


def burn_through_self_screen_m(radar_power_w: float, radar_gain: float, rcs_m2: float,
                               jammer_power_w: float, jammer_gain: float,
                               radar_bw_hz: float, jammer_bw_hz: float,
                               js_threshold: float = 1.0) -> float:
    """自卫干扰烧穿距离（米）。令 J/S = threshold。"""
    return math.sqrt(
        (radar_power_w * radar_gain * rcs_m2 * jammer_bw_hz) /
        (jammer_power_w * jammer_gain * 4.0 * math.pi * radar_bw_hz) * js_threshold
    )


def burn_through_standoff_m(radar_power_w: float, radar_gain: float, rcs_m2: float,
                            jammer_power_w: float, jammer_gain: float,
                            radar_bw_hz: float, jammer_bw_hz: float,
                            jammer_range_m: float, js_threshold: float = 1.0) -> float:
    """远距离支援干扰烧穿距离（米）。"""
    return (
        (radar_power_w * radar_gain * rcs_m2 * jammer_range_m ** 2 * jammer_bw_hz) /
        (jammer_power_w * jammer_gain * 4.0 * math.pi * radar_bw_hz) * js_threshold
    ) ** 0.25


def radar_detection_range_with_soj_m(radar_power_w: float, radar_gain: float,
                                     rcs_m2: float, wavelength: float,
                                     bandwidth_hz: float, noise_figure: float,
                                     loss: float, snr_min: float,
                                     jammer_power_w: float, jammer_gain: float,
                                     jammer_bw_hz: float, jammer_range_m: float) -> float:
    """考虑远距干扰后的雷达有效探测距离（米）。

    采用简化模型：当 J/S 达到检测门限时对应烧穿距离，
    与无干扰最大探测距离取较小值。
    该函数用于第 1 阶段快速计算，后续可替换为逐点 SNR+SJR 积分。
    """
    r_max = radar_max_range_m(radar_power_w, radar_gain, radar_gain, rcs_m2,
                              wavelength, bandwidth_hz, noise_figure, loss, snr_min)
    if jammer_power_w <= 0 or jammer_range_m <= 0:
        return r_max
    r_bt = burn_through_standoff_m(radar_power_w, radar_gain, rcs_m2,
                                   jammer_power_w, jammer_gain,
                                   bandwidth_hz, jammer_bw_hz, jammer_range_m)
    return min(r_max, r_bt)


def esm_received_power_w(emitter_power_w: float, emitter_gain: float,
                         esm_gain: float, wavelength: float, range_m: float) -> float:
    """ESM 单程截获接收功率（W）。

    Pr = Pt*Gt*Gr*λ^2 / ((4π)^2*R^2)
    """
    return (emitter_power_w * emitter_gain * esm_gain * wavelength ** 2) / \
           ((4.0 * math.pi * range_m) ** 2)


def esm_received_power_dbm(emitter_power_w: float, emitter_gain: float,
                           esm_gain: float, wavelength: float, range_m: float) -> float:
    """ESM 接收功率（dBm）。"""
    w = esm_received_power_w(emitter_power_w, emitter_gain, esm_gain, wavelength, range_m)
    return 10.0 * math.log10(w * 1000.0) if w > 0 else -math.inf


def esm_max_range_m(emitter_power_w: float, emitter_gain: float,
                    esm_gain: float, wavelength: float, sensitivity_w: float) -> float:
    """ESM 对给定辐射源的最大截获距离（米）。

    sensitivity_w 为接收机灵敏度（瓦）。Rmax = sqrt(Pt*Gt*Gr*λ^2 / ((4π)^2*Smin))
    """
    return math.sqrt(
        (emitter_power_w * emitter_gain * esm_gain * wavelength ** 2) /
        ((4.0 * math.pi) ** 2 * sensitivity_w)
    )


def free_space_loss_db(range_km: float, freq_mhz: float) -> float:
    """EW101 扩展损耗公式 Ls = 32.4 + 20log10(d) + 20log10(f)。"""
    if range_km <= 0 or freq_mhz <= 0:
        return 0.0
    return 32.4 + 20.0 * math.log10(range_km) + 20.0 * math.log10(freq_mhz)


def atmospheric_loss_db(freq_hz: float, range_km: float) -> float:
    """简化大气损耗（dB/km 按频段近似）。"""
    freq_ghz = freq_hz / 1e9
    loss_per_km = 0.0
    if freq_ghz > 30:
        loss_per_km = 0.3
    elif freq_ghz > 15:
        loss_per_km = 0.1
    elif freq_ghz > 10:
        loss_per_km = 0.03
    elif freq_ghz > 6:
        loss_per_km = 0.01
    return loss_per_km * max(range_km, 0.0)


def one_way_link_power_dbm(pt_dbm: float, gt_db: float, gr_db: float,
                           range_km: float, freq_mhz: float,
                           atm_loss_db: float = 0.0) -> float:
    """EW101 单向链路方程接收功率（dBm）。"""
    return pt_dbm + gt_db - free_space_loss_db(range_km, freq_mhz) - atm_loss_db + gr_db
