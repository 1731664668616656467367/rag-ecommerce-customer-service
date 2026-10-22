"""对话引导规则（问候 / 身份 / 感谢 / 告别 / 人工客服请求）。

为什么单独做一个模块，而不是把引导语写进知识库文档？
    知识库是“可被检索的资料”，回答方式是“摘录原文”。而问候语需要的是“精确命中 +
    固定话术 + 附带快捷按钮”，两者语义完全不同。混在一起会带来两个问题：
      1. 用户问“退款政策”，检索可能把“你好，欢迎咨询”那段当资料捞出来；
      2. 问候语被改写/摘录后语气会走样。
    所以引导类内容走独立规则，命中就短路，不进入检索。

最关键的判断原则：**宁可漏判，也不要误判**。
    “你好，我想知道退款流程”必须以“你好”开头，但它是个业务问题。
    所以判据不是“含有问候词”，而是“把问候词、客套词、语气词全部剥掉之后，
    还剩下什么”。只剩空壳才算纯问候，剩下任何实义内容就交给正常业务链路。

这套规则全程本地执行，不调用任何模型，纯知识库模式下零外联。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------- 快捷问题 ----------------

# 每个入口都必须能通向系统真实具备的能力（知识库检索 / 能力说明），
# 不允许出现“点了之后只能编一段话”的入口。
#
# query 的措辞不是随便写的：每一条都在当前知识库上实测过能命中对应文档。
# 例如最早写的“物流配送需要多久？”实际检索不到（覆盖率被“需要”“多久”这些
# 文档里不存在的二元组稀释到阈值以下），换成“同城配送一般几天能到？”才稳定命中
# 02-配送与物流时效。**没有靠调低全局阈值来凑**，那样会连带放过无关问题。
DEFAULT_SUGGESTIONS: tuple[dict, ...] = (
    {
        "label": "物流配送",
        "query": "同城配送一般几天能到？",
        "description": "发货时间与配送时效",
    },
    {
        "label": "退款政策",
        "query": "退款政策",
        "description": "退款条件与到账时间",
    },
    {
        "label": "退换货",
        "query": "退换货政策是怎样的？",
        "description": "七天无理由与质量问题",
    },
    {
        "label": "售后服务",
        "query": "如何申请售后服务？",
        "description": "保修与维修流程",
    },
    {
        "label": "订单查询",
        "query": "我想查询订单",
        "description": "订单状态与地址修改",
    },
    {
        "label": "联系人工客服",
        "query": "我想联系人工客服",
        "description": "本服务未接入在线人工客服",
    },
)


def default_suggestions() -> list[dict]:
    """返回快捷问题的副本，避免调用方改到模块级常量。"""
    return [dict(item) for item in DEFAULT_SUGGESTIONS]


# ---------------- 话术 ----------------

GREETING_TEXT = (
    "您好！欢迎使用智能客服助手。我可以帮您了解物流配送、退款政策、退换货和售后服务等信息。"
    "您可以直接输入问题，也可以点击下方的快捷问题开始咨询。"
)

IDENTITY_TEXT = (
    "我是智能客服助手，主要根据当前知识库中的信息回答电商相关问题，"
    "包括物流配送、退款规则、退换货和售后服务。"
    "如果暂时没有找到可靠答案，我会明确告知您。"
)

THANKS_TEXT = "不客气。如果还有其他物流、退款、退换货或售后的问题，随时告诉我。"

FAREWELL_TEXT = "再见，祝您购物愉快。后续遇到订单、物流或售后问题，欢迎随时回来咨询。"

# 不编造电话、链接、工单号：系统确实没有接在线人工客服
HUMAN_SERVICE_TEXT = (
    "本服务暂未接入在线人工客服，无法直接为您转接，也没有可提供的电话或链接。"
    "您可以继续描述遇到的问题，我会根据知识库给出说明；"
    "如果确实需要人工处理，建议通过购买平台的官方客服入口联系。"
)

OFF_SCOPE_TEXT = (
    "抱歉，我目前主要提供电商相关的客服咨询，暂时无法可靠回答这个问题。"
    "您可以选择下方的常见问题，或直接描述您遇到的订单、物流、退款或售后问题。"
)

UNINTELLIGIBLE_TEXT = (
    "抱歉，我暂时没有理解您的意思。请换一种方式描述您的问题，也可以点击下方的常见问题。"
)

TEXTS: dict[str, str] = {
    "greeting": GREETING_TEXT,
    "identity": IDENTITY_TEXT,
    "thanks": THANKS_TEXT,
    "farewell": FAREWELL_TEXT,
    "human_service": HUMAN_SERVICE_TEXT,
    "fallback": OFF_SCOPE_TEXT,
    "unclear": UNINTELLIGIBLE_TEXT,
}

# 哪一种引导回复要附带快捷问题（问候/身份/致谢/告别/超范围/没听懂都给）
WITH_SUGGESTIONS = frozenset(
    {"greeting", "identity", "thanks", "farewell", "human_service", "fallback", "unclear"}
)

# ---------------- 词表 ----------------

# 顺序即优先级：同一句话里既说“谢谢”又说“再见”时，按这个顺序取第一个
CATEGORY_ORDER: tuple[str, ...] = (
    "human_service",
    "identity",
    "thanks",
    "farewell",
    "greeting",
)

TOKENS: dict[str, tuple[str, ...]] = {
    "greeting": (
        "你好", "您好", "哈喽", "哈啰", "嗨", "hello", "hi",
        "在吗", "在么", "在不在", "有人吗",
        "早上好", "上午好", "中午好", "下午好", "晚上好",
    ),
    "identity": (
        "你是谁", "你是什么", "你叫什么", "介绍一下你", "介绍下你",
        "你能做什么", "你能干什么", "你能干嘛", "你会什么", "你有什么功能",
        "你能帮我做什么", "你能帮我干什么", "你是机器人吗",
    ),
    "thanks": (
        "谢谢你", "谢谢您", "谢谢", "谢啦", "谢了", "多谢", "非常感谢", "感谢",
        "thanks", "thankyou", "thx",
    ),
    "farewell": (
        "再见", "拜拜", "bye", "byebye", "886", "回见", "下次见", "先这样",
    ),
    # 人工客服只要提到就说明意图明确，单独处理（见 _match 里的短残句豁免）
    "human_service": (
        "转人工", "人工客服", "联系人工", "找人工", "真人客服", "人工服务",
    ),
}

# 剥掉这些之后如果什么都不剩，才认为“这句话只是客套”
FILLER = (
    "你", "您", "我", "他", "她", "的", "了", "啊", "呀", "呢", "吧", "哦",
    "嗯", "哈", "啦", "嘞", "哟", "呐", "嘛", "唉", "诶", "一下", "一个",
    "这个", "那个", "那么", "请问", "请", "帮", "帮忙", "谢谢", "想", "要",
    "有", "个", "问题", "问", "说", "看", "能", "可以", "吗", "是",
)

# 出现在句首的客套/请求框架。检索前会剥掉它们，只把“话题部分”交给检索。
# 例：“你好，我想退款” → “退款”。不剥的话，“你好”“我想”这些二元组会稀释
# 词面覆盖度，导致明明是退款问题却检索不到退款政策（实测覆盖率从 1.0 掉到 0.05）。
# 只在句首剥、且只剥这些固定框架，不会动到句子中间的实义内容。
REQUEST_PREFIXES: tuple[str, ...] = (
    "你好", "您好", "在不在", "在吗", "在么", "有人吗", "哈喽", "哈啰",
    "请问一下", "请问", "麻烦问一下", "麻烦", "打扰一下", "不好意思",
    "我想问一下", "我想问问", "我想问", "想问一下", "想请教一下",
    "我想知道", "我想了解", "想了解", "了解一下", "咨询一下", "咨询",
    "帮我查一下", "帮我看看", "帮我看下", "帮我", "帮忙", "给我",
    "我要", "我想", "查一下", "查查", "查询一下", "查询", "看一下", "看下",
)

_CORE_FALLBACK = re.compile(r"^[\s，,。.！!？?、；;：:]+|[\s，,。.！!？?、；;：:]+$")

_PUNCT = re.compile(
    r"""[\s，。！？、；：,.!?~～\-—…·()（）\[\]【】{}"'“”‘’<>《》/\\|@#$%^&*_+=`]+"""
)
_SAME_CHAR = re.compile(r"^(.)\1+$")
_HAS_LETTER = re.compile(r"[\u4e00-\u9fffa-zA-Z]")

