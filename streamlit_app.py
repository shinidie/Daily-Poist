# app.py
# Streamlit 舆情日报生成器（vibe coding 版）
# 功能：
# - 模式：auto / stable（偏稳定低位）/ noise（噪音偏多）/ sensitive（偏敏感但可控）/ escalate（需升级关注）
# - 输出：A（30秒版）/ B（常规日报版）
# - 可选：公司名称、监测期
# - 可选：粘贴媒体要点、互动平台要点，用于 auto 模式自动判定及文本轻微微调

import streamlit as st
import re
from typing import List, Tuple

def extract_media_posts(media_text: str, max_items: int = 5) -> List[Tuple[str, str]]:
    """
    从媒体要点中提取“媒体名 + 文章标题”，支持：
    - 中国经济网发文《标题》
    - 证券时报刊发《标题》
    - XX发布文章《标题》
    允许多条混写；返回去重后的列表。
    """
    if not media_text:
        return []

    t = media_text.replace("“", "《").replace("”", "》").replace('"', "《").replace('"', "》")
    # 常见动词：发文/刊发/发布/发表/推出/报道/刊登
    pattern = re.compile(r"(?P<outlet>[\u4e00-\u9fa5A-Za-z0-9·（）()\-]{2,30}?)\s*(?:发文|刊发|发布|发表|推出|报道|刊登)\s*《(?P<title>[^》]{2,80})》")
    found = pattern.findall(t)

    # 去重（按 outlet+title）
    seen = set()
    items: List[Tuple[str, str]] = []
    for outlet, title in found:
        outlet = outlet.strip(" ，,。；;:：")
        title = title.strip()
        key = (outlet, title)
        if key in seen:
            continue
        seen.add(key)
        items.append(key)
        if len(items) >= max_items:
            break
    return items


def render_media_posts_sentence(items: List[Tuple[str, str]]) -> str:
    """
    将提取结果渲染成一条“可上报”的提示句（不改变你的总体口径）。
    """
    if not items:
        return ""

    # 只列最多3条，避免过长；其余用“等”收尾
    show = items[:3]
    parts = [f"{outlet}发布文章《{title}》" for outlet, title in show]
    suffix = "等" if len(items) > 3 else ""
    return "监测期内，关注到" + "、".join(parts) + suffix + "。"

def classify_auto(media: str, platform: str):
    text = (media + " " + platform).strip()

    has_new_fact = any(k in text for k in ["公告", "披露", "澄清", "回复函", "正式通报", "更正", "提示性公告"])
    regulatory = any(k in text for k in ["问询", "监管", "警示", "立案", "处罚", "调查", "稽查", "行政监管措施"])
    deep_media = any(k in text for k in ["深度", "调查", "独家", "追踪", "质疑", "起底"])
    emotional = any(k in text for k in ["暴涨", "翻倍", "快跑", "庄家", "内幕", "割韭菜", "雷", "爆雷", "造假", "退市"])
    ai_like = any(k in text for k in ["AI", "模型", "自动生成", "模板化", "同质化", "一眼AI", "机器生成"])

    # 分层逻辑：尽量保守，不轻易判“升级”
    if (regulatory and deep_media) or (has_new_fact and regulatory):
        mode = "escalate"
    elif regulatory or deep_media or (emotional and not has_new_fact):
        mode = "sensitive"
    elif emotional or ai_like:
        mode = "noise"
    else:
        mode = "stable"

    signals = {
        "has_new_fact": has_new_fact,
        "regulatory": regulatory,
        "deep_media": deep_media,
        "emotional": emotional,
        "ai_like": ai_like,
    }
    return mode, signals

def render_A(company: str, window: str, mode: str):
    prefix = f"{window}，{company}相关舆情" if company else f"{window}公司相关舆情"
    if window.strip() == "":
        prefix = f"{company}相关舆情" if company else "公司相关舆情"

    if mode == "stable":
        return (f"{prefix}整体保持低位运行，新增信息有限。财经媒体以常规行情快讯及公开信息转述为主，基调中性，未见集中深度解读；"
                "互动平台讨论处于常态区间，主要为投资者个人观点交流，情绪整体平稳。综合判断，当前未见触发舆情升级的明显风险点，建议保持常规监测。")
    if mode == "noise":
        return (f"{prefix}热度有所抬升，但新增内容以互动平台个人观点扩散及存量公开信息重复转引为主，信息有效性有限。财经媒体端未见集中深度解读，"
                "互动平台存在情绪化与拼接式叙事苗头但传播可控。综合判断为噪音偏多，建议关注高频帖子是否跨平台扩散。")
    if mode == "sensitive":
        return (f"{prefix}出现阶段性升温，部分议题讨论集中度提高。媒体端以公开信息再解读及标题并置呈现为主，互动平台情绪扰动增加。"
                "综合判断为偏敏感但可控，建议提升监测强度并统一对外表述口径，防范误读扩散。")
    # escalate
    return (f"{prefix}呈现较强升温态势，媒体端出现观点型/追踪型内容，且与监管要素相关讨论增多。综合判断需升级关注，"
            "建议同步强化事实边界管理与对外口径一致性，并跟踪是否形成跨平台扩散链条。")
    

