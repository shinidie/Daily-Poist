import os
import re
from typing import Dict, Optional, Tuple

import streamlit as st

# ---------------- OpenAI client init (Cloud/local friendly) ----------------
try:
    from openai import OpenAI
except Exception as e:
    OpenAI = None  # type: ignore

def get_api_key() -> Optional[str]:
    # Streamlit Cloud secrets first
    try:
        if "OPENAI_API_KEY" in st.secrets:
            return str(st.secrets["OPENAI_API_KEY"]).strip()
    except Exception:
        pass
    # Then env var
    v = os.environ.get("OPENAI_API_KEY", "").strip()
    return v if v else None

API_KEY = get_api_key()
CLIENT = None
if OpenAI is not None and API_KEY:
    try:
        CLIENT = OpenAI(api_key=API_KEY)
    except Exception:
        CLIENT = None


# ---------------- Prompts ----------------
A_SYSTEM_PROMPT = """你是资本市场舆情日报撰写助手，输出用于向上级/监管/客户汇报，必须中性、客观、公文风。
任务：在不新增任何事实、不改变判断方向的前提下，对输入的“30秒舆情快览”进行风格微调。
硬性要求：
1) 严禁新增主体、数据、时间点、监管结论或推断；不得引入任何输入中未出现的新信息；
2) 判断词与风险边界（如“偏稳定/噪音偏多/偏敏感/需升级关注”“未见/暂未/整体/部分/以…为主/尚不构成/可能/需关注”等）不得改变、不得删除、不得弱化；
3) 输出为一段话，1–2句为宜，总长度不超过原文的1.2倍；
4) 风格克制、凝练，不口语化，不使用网络表达；
5) 仅输出改写后的正文，不要标题，不要解释过程。
额外要求：必须对句式做轻微变化（如调整句首、改写连接词、重排语序），但不得改变判断方向。"""

B_REWRITE_SYSTEM_PROMPT = """你是资本市场舆情日报撰写助手，输出用于向上级/监管/客户汇报，必须中性、客观、公文风。
任务：仅对输入段落进行“风格微调改写”，不得新增/猜测任何事实、数据、主体、时间点、监管结论或法律定性。
硬性要求：
1) 严禁引入任何输入中未出现的新事实/新主体/新时间点/新结论；
2) 必须保留并原样保留所有限定词与风险边界表达（如“未见/暂未/整体/部分/以…为主/尚不构成/可能/需关注”等），不得删除或弱化；
3) 输出2–4句，长度与输入相近；不得使用项目符号；不口语化，不夸张；
4) 仅输出改写后的正文，不要标题，不要解释过程。
额外要求：必须进行明显句式调整（至少改变句首结构或主从结构一次），并对高频重复词做同义替换以降低相似度。"""

B_GENERATE_SYSTEM_PROMPT = """你是资本市场舆情分析与日报撰写助手，输出用于向上级/监管/客户汇报，必须中性、客观、公文风。
任务：基于给定的【舆情判定模式】与【原始要点】，生成一份“常规舆情日报（B版）”。

【强约束（必须遵守）】
1) 仅使用输入要点与行业通用表述，不得新增具体事实、数据、主体、时间点或监管结论；
2) 不得进行定性指控、法律判断或监管定性；
3) 必须保留风险边界词（如“未见”“暂未”“整体”“部分”“以…为主”“尚不构成”“需关注”等）；
4) 风格中性、克制、公文风，避免情绪化和网络化表达；
5) 每一部分2–4句，不要堆砌套话；不使用项目符号。

【输出结构（必须严格按以下四段）】
一、整体舆情情况
二、财经媒体传播情况
三、互动平台舆情情况
四、研判与建议
仅输出上述四段内容，不要额外说明。"""


# ---------------- Helpers ----------------
def safe_strip(x: str) -> str:
    return (x or "").strip()

