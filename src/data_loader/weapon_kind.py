"""武器类型推断（各数据源加载器共用）。

背景：原先只有 china_loader 内部的一套规则，仅识别中国装备命名
（PL- / YJ- / HQ-）。CMO 世界数据里的 NATO 命名（AIM- / AGM- / RIM- /
GBU-）会被一律判成 "weapon"，而 Environment._choose_weapon() 只认
aam / sam / arm / asm 四类，结果是装载美系装备后一架飞机都选不到弹。

匹配规则：所有关键字都要求出现在"词首"（串首或非字母数字之后）。
早先版本用朴素子串匹配，"tor " 会命中 rapTOR / gaTOR / penetraTOR，
"sm-1" 会命中 aSM-135a，把集束炸弹和空地弹误判成舰空弹。
"""

from __future__ import annotations

# 反辐射导弹：必须排在反舰/空地之前判断，否则 AGM-88 会被归入 asm
_ARM_TOKENS = (
    "agm-88", "agm-78", "agm-122", "agm-136",
    "alarm", "martel", "as-11", "as-17",
    "kh-31p", "kh-58", "kh-25mp", "kh-27",
    "ld-10", "yj-91", "cm-102", "mar-1",
)

_AAM_TOKENS = (
    "aim-", "pl-", "aa-1", "aa-2", "aa-8", "aa-10", "aa-11", "aa-12",
    "r-27", "r-73", "r-77", "r-60", "r-3", "r-13",
    "sidewinder", "sparrow", "amraam", "asraam", "meteor", "mica",
    "iris-t", "python", "derby", "sd-10", "pl-12", "pl-15", "pl-10",
)

# 注意：不写裸 "sa-"，否则会误伤大量无关名称
_SAM_TOKENS = (
    "rim-", "hq-", "hhq-", "sa-n",
    "sa-2", "sa-3", "sa-5", "sa-6", "sa-8", "sa-10", "sa-11", "sa-12",
    "sa-15", "sa-17", "sa-19", "sa-20", "sa-21", "sa-22", "sa-23", "sa-24",
    "sm-1", "sm-2", "sm-3", "sm-6",
    "standard missile", "sea sparrow", "essm", "aster",
    "s-300", "s-400", "s-350", "s-75", "s-125", "s-200",
    "9k33", "9k330", "9k331", "9k332", "tor-m", "tor m1", "buk", "pantsir",
)

_ASM_TOKENS = (
    "agm-84", "agm-119", "agm-158", "rbs-15", "nsr", "otomat",
    "exocet", "harpoon", "anti-ship", "kh-35", "kh-59", "kh-22", "ss-n",
    "yj-", "c-80", "c-60", "c-70", "yh-", "penguin", "sea eagle",
)

_TORPEDO_TOKENS = (
    "torpedo", "鱼雷", "mk46", "mk48", "mk50", "mk54", "mk-46", "mk-48",
    "yu-", "set-", "dm2a", "black shark", "spearfish", "f17", "tp-6",
)

_BOMB_TOKENS = (
    "gbu-", "mk81", "mk82", "mk83", "mk84", "mk20", "cbu-",
    "paveway", "jdamm", "ls-", "ft-", "kab-", "fab-", "betab",
)

# 各组按顺序判定，命中即返回
_GROUPS = (
    ("arm", _ARM_TOKENS),
    ("torpedo", _TORPEDO_TOKENS),
    ("aam", _AAM_TOKENS),
    ("sam", _SAM_TOKENS),
    ("asm", _ASM_TOKENS),
    ("bomb", _BOMB_TOKENS),
)


def _matches_at_word_start(name: str, token: str) -> bool:
    """判断 token 是否出现在 name 的词首位置（串首或非字母数字之后）。"""
    start = name.find(token)
    while start != -1:
        if start == 0 or not name[start - 1].isalnum():
            return True
        start = name.find(token, start + 1)
    return False


def infer_weapon_kind(name: str) -> str:
    """根据武器名称推断类型。

    返回 aam / sam / arm / asm / torpedo / bomb / weapon。
    只有前五类会被 Environment._choose_weapon() 采用。
    """
    n = (name or "").lower()
    for kind, tokens in _GROUPS:
        if any(_matches_at_word_start(n, t) for t in tokens):
            return kind
    return "weapon"