# 业务词白名单式的“否决项”：只要残留内容里出现这些词，就一律放行到业务检索。
# 这条规则比长度阈值更可靠 —— 它直接回答了“这句话到底在问业务吗”。
_BUSINESS_WORDS: tuple[str, ...] = (
    "退款", "退货", "换货", "退换", "退钱", "物流", "快递", "配送", "发货",
    "订单", "售后", "保修", "维修", "质量", "破损", "地址", "发票", "优惠",
    "会员", "积分", "运费", "签收", "到账", "包邮", "价格", "多少钱",
)


@dataclass
class SmallTalkMatch:
    """命中引导规则的结果。"""

    kind: str                      # greeting / identity / thanks / farewell / human_service
    text: str                      # 固定话术
    suggestions: list[dict] = field(default_factory=list)


def normalize(text: str) -> str:
    """去标点、去空白、转小写。中文判断不依赖空格，所以可以直接压平。"""
    return _PUNCT.sub("", (text or "").lower())


def _strip_all(text: str, pieces: tuple[str, ...]) -> str:
    """把 pieces 里出现过的词全部从 text 中删掉（长词优先，避免“谢谢你”被“谢谢”截断）。"""
    out = text
    for piece in sorted(pieces, key=len, reverse=True):
        out = out.replace(piece, "")
    return out


