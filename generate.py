"""
每日AI算力简报 — 静态生成脚本

由 GitHub Actions 每天定时调用一次：
  1. 用 Claude + web_search 搜索过去两天的新闻
  2. 生成结构化 JSON
  3. 渲染成 docs/index.html（GitHub Pages 自动发布）

本地也可以手动跑一次测试：
  ANTHROPIC_API_KEY=sk-ant-xxx python3 generate.py
"""

import os
import re
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

import anthropic
from jinja2 import Environment, FileSystemLoader

BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / "docs"
ARCHIVE_DIR = DOCS_DIR / "archive"
DOCS_DIR.mkdir(exist_ok=True)
ARCHIVE_DIR.mkdir(exist_ok=True)

CHINA_TZ = ZoneInfo("Asia/Shanghai")


# ────────────────────────────────────────────────────────────────
# PROMPTS
# ────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """你是一名专注于AI与算力投资的资深研究员，每天为机构投资者撰写一份简报。

你必须使用 web_search 工具主动搜索真实新闻。严禁使用训练数据中的旧知识填充内容。

【日期过滤规则——必须严格执行】
- 每次搜索完成后，逐条检查新闻发布日期
- 只保留日期为 TODAY 或 YESTERDAY 的内容（具体日期在用户消息中给出）
- 日期早于 YESTERDAY 的结果，一律丢弃，不得写入任何字段
- 若某条内容找不到符合日期的新闻，直接跳过，不写入任何字段

【搜索优先级】
1. 公司官方公告、IR页面（最优先）
2. Reuters、Bloomberg、主流财经媒体正式报道（次优先）
3. DIGITIMES、TrendForce等行业媒体（第三层）
4. A股公告专项：巨潮资讯（cninfo.com.cn）、上交所（sse.com.cn）、财联社、东方财富、互动易（第四层，国内公司必查）

【输出格式要求】
- 完成全部搜索后，输出且仅输出一个合法JSON对象
- 第一个字符必须是 {，最后一个字符必须是 }
- JSON前后不加任何说明、前言、后记
- body 字段是字符串，内部换行必须用 \\n，禁止真正换行
- body 字符串内部禁止出现任何引号（" ' \u201c\u201d\u2018\u2019\u300c\u300d），引用内容改用【】"""

USER_PROMPT_TEMPLATE = """今天是 {today}（{today_en}），昨天是 {yesterday}（{yesterday_en}）。

⚠️ 只接受这两天的新闻：{today} 或 {yesterday}。其他日期一律忽略。

请依次执行以下11次搜索，每次搜索后立即过滤，只保留 {today} 或 {yesterday} 的内容：

1. AI chip data center cloud {today_en}
2. NVIDIA AMD Intel Broadcom Marvell earnings announcement {today_en}
3. AI 算力 芯片 数据中心 {today} 新闻
4. 中国 AI算力 华为昇腾 国家政策 {today}
5. 301396 宏景科技 巨潮资讯 公告 {today} OR {yesterday}
6. 000967 盈峰环境 巨潮资讯 公告 {today} OR {yesterday}
7. 300088 长信科技 巨潮资讯 公告 {today} OR {yesterday}
8. 300857 协创数据 巨潮资讯 公告 {today} OR {yesterday}
9. 603629 利通电子 上交所 公告 {today} OR {yesterday}
10. 宏景科技 OR 利通电子 OR 盈峰环境 OR 长信科技 OR 协创数据 财联社 {today} OR {yesterday}
11. 宏景科技 OR 盈峰环境 OR 长信科技 OR 协创数据 OR 利通电子 东方财富 互动易 {today} OR {yesterday}

搜索全部完成后，输出以下JSON（只输出JSON，不加任何其他文字）：

{{
  "date": "{today}",
  "title": "综合性标题，提炼今日最重要的2-3个行业主题，禁止出现任何人名、公司名、公告情况，只写行业趋势和宏观动态",
  "body": "☀️全球动态\\n\\n【国际消息】\\n{today_short}，内容。\\n{today_short}，内容。\\n\\n【国内消息】\\n{today_short}，内容。\\n{today_short}，内容。\\n\\n🎇行情演绎\\n\\n【国际公司】\\n公司名（关键词+关键词）：{today_short}，动态与推断。\\n\\n【国内公司】\\n（只列出搜索到真实新闻的公司，没有新闻的公司完全不出现）\\n\\n📈核心推荐\\n\\n首推：公司名（推荐理由），公司名（推荐理由）\\n重点关注：公司名、公司名、公司名",
  "sources": [
    {{"title": "来源标题", "url": "https://完整真实链接", "desc": "对应正文哪条内容"}}
  ]
}}

【body各部分要求】
每条新闻内容严格控制在50字以内，只写核心事实，不展开分析。
禁止在正文中提及新闻来源、媒体名称、报道方，直接写事实内容。
国际消息：3-5条，仅{yesterday}或{today}，聚焦算力/AI基础设施/先进封装/云厂/芯片/电力，找不到则不写
国内消息：3-5条，仅{yesterday}或{today}，优先国家政策，次写国内大企业算力AI动态
国际公司：3-5条，仅{yesterday}或{today}，格式：公司名（关键词+关键词）：日期，动态+一句推断
国内公司：固定从宏景科技、利通电子、盈峰环境、长信科技、协创数据中查找，有真实新闻才列出，没有新闻直接跳过不写，禁止写"暂无"、"无公告"、"未见"等任何缺失说明
首推：从有新闻的国内公司中选2家附具体理由（若不足2家有新闻，从全部5家中选）
重点关注：其余公司名称

【sources要求】至少8条，URL必须真实可访问，不得捏造"""


