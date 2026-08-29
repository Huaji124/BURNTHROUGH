"""从 CMO 世界数据（本地单文件或 cmo_full_by_country 国家目录）构建烧穿环境。

推荐使用 load_cmo_country_environment() 从按国家拆分目录加载。
"""

from __future__ import annotations

import json
from pathlib import Path

from core.emitter import Emitter
from core.environment import Environment, Platform
from core.jammer import Jammer
from core.receiver import Receiver

from .common import DEFAULT_CENTER, index_by_id, scatter_point
from .weapon_kind import infer_weapon_kind

SENSOR_ROLE_RADAR = set(range(2001, 2200)) | {2207, 2208, 2209}
SENSOR_ROLE_ECM = {4001, 4011, 4021, 4031, 4091}
SENSOR_ROLE_RWR = {3001}
SENSOR_ROLE_ESM = {3011, 3012, 3031, 3032, 3201, 3202}

# 只有这几类武器会接入兵推（Environment._choose_weapon 只认导弹/鱼雷）
_USABLE_KINDS = ("aam", "sam", "arm", "asm", "torpedo")

# ----------------------------------------------------------------------
# 舰载武器兜底推导
#
# CMO 导出的 loadout_weapons 基本只覆盖飞机；舰艇的导弹挂在发射装置上，
# 而发射装置到弹型的映射表并未随包导出（实测 magazine_weapons 的
# ComponentID 指向的是发射架本身，如 "Mk26 Mod 1 Twin Rail"，不是导弹）。
# 结果是舰艇一个可用武器都没有，既打不到人也防不了空。
# 这里依据发射装置型号做保守推导，让舰艇至少具备基本的防空/反舰手段。
# ----------------------------------------------------------------------
# 舰空导弹发射装置（Mk41 也可装战斧/阿斯洛克，但以防空为主业）
_SAM_LAUNCHERS = ("mk41", "mk13", "mk26", "mk10", "mk22", "sylver", "vls",
                  "mk48 vls", "mk57", "a-43", "3s90", "shtil", "riff",
                  "hq-9", "hhq-9", "vertical launch")
# 反舰导弹发射装置
_ASM_LAUNCHERS = ("mk141", "mk112", "harpoon", "exocet", "otomat", "nsr",
                  "rbs-15", "penguin", "sea eagle", "c-802", "c-801",
                  "ssm-", "kh-35", "yj-8", "yj-83", "mk60", "tomahawk")
# 鱼雷发射管
_TORPEDO_TUBES = ("533mm", "324mm", "650mm", "mk32", "mk68", "tt ", "torpedo tube")

# 箔条/诱饵发射装置
_CHAFF_LAUNCHERS = ("srboc", "mk36", "mk53", "nulka", "chaff", "decoy",
                    "dl-", "干扰弹", "诱饵")


def _infer_ship_weapons(platform: Platform, mount_names: list[str]) -> None:
    """发射装置型号 -> 兜底的舰载导弹能力（仅在完全没有挂载明细时启用）。"""
    if platform.loadout_weapons or not mount_names:
        return
    low = " | ".join(n.lower() for n in mount_names)

    def _add(name: str, kind: str, count: int) -> None:
        platform.loadout_weapons.append({"name": name, "kind": kind, "count": count})
        platform.ammo[name] = count
        platform.max_ammo[name] = count
        platform.magazine.setdefault(name, 0)

    if any(k in low for k in _SAM_LAUNCHERS):
        _add("舰空导弹", "sam", 8)
    if any(k in low for k in _ASM_LAUNCHERS):
        _add("反舰导弹", "asm", 8)
    if any(k in low for k in _TORPEDO_TUBES):
        _add("鱼雷", "torpedo", 6)


def _hz(hz_value: float | None) -> float:
    """CMO 数据库频率/带宽字段以 Hz 存储；统一返回 Hz。"""
    if not hz_value:
        return 1_000_000_000.0
    return float(hz_value)


def _role_name(role_id: int | None) -> str:
    if role_id is None:
        return "search_radar"
    if role_id <= 2100:
        return "search_radar"
    if role_id < 2200:
        return "multifunction_radar"
    return "fire_control_radar"