def classify_auto(media_text: str, platform_text: str) -> Tuple[str, Dict]:
    """Very simple rule-based classification; returns (mode, signals)."""
    t = (media_text + "\n" + platform_text).lower()
    signals = {
        "ai_like": bool(re.search(r"ai|自动生成|模板化|同质化|一键生成", media_text + platform_text)),
        "sensitive": bool(re.search(r"问询|立案|调查|警示|处罚|诉讼|仲裁|造假|退市|爆雷|财务造假|监管", media_text + platform_text)),
        "big_move": bool(re.search(r"涨停|跌停|地天|天地|暴跌|暴涨|闪崩|异动", media_text + platform_text)),
    }

    # Priority: escalate > sensitive > noise > stable
    if re.search(r"立案|调查|处罚|退市|财务造假|刑事|重大风险|爆雷", media_text + platform_text):
        return "escalate", signals
    if signals["sensitive"] or re.search(r"问询|警示|监管", media_text + platform_text):
        return "sensitive", signals
    if signals["big_move"] or re.search(r"争议|撕|爆|热搜|刷屏|集中发酵|谣言", media_text + platform_text):
        return "noise", signals
    return "stable", signals

def render_A(company: str, window: str, mode: str) -> str:
    name = company if company else "公司"
    w = safe_strip(window)
    head = f"监测期内，{name}相关舆情" if not w else f"监测期内（{w}），{name}相关舆情"

    if mode == "stable":
        return f"{head}热度整体处于低位运行区间，增量信息有限，传播以常规行情信息及个人观点为主，整体情绪平稳，暂未见明显升级触发因素。"
    if mode == "noise":
        return f"{head}关注度有所抬升，新增信息以存量事项转引与互动讨论扩散为主，观点分化、噪音偏多，尚未见权威新增事实推动舆情结构性变化。"
    if mode == "sensitive":
        return f"{head}热度有所抬升，部分议题集中度提高，存在误读与联想扩散空间，整体处于偏敏感但可控区间，需关注后续权威信息与传播走向。"
    # escalate
    return f"{head}出现阶段性升温并伴随监管相关叙事增强，已具备外溢扩散与预期扰动条件，建议提升响应等级并强化跟踪处置。"

def extract_media_posts(text: str):
    """Extract rough 'title' lines if user pasted '某媒体《标题》'."""
    if not text.strip():
        return []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    items = []
    for ln in lines:
        m = re.search(r"《(.+?)》", ln)
        if m:
            items.append(m.group(1))
    return items

def render_media_posts_sentence(items):
    if not items:
        return ""
    # Keep short and neutral
    tops = items[:3]
    if len(items) == 1:
        return f"财经媒体端出现单篇关注，标题为《{tops[0]}》。"
    return "财经媒体端出现多篇关注，代表性标题包括：" + "、".join([f"《{t}》" for t in tops]) + "。"