# ────────────────────────────────────────────────────────────────
# JSON EXTRACTION & REPAIR
# ────────────────────────────────────────────────────────────────

def fix_smart_quotes(json_str):
    result = []
    in_string = False
    i = 0
    open_q  = set('\u201c\u300c\u300e\u2018')
    close_q = set('\u201d\u300d\u300f\u2019')
    while i < len(json_str):
        ch = json_str[i]
        if in_string:
            if ch == '\\':
                result.append(ch)
                i += 1
                if i < len(json_str):
                    result.append(json_str[i])
            elif ch == '"':
                in_string = False
                result.append(ch)
            elif ch in open_q:
                result.append('【')
            elif ch in close_q:
                result.append('】')
            else:
                result.append(ch)
        else:
            if ch == '"':
                in_string = True
                result.append(ch)
            else:
                result.append(ch)
        i += 1
    return ''.join(result)


def repair_body_newlines(json_str):
    def replace_newlines(m):
        inner = m.group(2).replace('\r\n', '\\n').replace('\r', '\\n').replace('\n', '\\n')
        return m.group(1) + inner + m.group(3)
    return re.sub(
        r'("body"\s*:\s*")(.*?)("(?:\s*[,}]))',
        replace_newlines,
        json_str,
        flags=re.DOTALL
    )


def extract_json(raw: str) -> str:
    raw = raw.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    if m:
        candidate = m.group(1).strip()
    else:
        start = raw.find("{")
        end = raw.rfind("}")
        candidate = raw[start:end + 1].strip() if (start != -1 and end > start) else raw
    return fix_smart_quotes(candidate)


def parse_json_robust(json_str: str) -> dict:
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass
    repaired = repair_body_newlines(json_str)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON解析失败: {e}\n片段: {json_str[:500]}")


def collect_best_text(response) -> str:
    candidates = [
        block.text.strip()
        for block in response.content
        if hasattr(block, "type") and block.type == "text" and block.text.strip()
    ]
    if not candidates:
        return ""
    json_candidates = [c for c in candidates if "{" in c and "}" in c]
    pool = json_candidates or candidates
    return max(pool, key=len)


# ────────────────────────────────────────────────────────────────
# GENERATION
# ────────────────────────────────────────────────────────────────