def _sensor_to_components(sensor: dict, platform_id: str) -> tuple[list[Emitter], list[Receiver], list[Jammer]]:
    """将一个 DataSensor 记录映射为本项目组件。"""
    emitters: list[Emitter] = []
    receivers: list[Receiver] = []
    jammers: list[Jammer] = []
    rid = sensor.get("Role")
    sid = str(sensor.get("ID"))

    if sensor.get("RadarPeakPower") or (rid in SENSOR_ROLE_RADAR):
        emitters.append(Emitter(
            id=f"cmo-world-{sid}",
            name=sensor.get("Name") or f"传感器 {sid}",
            role=_role_name(rid),
            band="X" if _hz(sensor.get("FrequencyLower")) >= 8e9 else "S",
            freq_min_hz=_hz(sensor.get("FrequencyLower")),
            freq_max_hz=_hz(sensor.get("FrequencyUpper")),
            peak_power_w=float(sensor.get("RadarPeakPower") or 100_000),
            # 数据库未导出天线增益；给雷达一个典型波束增益，保证视距内探测
            antenna_gain_db=40.0,
            prf_min_hz=float(sensor.get("RadarPRF") or 500),
            prf_max_hz=float(sensor.get("RadarPRF") or 5000),
            scan_period_s=float(sensor.get("ScanInterval") or 4.0),
            beam_width_deg=float(sensor.get("RadarHorizontalBeamwidth") or 1.5),
            frequency_agility=bool(sensor.get("FrequencyAgility") or False),
            pulse_compression_gain_db=float(sensor.get("RadarProcessingGainLoss") or 0),
            platform_id=platform_id,
        ))

    if sensor.get("ESMSensitivity") or (rid in SENSOR_ROLE_RWR | SENSOR_ROLE_ESM):
        receivers.append(Receiver(
            id=f"cmo-world-{sid}-esm",
            name=sensor.get("Name") or f"ESM {sid}",
            kind="rwr" if rid in SENSOR_ROLE_RWR else "esm",
            freq_min_hz=_hz(sensor.get("FrequencyLower")),
            freq_max_hz=_hz(sensor.get("FrequencyUpper")),
            sensitivity_dbm=float(sensor.get("ESMSensitivity") or -70),
            gain_db=0.0,
            df_accuracy_deg=float(sensor.get("DirectionFindingAccuracy") or 3),
            processing_time_s=float(sensor.get("ScanInterval") or 1.0),
            platform_id=platform_id,
        ))

    if sensor.get("ECMPeakPower") or sensor.get("ECMGain") or (rid in SENSOR_ROLE_ECM):
        jammers.append(Jammer(
            id=f"cmo-world-{sid}-ecm",
            name=sensor.get("Name") or f"ECM {sid}",
            mode=["noise", "deception"],
            band=["S", "X", "Ku"],
            freq_min_hz=_hz(sensor.get("FrequencyLower")),
            freq_max_hz=_hz(sensor.get("FrequencyUpper")),
            power_w=float(sensor.get("ECMPeakPower") or 100),
            gain_db=float(sensor.get("ECMGain") or 10),
            spot_bandwidth_hz=20_000_000,
            barrage_bandwidth_hz=500_000_000,
            current_mode="spot_noise",
            max_targets=int(sensor.get("ECMNumberOfTargets") or 4),
            techniques=["spot_noise", "barrage_noise", "rgpo", "vgpo", "false_target"],
            sector_half_deg=180.0,
            emcon_state="on",
            platform_id=platform_id,
        ))
    return emitters, receivers, jammers