def _is_filler_only(text: str) -> bool:
    """剩下的是不是只有语气词/人称/客套词。"""
    if not text:
        return True
    return _strip_all(text, FILLER) == ""


def match_smalltalk(text: str) -> SmallTalkMatch | None:
    """判断是否为纯引导类发言。返回 None 表示“不是引导，走正常业务链路”。"""
    s = normalize(text)
    if not s:
        return None

    hit_categories = [c for c in CATEGORY_ORDER if any(t in s for t in TOKENS[c])]
    if not hit_categories:
        return None

    # 把所有命中类别的话术词一次性剥掉，看还剩多少实义内容。
    # 这样才能正确处理“谢谢你，再见”这种多类别混说。
    remaining = s
    for category in hit_categories:
        remaining = _strip_all(remaining, TOKENS[category])

    if _is_filler_only(remaining):
        kind = hit_categories[0]
        return SmallTalkMatch(kind=kind, text=TEXTS[kind], suggestions=default_suggestions())

    # 残留内容里只要还有业务词，一律交给业务检索。
    # 这一步是为了兜住“你好，我想知道退款流程”这类句子：它们以问候开头，
    # 但真正要问的是退款，不能被当成闲聊打发掉。
    if any(word in s for word in _BUSINESS_WORDS):
        return None

    # 唯一豁免：明确说要人工客服，即使前后还带几个字也算命中。
    # 系统没有人工客服通道，这类请求必须走“能力说明”，绝不能编电话或链接。
    if "human_service" in hit_categories and len(remaining) <= 6:
        return SmallTalkMatch(
            kind="human_service",
            text=HUMAN_SERVICE_TEXT,
            suggestions=default_suggestions(),
        )

    # 还有实义内容，但不是业务词 —— 保守起见放行到检索，不拦
    return None


def strip_request_prefix(text: str) -> str:
    """去掉句首的客套/请求框架，得到“话题部分”，供检索与意图识别使用。

    为什么需要这一步：
        用户很自然会写“你好，我想退款”。如果原样丢给检索，问句里会多出
        “你好”“好我”“我想”“想退”这些二元组，而它们几乎不可能出现在政策文档里，
        于是词面覆盖度被稀释到 0.05（门槛是 0.12），明明该命中退款政策却返回“没找到”。
        剥掉前缀后只剩“退款”，覆盖率直接到 1.0。

    边界：
        只在**句首**剥，且只剥固定框架词；句子中间的实义内容一个字都不动。
        剥完如果什么都不剩（例如用户只发了“请问”），返回原文，避免把空串交给检索。
    """
    s = (text or "").strip()
    changed = True
    while changed:
        changed = False
        for prefix in sorted(REQUEST_PREFIXES, key=len, reverse=True):
            if s.startswith(prefix):
                s = _CORE_FALLBACK.sub("", s[len(prefix):])
                changed = True
                break
    return s or (text or "").strip()


def is_unintelligible(text: str) -> bool:
    """判断是否是“看不懂”的输入（空壳、纯符号、单字重复）。

    注意这里只拦明显看不懂的情况。像“asdf”这种虽然大概率无意义，
    但规则没法可靠区分它和英文缩写，交给检索失败后的“超范围”话术处理，
    不去猜“用户打错了”。
    """
    s = normalize(text)
    if len(s) < 2:
        return True
    if not _HAS_LETTER.search(s):
        return True
    # 叠字规则只对 3 字以上生效：中文里“谢谢”“拜拜”“哈哈”是正常表达，
    # 两字重复直接判“看不懂”会把真实发言吞掉。
    if len(s) >= 3 and _SAME_CHAR.match(s):
        return True
    return False


def has_business_topic(text: str) -> bool:
    """这句话里有没有电商业务词。

    用途：检索失败后区分“业务问题但知识库没资料”和“根本不是我的业务范围”。
        前者应该说“知识库里没有找到相关依据”（用户还会继续问别的）；
        后者才该说“我只负责电商客服”。
        判错的代价不对称：把业务问题说成“不归我管”，用户会直接走人。
    """
    s = normalize(text)
    return any(word in s for word in _BUSINESS_WORDS)