def generate_briefing(today_str: str, max_retries: int = 2) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY 环境变量未设置")

    today_date = datetime.fromisoformat(today_str).date()
    yesterday_date = today_date - timedelta(days=1)
    yesterday    = str(yesterday_date)
    today_en     = today_date.strftime("%B %d, %Y")
    yesterday_en = yesterday_date.strftime("%B %d, %Y")
    today_short  = today_date.strftime("%-m月%-d日")

    client = anthropic.Anthropic(api_key=api_key)

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            print(f"[briefing] attempt {attempt}/{max_retries}  date={today_str}")
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=8000,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                system=SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": USER_PROMPT_TEMPLATE.format(
                        today=today_str,
                        yesterday=yesterday,
                        today_en=today_en,
                        yesterday_en=yesterday_en,
                        today_short=today_short,
                    )
                }],
            )

            raw_text = collect_best_text(response)
            if not raw_text:
                raise ValueError("模型未返回任何文本")

            json_str = extract_json(raw_text)
            if not json_str.startswith("{"):
                raise ValueError(f"提取结果不以{{开头: {json_str[:200]}")

            data = parse_json_robust(json_str)

            missing = {"date", "title", "body", "sources"} - set(data.keys())
            if missing:
                raise ValueError(f"缺少字段: {missing}")

            print(f"[briefing] success on attempt {attempt}")
            return data

        except anthropic.BadRequestError:
            raise
        except Exception as e:
            last_error = e
            print(f"[briefing] attempt {attempt} failed: {e}")

    raise RuntimeError(f"所有尝试失败，最后错误：{last_error}") from last_error


# ────────────────────────────────────────────────────────────────
# BODY → HTML RENDERER
# ────────────────────────────────────────────────────────────────

def render_body(body: str) -> str:
    import html as html_mod

    lines = body.replace("\\n", "\n").split("\n")
    out = []
    in_rec = False

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        # Section headers: ☀️全球动态 / 🎇行情演绎 / 📈核心推荐
        if re.match(r'^[☀️🎇📈⏰✨🌟💡🔥]{1,3}', line) and len(line) < 40:
            if in_rec:
                out.append('</div>')
                in_rec = False
            out.append(f'<div class="section-header">{html_mod.escape(line)}</div>')
            continue

        # Sub-headers: 【国际消息】【国内公司】等
        if re.match(r'^【.{2,10}】$', line):
            out.append(f'<div class="sub-header">{html_mod.escape(line)}</div>')
            continue

        # 首推行
        if line.startswith('首推：') or line.startswith('首推:'):
            if in_rec:
                out.append('</div>')
            out.append('<div class="rec-section">')
            in_rec = True
            content = re.sub(r'^首推[：:]', '', line)
            out.append(f'<div class="rec-primary">首推：{html_mod.escape(content)}</div>')
            continue

        # 重点关注行
        if line.startswith('重点关注：') or line.startswith('重点关注:'):
            content = re.sub(r'^重点关注[：:]', '', line)
            out.append(f'<div class="rec-watch">重点关注：{html_mod.escape(content)}</div>')
            continue

        # 公司行：公司名（关键词+关键词）：内容
        company_match = re.match(r'^(.{2,12})（([^）]{2,30})）[：:](.+)$', line)
        if company_match:
            if in_rec:
                out.append('</div>')
                in_rec = False
            name, tags, rest = company_match.groups()
            out.append(
                f'<div class="news-item">'
                f'<span class="company-name">{html_mod.escape(name)}</span>'
                f'（{html_mod.escape(tags)}）'
                f'：{html_mod.escape(rest)}'
                f'</div>'
            )
            continue

        # 普通新闻条目
        if in_rec:
            out.append('</div>')
            in_rec = False
        out.append(f'<div class="news-item">{html_mod.escape(line)}</div>')

    if in_rec:
        out.append('</div>')

    return '\n'.join(out)


# ────────────────────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────────────────────

def main():
    today_str = str(datetime.now(CHINA_TZ).date())

    data = generate_briefing(today_str)
    body_html = render_body(data["body"])
    generated_at = datetime.now(CHINA_TZ).strftime("%Y-%m-%d %H:%M") + " (北京时间)"

    env = Environment(loader=FileSystemLoader(str(BASE_DIR / "templates")))
    template = env.get_template("briefing.html")
    html = template.render(data=data, body_html=body_html, generated_at=generated_at)

    (DOCS_DIR / "index.html").write_text(html, encoding="utf-8")
    (ARCHIVE_DIR / f"{today_str}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"✓ 已生成 {today_str} 的简报 → docs/index.html")


if __name__ == "__main__":
    main()