def render_B_sections(company: str, window: str, mode: str, media_text: str, signals: dict | None = None):
    media_items = extract_media_posts(media_text)
    media_hint = render_media_posts_sentence(media_items)

    name = company if company else "公司"
    w = window.strip()
    head = f"监测期内，{name}相关舆情" if not w else f"监测期内（{w}），{name}相关舆情"

    if mode == "stable":
        overall = (f"{head}热度整体处于低位运行区间，信息增量有限。传播内容主要包括常规行情信息、既有公开事项的零散转引及投资者个人观点交流，"
                   "未见权威渠道新增重大事项披露或集中性负面议题发酵。整体舆论情绪保持平稳，未出现异常放大或跨平台扩散迹象。")
        base_media = ("财经媒体端关注度保持稳定，相关报道以盘面快讯、行情简评及公开信息摘要为主，报道基调中性客观，未见集中性深度解读或持续追踪报道。"
                      "未发现明显失实信息或倾向性放大表述，媒体端整体风险水平可控。")
        media = (media_hint + base_media) if media_hint else base_media
        platform = ("互动平台讨论量处于常态区间，发帖主体以中小投资者为主，讨论内容集中于股价波动、持仓操作及短期走势的个人判断，观点分化但情绪化程度不高。"
                    "部分内容存在模板化表达或借助自动生成工具生成的痕迹，但传播范围有限，对整体舆情风险影响较小。")
        advice = ("综合研判，当前舆情处于低位平稳状态，短期内未见触发舆情升级的明显因素。建议保持常规监测频率，重点关注权威媒体是否出现观点型集中报道、"
                  "互动平台是否形成单一叙事并跨平台扩散，以及与监管要素相关信息的误读演绎风险。在信息披露合规前提下，持续保持对外表述口径一致与事实边界清晰。")

    elif mode == "noise":
        overall = (f"{head}关注度有所抬升，但新增信息以互动平台个人观点扩散及对存量公开信息的重复转引为主，未见权威渠道新增事实披露。"
                   "整体讨论呈现话题分散、观点堆叠特征，信息有效性相对有限。")
        base_media = ("财经媒体报道总体保持常规节奏，内容以行情快讯、公开信息摘要及既有事项回顾为主，未见集中性深度解读或持续追踪。"
                      "个别标题存在并置呈现的表达方式，可能放大联想空间，但正文多为事实转述，媒体端风险总体可控。")
        media = (media_hint + base_media) if media_hint else base_media
        platform = ("互动平台讨论较为活跃，内容集中于股价波动归因及事项解读的个人判断，观点分化明显。部分帖文存在情绪化表达与因果牵引式叙事，"
                    "将不同信息点进行主观拼接；同时，部分内容结构化特征明显、同质化程度较高，疑似借助自动生成工具批量产出，信息增量有限。")
        advice = ("综合研判，当前舆情以噪音扰动为主，尚不构成事实层面风险升级。建议继续保持监测强度，重点跟踪高频话题是否形成单一叙事并外部扩散，"
                  "以及媒体端是否出现观点型深度解读。在信息披露合规前提下，统一对外表述口径，强化事实边界与时间线表述，降低误读空间。")

    elif mode == "sensitive":
        overall = (f"{head}热度有所抬升，部分议题讨论集中度提高。新增内容以公开信息再解读与情绪化推断为主，尚未见权威新增事实披露引发的结构性变化。"
                   "整体舆情风险偏敏感但仍处于可控区间。")
        base_media = ("财经媒体层面，相关报道以监管信息转述、事项回顾及市场解读为主，个别标题存在并置呈现倾向，可能引发联想与误读；"
                      "目前未见大范围持续追踪或集中深度调查，传播强度总体可控。")
        media = (media_hint + base_media) if media_hint else base_media
        platform = ("互动平台讨论活跃度提升，围绕监管动态、公司事项及短期走势的个人解读增多。部分发帖情绪化特征较为明显，存在将不同事件进行因果关联、"
                    "主观推断后续走向的情况；同时，模板化内容较多，观点同质化明显，信息增量有限。")
        advice = ("综合研判，当前舆情处于偏敏感但可控状态，风险点主要来自互动平台情绪叠加及标题并置引发的认知偏差。建议提升监测强度，重点跟踪："
                  "一是是否出现权威媒体观点型集中报道或调查类内容；二是高热话题是否跨平台扩散；三是监管要素相关表述是否出现误读、拼接或二次演绎。"
                  "在信息披露合规前提下，统一口径并强化事实边界管理。")

    else:  # escalate
        overall = (f"{head}出现阶段性升温，媒体端观点型/追踪型内容增多，且与监管要素相关讨论占比上升。当前已具备外溢扩散与预期扰动的触发条件，"
                   "建议按升级情形处置。")
        base_media = ("财经媒体方面，除行情快讯外，已出现持续追踪、质疑或观点性较强的内容供给，传播端对叙事框架的塑造增强。需重点关注引用来源、"
                      "表述边界及是否出现跨媒体复用放大。")
        media = (media_hint + base_media) if media_hint else base_media
        platform = ("互动平台方面，相关话题讨论集中度提升，情绪化表达与因果牵引式叙事加速聚合，存在将多信息点主观拼接并扩散的风险。"
                    "需关注头部帖子与跨平台转载链条。")
        advice = ("建议提升响应等级并启动专项跟踪：一是建立关键议题清单与时间线，明确事实边界；二是梳理高频误读点并准备合规口径；"
                  "三是密切跟踪权威媒体及头部自媒体动向；四是评估是否需要在合规前提下进行必要的澄清说明，以降低误读扩散与情绪外溢。")

    hint = ""
    if signals and signals.get("ai_like") and mode in ["stable", "noise"]:
        hint = "另，监测到少量模板化内容，疑似自动生成，整体传播影响有限。"

    if hint:
        platform = platform + hint

    return {
        "overall": overall,
        "media": media,
        "platform": platform,
        "advice": advice,
    }