def _build_from_data(data: dict, side: str = "blue",
                     limit_platforms: int | None = None,
                     center: tuple[float, float] = DEFAULT_CENTER,
                     spread_km: float = 250.0) -> Environment:
    """从 CMO 风格数据字典构建环境。

    center / spread_km 控制布点：CMO 数据库不含经纬度，所有单位需要
    由调用方指定一片海域来展开。
    """
    env = Environment()
    selected = data["platforms"]
    if limit_platforms is not None:
        selected = selected[:limit_platforms]

    mounts = data.get("mounts", {})
    loadouts = data.get("loadouts", {})
    magazines = data.get("magazines", {})
    fuel_table = data.get("fuel", {})

    # 一次性建索引，避免逐平台全表线性扫描
    mw_by_id = index_by_id(data.get("magazine_weapons", []))
    perf_by_id = index_by_id(data.get("propulsion_performance", []))

    total = len(selected)
    for idx, p in enumerate(selected):
        raw = p.get("raw", {})
        pid = f"{p['kind']}-{raw.get('ID')}"
        name = raw.get("Name") or pid

        if p["kind"] == "ship":
            kind = "ship"
            speed_kt = float(raw.get("SpeedKts") or 20)
        elif p["kind"] == "submarine":
            kind = "submarine"
            speed_kt = float(raw.get("SpeedKts") or 15)
        else:
            kind = "aircraft"
            speed_kt = float(raw.get("CruiseSpeedKts") or 400)

        lat, lon = scatter_point(idx, total, center, spread_km)

        platform = Platform(
            id=pid,
            name=name,
            side=side,
            kind=kind,
            latitude=lat,
            longitude=lon,
            altitude_ft=30_000.0 if kind == "aircraft" else 0.0,
            heading_deg=0.0,
            speed_kt=speed_kt,
            cruise_speed_kt=speed_kt,
            hp=float(raw.get("DamagePoints") or 100),
        )

        # 信号特征（RCS / 红外 / 声呐）——此前完全没读，全部走默认值
        for sig in p.get("signatures", []):
            sig_type = sig.get("Type")
            front = float(sig.get("Front") or 0)
            if sig_type in (5001, 5002):
                platform.sig_radar_db_sm = front
            elif sig_type in (4001, 4002):
                platform.sig_ir_km = front
            elif sig_type in (1001, 1002, 1003, 1004, 2001):
                platform.sig_sonar_db = max(platform.sig_sonar_db or 0.0, front)

        for sid in p.get("sensor_ids", []):
            sensor = data["sensors"].get(str(sid))
            if not sensor:
                continue
            emitters, receivers, jammers = _sensor_to_components(sensor, platform.id)
            platform.emitters.extend(emitters)
            platform.receivers.extend(receivers)
            platform.jammers.extend(jammers)

        mount_names: list[str] = []
        for wid in p.get("mount_ids", []):
            mount = mounts.get(str(wid))
            if not mount:
                continue
            mname = mount.get("Name") or ""
            platform.weapons.append(mname)
            mount_names.append(mname)
            low = mname.lower()
            if any(k in low for k in ("ciws", "phalanx", "1130", "730",
                                      "h/pj-14", "h/pj-12", "ak-630",
                                      "goalkeeper", "近程防御", "近防")):
                platform.ciws = True
                platform.ciws_hit_probability = 0.4
            if "gun" in low or low.startswith("h/pj") or "炮" in mname:
                platform.gun_range_km = max(platform.gun_range_km, 8.0)
                platform.gun_hit_probability = max(platform.gun_hit_probability, 0.15)
            # SRBOC / Nulka 等箔条诱饵发射装置（原先只认 "chaff"，
            # 漏掉了 "Mk36 SRBOC" 这类按型号命名的装置）
            if any(k in low for k in _CHAFF_LAUNCHERS):
                platform.chaff_count = max(platform.chaff_count,
                                           int(mount.get("Capacity") or 12))
            if (any(k in low for k in ("ssm", "anti-ship", "harpoon",
                                       "exocet", "tomahawk"))
                    and "ssm" not in platform.weapons):
                platform.weapons.append("ssm")

        # 挂载方案 -> 实际导弹。
        # CMO 导出里 loadout_weapons.ComponentID 指向的武器表并未随包导出
        # （实测 26624 条里只有 520 条能落到 mounts.json，且映射结果明显错位），
        # 可用信息其实就在 loadouts 记录本身：Name 即武器名，Capacity 即载弹量。
        for lid in p.get("loadout_ids", []):
            loadout = loadouts.get(str(lid))
            if not loadout:
                continue
            wname = (loadout.get("Name") or "").strip()
            # 跳过占位挂载："(Reserve [Available])"、"(Maintenance [Unavailable])"
            if not wname or wname.startswith("("):
                continue
            count = int(loadout.get("Capacity") or 0)
            if count <= 0:
                continue
            kind2 = infer_weapon_kind(wname)
            if kind2 not in _USABLE_KINDS:
                continue
            platform.loadout_weapons.append({
                "name": wname, "kind": kind2, "count": count})
            platform.ammo[wname] = max(platform.ammo.get(wname, 0), count)
            platform.max_ammo[wname] = max(platform.max_ammo.get(wname, 0), count)
            platform.magazine.setdefault(wname, 0)

        # 舰艇/潜艇没有挂载明细时，按发射装置型号推导基本武器能力
        if kind in ("ship", "submarine"):
            _infer_ship_weapons(platform, mount_names)

        # 弹药库：能解析出武器名的才计入，解析不出就跳过而不是乱配
        for mid in p.get("magazine_ids", []):
            mag = magazines.get(str(mid))
            if not mag:
                continue
            cap = int(mag.get("Capacity") or 0)
            if cap <= 0:
                continue
            for mw in mw_by_id.get(mid, []):
                comp = mounts.get(str(mw.get("ComponentID")))
                if not comp:
                    continue
                wname = (comp.get("Name") or "").strip()
                if not wname:
                    continue
                platform.magazine[wname] = platform.magazine.get(wname, 0) + cap
                platform.max_ammo.setdefault(wname, max(1, cap))

        # 推进性能 -> 最大速度 / 耗油率
        max_speed = 0.0
        for prid in p.get("propulsion_ids", []):
            for perf in perf_by_id.get(prid, []):
                max_speed = max(max_speed, float(perf.get("Speed") or 0))
                cons = float(perf.get("Consumption") or 0)
                if cons > 0:
                    platform.fuel_consumption_kg_per_h = max(
                        platform.fuel_consumption_kg_per_h, cons)
        if max_speed > 0:
            platform.max_speed_kt = max_speed
            platform.speed_kt = min(platform.speed_kt, max_speed)
            platform.cruise_speed_kt = min(platform.cruise_speed_kt, max_speed)

        fuel_cap = 0.0
        for fid in p.get("fuel_ids", []):
            f = fuel_table.get(str(fid))
            if f:
                fuel_cap += float(f.get("Capacity") or 0)
        if fuel_cap > 0:
            platform.fuel_capacity_kg = fuel_cap
            platform.fuel_kg = fuel_cap

        platform.extra_loadouts = {
            "operator_country": raw.get("OperatorCountry"),
            "year_commissioned": raw.get("YearCommissioned"),
        }
        env.add_platform(platform)

    env.data_source = str(data.get("source", ""))
    return env