def render_B_sections(company: str, window: str, mode: str, media_text: str, platform_text: str, signals: Optional[Dict] = None) -> Dict[str, str]:
    """Deterministic B sections (base draft)."""
    name = company if company else "公司"
    w = safe_strip(window)
    head = f"监测期内，{name}相关舆情" if not w else f"监测期内（{w}），{name}相关舆情"

    media_items = extract_media_posts(media_text)
    media_hint = render_media_posts_sentence(media_items)

    if mode == "stable":
        overall = (f"{head}热度整体处于低位运行区间，增量信息有限。传播内容以常规行情信息、既有公开事项零散转引及个人观点交流为主，"
                   "暂未见权威渠道新增重大事项披露或集中性负面议题发酵，舆论情绪总体平稳。")
        base_media = ("财经媒体端关注度保持常规水平，相关内容以盘面快讯、行情简评及公开信息摘要为主，报道基调中性客观，未见集中性深度解读或持续追踪。")
        media = (media_hint + base_media) if media_hint else base_media
        platform = ("互动平台讨论量处于常态区间，发帖主体以中小投资者为主，讨论集中于股价波动、持仓操作及短期走势的个人判断，观点分化但情绪化程度不高。"
                    "部分内容存在模板化表达或疑似自动生成痕迹，但传播影响有限。")
        advice = ("综合研判，当前舆情处于低位平稳状态。建议保持常规监测频率，重点关注权威媒体是否出现观点型集中报道、互动平台是否形成单一叙事并跨平台扩散，"
                  "以及监管要素相关信息的误读演绎风险；在信息披露合规前提下，统一对外表述口径并强化事实边界。")

    elif mode == "noise":
        overall = (f"{head}关注度有所抬升，但新增信息以互动平台个人观点扩散及对存量公开信息的重复转引为主，权威渠道新增事实供给有限。"
                   "整体讨论呈现话题分散、观点堆叠特征，信息有效性相对有限。")
        base_media = ("财经媒体报道总体保持常规节奏，内容以行情快讯、公开信息摘要及既有事项回顾为主，未见集中性深度解读或持续追踪。"
                      "个别标题存在并置呈现的表达方式，可能放大联想空间，但正文多为事实转述。")
        media = (media_hint + base_media) if media_hint else base_media
        platform = ("互动平台讨论较为活跃，内容集中于股价波动归因及事项解读的个人判断，观点分化明显。部分帖文存在情绪化表达与因果牵引式叙事，"
                    "将不同信息点进行主观拼接；同时，同质化内容较多，疑似借助自动生成工具批量产出，信息增量有限。")
        advice = ("综合研判，当前舆情以噪音扰动为主，尚不构成事实层面风险升级。建议保持监测强度，重点跟踪高频话题是否形成单一叙事并外溢扩散，"
                  "以及媒体端是否出现观点型深度解读；在信息披露合规前提下，统一口径并强化时间线与事实边界表述，降低误读空间。")

    elif mode == "sensitive":
        overall = (f"{head}热度有所抬升，部分议题讨论集中度提高。新增内容以公开信息再解读与情绪化推断为主，暂未见权威新增事实披露引发的结构性变化，"
                   "整体处于偏敏感但可控区间。")
        base_media = ("财经媒体层面，相关报道以监管信息转述、事项回顾及市场解读为主，个别标题存在并置呈现倾向，可能引发联想与误读；"
                      "目前未见大范围持续追踪或集中深度调查，传播强度总体可控。")
        media = (media_hint + base_media) if media_hint else base_media
        platform = ("互动平台讨论活跃度提升，围绕监管动态、公司事项及短期走势的个人解读增多。部分发帖情绪化特征较为明显，存在将不同事件进行因果关联、"
                    "主观推断后续走向的情况；同时，模板化内容较多，观点同质化明显，信息增量有限。")
        advice = ("综合研判，当前舆情处于偏敏感但可控状态，风险点主要来自情绪叠加与标题并置引发的认知偏差。建议提升监测强度，重点关注："
                  "一是权威媒体是否出现观点型集中报道或调查类内容；二是高热话题是否跨平台扩散；三是监管要素相关表述是否出现误读、拼接或二次演绎；"
                  "在信息披露合规前提下，统一口径并强化事实边界管理。")

    else:
        overall = (f"{head}出现阶段性升温，媒体端观点型/追踪型内容增多，且与监管要素相关讨论占比上升。当前已具备外溢扩散与预期扰动触发条件，建议按升级情形处置。")
        base_media = ("财经媒体方面，除行情快讯外，已出现持续追踪、质疑或观点性较强的内容供给，传播端对叙事框架的塑造增强。需重点关注引用来源、表述边界及跨媒体复用放大风险。")
        media = (media_hint + base_media) if media_hint else base_media
        platform = ("互动平台方面，相关话题讨论集中度提升，情绪化表达与因果牵引式叙事加速聚合，存在将多信息点主观拼接并扩散的风险。需关注头部帖子与跨平台转载链条。")
        advice = ("建议提升响应等级并启动专项跟踪：一是建立关键议题清单与时间线，明确事实边界；二是梳理高频误读点并准备合规口径；"
                  "三是密切跟踪权威媒体及头部自媒体动向；四是评估是否需要在合规前提下进行必要澄清说明，以降低误读扩散与情绪外溢。")

    # optional small hint
    if signals and signals.get("ai_like"):
        platform += "另，监测到少量模板化内容，疑似自动生成，整体传播影响有限。"

    return {"overall": overall, "media": media, "platform": platform, "advice": advice}

# ---------------- OpenAI calls ----------------
def rewrite_A_with_openai(text: str, style_profile: str, model_name: str) -> str:
    if not text.strip() or CLIENT is None:
        return text

    user_input = f"风格档位：{style_profile}\n原文：{text}"
    try:
        resp = CLIENT.responses.create(
            model=model_name,
            input=[
                {"role": "system", "content": A_SYSTEM_PROMPT},
                {"role": "user", "content": user_input},
            ],
            max_output_tokens=240,
        )
        out = (resp.output_text or "").strip()
        return out if out else text
    except Exception as e:
        st.warning(f"A版AI润色失败，已回退模板：{e}")
        return text