# ---------------- UI ----------------

st.set_page_config(page_title="舆情日报生成器（vibe版）", layout="centered")
st.title("舆情日报生成器（vibe版）")

st.caption("用途：将“今日偏稳定/噪音偏多/偏敏感”等内部判断，稳定渲染为A（30秒版）或B（常规日报版）的可用文字。")

company = st.text_input("公司名称（可选）", value="", key="company")
window = st.text_input("监测期（可选，例如：2026年1月19日）", value="", key="window")
media_text = st.text_area("财经媒体要点（可一句话或多条拼接）", height=120, key="media_text")
platform_text = st.text_area("互动平台要点（可一句话或多条拼接）", height=120, key="platform_text")
mode = st.selectbox(
    "模式",
    options=[
        ("auto", "自动判定（基于要点触发词）"),
        ("stable", "偏稳定（低位运行）"),
        ("noise", "噪音偏多"),
        ("sensitive", "偏敏感但可控"),
        ("escalate", "需升级关注"),
    ],
    format_func=lambda x: x[1],
    key="mode",
)[0]
out = st.selectbox(
    "输出版本",
    options=[
        ("A", "A｜30秒版"),
        ("B", "B｜常规日报版"),
    ],
    format_func=lambda x: x[1],
    key="out",
)[0]

st.divider()
st.write("输入要点（可选，建议在 auto 模式下填写；非 auto 模式可留空）")
media_text = st.text_area("财经媒体要点（可一句话或多条拼接）", height=120)
platform_text = st.text_area("互动平台要点（可一句话或多条拼接）", height=120)

st.divider()
st.subheader("输出模块选择")

col_a, col_b = st.columns(2)

with col_a:
    show_overall = st.checkbox("一、整体舆情情况", value=True, key="show_overall")
    show_media = st.checkbox("二、财经媒体传播情况", value=True, key="show_media")

with col_b:
    show_platform = st.checkbox("三、互动平台舆情情况", value=True, key="show_platform")
    show_advice = st.checkbox("四、研判与建议", value=True, key="show_advice")

st.subheader("自定义覆盖（留空则使用系统生成）")

custom_overall = st.text_area("自定义：整体舆情情况", height=80, key="custom_overall")
custom_media = st.text_area("自定义：财经媒体传播情况", height=80, key="custom_media")
custom_platform = st.text_area("自定义：互动平台舆情情况", height=80, key="custom_platform")
custom_advice = st.text_area("自定义：研判与建议", height=80, key="custom_advice")

if st.button("生成"):
    # ① 先定义，保证后面一定能用
    signals = None
    final_mode = mode

    # ② 如果是 auto，才计算
    if mode == "auto":
        final_mode, signals = classify_auto(media_text, platform_text)

    # ③ A / B 分支
    if out == "A":
        result = render_A(company, window, final_mode)
        st.subheader("输出（A｜30秒版）")
        st.code(result)
    else:
        sections = render_B_sections(company, window, final_mode, media_text, signals)

        output = []
        if show_overall:
            t = custom_overall.strip() or sections["overall"]
            output.append("一、整体舆情情况\n" + t)

        if show_media:
            t = custom_media.strip() or sections["media"]
            output.append("二、财经媒体传播情况\n" + t)

        if show_platform:
            t = custom_platform.strip() or sections["platform"]
            output.append("三、互动平台舆情情况\n" + t)

        if show_advice:
            t = custom_advice.strip() or sections["advice"]
            output.append("四、研判与建议\n" + t)

        st.subheader("输出（B｜常规日报版）")
        st.code("\n\n".join(output))

    st.write(f"判定模式：{final_mode}")


st.divider()
st.write("使用方式")
st.code(
    "1) 安装依赖：pip install streamlit\n"
    "2) 运行：streamlit run app.py\n"
    "3) 选择模式与输出版本，点击“生成”即可复制结果"
)