def load_cmo_world_environment(path: str | Path = "data/cmo_world_full.json",
                               side: str = "blue",
                               limit_platforms: int | None = None) -> Environment:
    """加载 CMO 世界数据合并 JSON（老格式）。"""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return _build_from_data(data, side=side, limit_platforms=limit_platforms)


def _load_json(base: Path, name: str, default):
    """读取可选 JSON 文件，缺失时返回默认值。"""
    f = base / name
    if not f.exists():
        return default
    return json.loads(f.read_text(encoding="utf-8"))


def load_cmo_country_environment(country_dir: str | Path, side: str = "blue",
                                 limit_platforms: int | None = None,
                                 center: tuple[float, float] = DEFAULT_CENTER,
                                 spread_km: float = 250.0) -> Environment:
    """从 cmo_full_by_country/<slug>/ 目录加载一个国家。

    目录需包含 platforms.json / sensors.json / mounts.json；
    loadouts / magazines / propulsion_performance / fuel 等为可选，
    缺失时对应能力退化为默认值。

    center / spread_km：CMO 数据库不含经纬度，展开海域由调用方指定。
    """
    base = Path(country_dir)
    data = {
        "source": str(base),
        "platforms": json.loads((base / "platforms.json").read_text(encoding="utf-8")),
        "sensors": json.loads((base / "sensors.json").read_text(encoding="utf-8")),
        "mounts": json.loads((base / "mounts.json").read_text(encoding="utf-8")),
        "loadouts": _load_json(base, "loadouts.json", {}),
        "loadout_weapons": _load_json(base, "loadout_weapons.json", []),
        "magazines": _load_json(base, "magazines.json", {}),
        "magazine_weapons": _load_json(base, "magazine_weapons.json", []),
        "propulsion_performance": _load_json(base, "propulsion_performance.json", []),
        "fuel": _load_json(base, "fuel.json", {}),
    }
    return _build_from_data(data, side=side, limit_platforms=limit_platforms,
                            center=center, spread_km=spread_km)