def rewrite_B_with_openai(text: str, section_type: str, style_profile: str, model_name: str) -> str:
    if not text.strip() or CLIENT is None:
        return text

    user_input = f"段落类型：{section_type}\n风格档位：{style_profile}\n原段落：{text}"
    try:
        resp = CLIENT.responses.create(
            model=model_name,
            input=[
                {"role": "system", "content": B_REWRITE_SYSTEM_PROMPT},
                {"role": "user", "content": user_input},
            ],
            max_output_tokens=420,
        )
        out = (resp.output_text or "").strip()
        return out if out else text
    except Exception as e:
        st.warning(f"B段AI微调失败（{section_type}），已回退模板：{e}")
        return text

def generate_B_with_openai(
    company: str,
    window: str,
    mode: str,
    media_text: str,
    platform_text: str,
    model_name: str,
) -> str:
    if CLIENT is None:
        return ""

    name = company if company else "公司"
    w = safe_strip(window)
    head = f"监测期内，{name}相关舆情" if not w else f"监测期内（{w}），{name}相关舆情"

    system_prompt = (
        B_GENERATE_SYSTEM_PROMPT
        + "\n\n"
        + f"【舆情判定模式】\n{mode}\n\n"
        + f"【统一开头提示】\n{head}\n"
    )
    user_prompt = (
        "【财经媒体要点（原始输入）】\n"
        + (media_text.strip() if media_text.strip() else "未提供具体要点")
        + "\n\n"
        + "【互动平台要点（原始输入）】\n"
        + (platform_text.strip() if platform_text.strip() else "未提供具体要点")
    )

    try:
        resp = CLIENT.responses.create(
            model=model_name,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_output_tokens=950,
        )
        return (resp.output_text or "").strip()
    except Exception as e:
        st.warning(f"B版AI生成失败：{e}")
        return ""


# ---------------- UI ----------------
st.set_page_config(page_title="舆情日报生成器（vibe版）", layout="centered")
st.title("舆情日报生成器（vibe版）")
st.caption("用途：将“偏稳定/噪音偏多/偏敏感/需升级关注”等判断，渲染为A（30秒版）或B（常规日报版）。")

if OpenAI is None:
    st.error("未安装 openai 依赖。请在 requirements.txt 中加入 openai 并重新部署。")
elif not API_KEY:
    st.warning("未检测到 OPENAI_API_KEY：AI 功能不可用（将输出模板文本）。如在 Streamlit Cloud，请在 Secrets 中配置 OPENAI_API_KEY。")

company = st.text_input("公司名称（可选）", value="", key="company")
window = st.text_input("监测期（可选，例如：2026年1月19日）", value="", key="window")

col1, col2 = st.columns(2)
with col1:
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
        key="mode_select",
    )[0]
with col2:
    out = st.selectbox(
        "输出版本",
        options=[("A", "A｜30秒版"), ("B", "B｜常规日报版")],
        format_func=lambda x: x[1],
        key="out_select",
    )[0]

st.divider()
st.write("输入要点（建议在 auto 模式下填写；非 auto 模式可留空）")
media_text = st.text_area("财经媒体要点（可一句话或多条拼接）", height=120, key="media_text")
platform_text = st.text_area("互动平台要点（可一句话或多条拼接）", height=120, key="platform_text")

# B output strategy
st.divider()
st.subheader("B版输出方式")
b_strategy = st.radio(
    "选择B版生成路径（推荐：AI生成以降低重复）",
    options=[
        ("template", "模板直出/可选AI微调（更稳）"),
        ("ai_generate", "AI生成B版正文（更不重复）"),
    ],
    format_func=lambda x: x[1],
    index=1,
    key="b_strategy",
)

# Module selection & custom overrides (for template path)
st.divider()
st.subheader("输出模块选择（模板路径适用）")
col_a, col_b = st.columns(2)
with col_a:
    show_overall = st.checkbox("一、整体舆情情况", value=True, key="show_overall")
    show_media = st.checkbox("二、财经媒体传播情况", value=True, key="show_media")
with col_b:
    show_platform = st.checkbox("三、互动平台舆情情况", value=True, key="show_platform")
    show_advice = st.checkbox("四、研判与建议", value=True, key="show_advice")

st.subheader("自定义覆盖（留空则使用系统生成；填了则不走AI）")
custom_overall = st.text_area("自定义：整体舆情情况", height=80, key="custom_overall")
custom_media = st.text_area("自定义：财经媒体传播情况", height=80, key="custom_media")
custom_platform = st.text_area("自定义：互动平台舆情情况", height=80, key="custom_platform")
custom_advice = st.text_area("自定义：研判与建议", height=80, key="custom_advice")

# AI controls
st.divider()
st.subheader("AI设置（可选）")
model_name = st.selectbox(
    "模型名称（先用稳定可用的；跑通后再尝试更高阶模型）",
    options=["gpt-4.1-mini", "gpt-4.1"],
    index=0,
    key="model_name",
)

col_ai1, col_ai2 = st.columns(2)
with col_ai1:
    use_ai_A = st.checkbox("A版启用智能润色（不改变判断）", value=False, key="use_ai_A")
    style_A = st.selectbox("A版润色档位", options=["稳健监管版", "常规中性版", "更精炼版"], index=0, key="style_A")
with col_ai2:
    use_ai_B = st.checkbox("模板路径：B段启用AI微调（去重）", value=False, key="use_ai_B")
    style_B = st.selectbox("模板路径：B段微调档位", options=["稳健监管版", "常规中性版", "更精炼版"], index=0, key="style_B")

st.divider()

if st.button("生成", key="btn_generate"):
    # Decide mode
    signals = None
    final_mode = mode
    if mode == "auto":
        final_mode, signals = classify_auto(media_text, platform_text)

    if out == "A":
        base = render_A(company, window, final_mode)
        if use_ai_A and CLIENT is not None:
            result = rewrite_A_with_openai(base, style_profile=style_A, model_name=model_name)
        else:
            result = base

        st.subheader("输出（A｜30秒版）")
        st.code(result)
        st.write(f"判定模式：{final_mode}")

    else:
        # B
        if b_strategy == "ai_generate":
            if CLIENT is None:
                st.warning("AI 功能不可用（未配置 OPENAI_API_KEY 或 openai 未安装），请切换到“模板直出”。")
                sections = render_B_sections(company, window, final_mode, media_text, platform_text, signals)
                st.subheader("输出（B｜常规日报版｜模板）")
                st.code("\n\n".join([
                    "一、整体舆情情况\n" + sections["overall"],
                    "二、财经媒体传播情况\n" + sections["media"],
                    "三、互动平台舆情情况\n" + sections["platform"],
                    "四、研判与建议\n" + sections["advice"],
                ]))
            else:
                result = generate_B_with_openai(
                    company=company,
                    window=window,
                    mode=final_mode,
                    media_text=media_text,
                    platform_text=platform_text,
                    model_name=model_name,
                )
                st.subheader("输出（B｜常规日报版｜AI生成）")
                st.code(result if result else "（未返回内容：请查看页面警告信息或调整输入要点/模型）")
                st.write(f"判定模式：{final_mode}")
        else:
            # Template path
            sections = render_B_sections(company, window, final_mode, media_text, platform_text, signals)

            def pick(key: str, custom_text: str, section_type: str) -> str:
                if custom_text.strip():
                    return custom_text.strip()
                base_seg = sections[key]
                if use_ai_B and CLIENT is not None:
                    return rewrite_B_with_openai(
                        base_seg,
                        section_type=section_type,
                        style_profile=style_B,
                        model_name=model_name,
                    )
                return base_seg

            output = []
            if show_overall:
                output.append("一、整体舆情情况\n" + pick("overall", custom_overall, "整体舆情情况"))
            if show_media:
                output.append("二、财经媒体传播情况\n" + pick("media", custom_media, "财经媒体传播情况"))
            if show_platform:
                output.append("三、互动平台舆情情况\n" + pick("platform", custom_platform, "互动平台舆情情况"))
            if show_advice:
                output.append("四、研判与建议\n" + pick("advice", custom_advice, "研判与建议"))

            st.subheader("输出（B｜常规日报版｜模板/微调）")
            st.code("\n\n".join(output))
            st.write(f"判定模式：{final_mode}")

st.divider()
st.write("使用说明（本地/Cloud）")
st.code(
    "本地：\n"
    "1) pip install -r requirements.txt\n"
    "2) 运行：python -m streamlit run streamlit_app.py\n\n"
    "Streamlit Cloud：\n"
    "1) 仓库根目录包含 requirements.txt（至少含 streamlit 和 openai）\n"
    "2) Manage app -> Secrets 配置：OPENAI_API_KEY = \"sk-...\"\n"
)
