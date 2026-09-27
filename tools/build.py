#!/usr/bin/env python3
"""从 content/*.md 生成 units/*.html、index.html 与 cards/*.md。

只用标准库。内容源是扁平 frontmatter + 固定的 `## 槽位`；作者不写 HTML，
交互所需的 DOM（data-* 钩子）全部由本脚本按槽位生成，assets/interview.js 只绑定行为。

用法：python3 tools/build.py [ROOT]   （ROOT 默认为仓库根目录）
"""
import html
import re
import sys
from pathlib import Path

SITE_TITLE = 'Agent 设计面试手册'

# 槽位顺序即页面顺序；A = 端到端交卷，B = 横切深挖
SLOTS_COMMON = ['Prompt', 'Constraints', 'Clarify', 'One-line frame', 'Decision table']
SLOTS = {
    'A': SLOTS_COMMON + ['Blank submission', 'Reference submission', 'Rubric',
                         'Two-minute English', 'Follow-ups', 'Failure cards', 'Estimate',
                         'Cross-references', 'My example', 'Practice log'],
    'B': SLOTS_COMMON + ['Two-minute English', 'Follow-ups', 'Failure cards', 'Estimate',
                         'Cross-references', 'My example', 'Practice log'],
}
OPTIONAL_SLOTS = {'Estimate'}
FRONTMATTER_KEYS = ['id', 'kind', 'title', 'title_zh', 'priority', 'role_tags',
                    'followups_to', 'tool_asof']
FRONTMATTER_KEYS_A = ['submit_minutes']
# 外部手册的本地仓库，check.py 用来核对回链文件确实存在
EXTERNAL_LOCAL = {
    'ai': '~/Documents/ai-systems-handbook-starter/chapters/{}.html',
    'dv': '~/Documents/ccdv-handbook/chapters/{}.html',
    'ar': '~/Documents/ccar-handbook/chapters/{}.html',
}

EXTERNAL = {
    'ai': ('AI 系统工程手册', 'https://xxxxxthhh.github.io/ai-systems-handbook/chapters/{}.html'),
    'dv': ('CCDV 备考手册', 'https://xxxxxthhh.github.io/ccdv-handbook/chapters/{}.html'),
    'ar': ('CCAR 备考手册', 'https://xxxxxthhh.github.io/ccar-handbook/chapters/{}.html'),
}


class BuildError(Exception):
    pass


# ---------------------------------------------------------------- 解析

def parse_unit(path):
    text = path.read_text(encoding='utf-8')
    m = re.match(r'^---\n(.*?)\n---\n(.*)$', text, re.S)
    if not m:
        raise BuildError(f'{path.name}: 缺少 frontmatter')
    meta = {}
    for line in m.group(1).splitlines():
        if not line.strip():
            continue
        if ':' not in line:
            raise BuildError(f'{path.name}: frontmatter 行不是 key: value —— {line!r}')
        k, v = line.split(':', 1)
        meta[k.strip()] = v.strip()
    slots, order, cur = {}, [], None
    for line in m.group(2).splitlines():
        if line.startswith('## '):
            cur = line[3:].strip()
            if cur in slots:
                raise BuildError(f'{path.name}: 槽位重复 {cur}')
            slots[cur] = []
            order.append(cur)
        elif cur is not None:
            slots[cur].append(line)
    slots = {k: '\n'.join(v).strip() for k, v in slots.items()}
    return meta, slots, order


def load_catalog(root):
    rows = (root / 'content' / 'catalog.tsv').read_text(encoding='utf-8').strip().splitlines()
    head = rows[0].split('\t')
    return [dict(zip(head, r.split('\t'))) for r in rows[1:]]


def split_h3(body):
    """把槽位正文按 ### 切成 [(标题, 正文)]。"""
    items, cur = [], None
    for line in body.splitlines():
        if line.startswith('### '):
            cur = [line[4:].strip(), []]
            items.append(cur)
        elif cur is not None:
            cur[1].append(line)
    return [(t, '\n'.join(b).strip()) for t, b in items]


def table_rows(body):
    """返回 markdown 表格的数据行（不含表头与分隔行），每行为单元格列表。"""
    lines = [l for l in body.splitlines() if l.strip().startswith('|')]
    if len(lines) < 2:
        return []
    return [cells(l) for l in lines[2:]]


def cells(line):
    return [c.strip() for c in line.strip().strip('|').split('|')]


def list_items(body, ordered):
    pat = r'^\d+\.\s+' if ordered else r'^-\s+'
    return [l for l in body.splitlines() if re.match(pat, l)]


def parse_refs(body):
    """Cross-references 行：- [scheme:target] 说明"""
    refs = []
    for line in body.splitlines():
        m = re.match(r'^-\s+\[(ai|dv|ar|unit):([\w-]+)\]\s*(.*)$', line)
        if m:
            refs.append(m.groups())
    return refs


# ---------------------------------------------------------------- 受限 Markdown

def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'\[([^\]]+)\]\((https?://[^)\s]+|[\w./#-]+)\)',
               lambda m: f'<a href="{html.escape(m.group(2))}">{m.group(1)}</a>', s)
    return s


def render_table(lines):
    head = cells(lines[0])
    out = ['<div class="tbl-scroll"><table><thead><tr>']
    out += [f'<th>{inline(c)}</th>' for c in head]
    out.append('</tr></thead><tbody>')
    for l in lines[2:]:
        out.append('<tr>' + ''.join(f'<td>{inline(c)}</td>' for c in cells(l)) + '</tr>')
    out.append('</tbody></table></div>')
    return ''.join(out)


def md(body, root):
    """段落 / 列表 / 表格 / 引用 / 代码块 / 图（![[fig:名字|说明]]）。禁止原始 HTML。"""
    lines, out, i = body.splitlines(), [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith('```'):
            j = i + 1
            while j < len(lines) and not lines[j].startswith('```'):
                j += 1
            code = html.escape('\n'.join(lines[i + 1:j]), quote=False)
            out.append(f'<pre class="formula calc"><code>{code}</code></pre>')
            i = j + 1
            continue
        m = re.match(r'^!\[\[fig:([\w-]+)\|(.+)\]\]$', line.strip())
        if m:
            svg_path = root / 'assets' / 'fig' / f'{m.group(1)}.svg'
            if not svg_path.exists():
                raise BuildError(f'图不存在：{svg_path.name}')
            svg = svg_path.read_text(encoding='utf-8').strip()
            out.append(f'<figure data-fig="{m.group(1)}">{svg}<figcaption>{inline(m.group(2))}</figcaption></figure>')
            i += 1
            continue
        if line.lstrip().startswith('<'):
            raise BuildError(f'内容源里出现原始 HTML：{line[:40]!r}')
        if line.startswith('|'):
            j = i
            while j < len(lines) and lines[j].startswith('|'):
                j += 1
            out.append(render_table(lines[i:j]))
            i = j
            continue
        if line.startswith('> '):
            j = i
            buf = []
            while j < len(lines) and lines[j].startswith('>'):
                buf.append(lines[j][1:].strip())
                j += 1
            out.append(f'<div class="callout prompt-card"><p>{inline(" ".join(buf))}</p></div>')
            i = j
            continue
        for ordered, pat, tag in ((False, r'^-\s+', 'ul'), (True, r'^\d+\.\s+', 'ol')):
            if re.match(pat, line):
                j, items = i, []
                while j < len(lines) and re.match(pat, lines[j]):
                    items.append(re.sub(pat, '', lines[j]))
                    j += 1
                out.append(f'<{tag}>' + ''.join(f'<li>{inline(x)}</li>' for x in items) + f'</{tag}>')
                i = j
                break
        else:
            if line.startswith('### '):
                out.append(f'<h3>{inline(line[4:])}</h3>')
                i += 1
                continue
            j, buf = i, []
            while j < len(lines) and lines[j].strip() and not re.match(r'^(-\s|\d+\.\s|\||>|```|###|!\[\[)', lines[j]):
                buf.append(lines[j])
                j += 1
            if j == i:
                raise BuildError(f'无法解析的行：{line[:40]!r}')
            out.append(f'<p>{inline(" ".join(buf))}</p>')
            i = j
    return '\n'.join(out)


# ---------------------------------------------------------------- 页面组件

def section(sid, label, heading, inner, extra=''):
    return (f'<section id="{sid}"{extra}>\n<div class="sec-tag"><span class="cell"></span>'
            f'<span class="lab">{label}</span></div>\n<h2>{heading}</h2>\n{inner}\n</section>')


def timer(seconds, label):
    mm = f'{seconds // 60:02d}:{seconds % 60:02d}'
    return (f'<div class="timer" data-timer data-seconds="{seconds}" hidden>'
            f'<span class="t-label">{label}</span><span class="t-read" aria-live="polite">{mm}</span>'
            f'<span class="t-bar"><span></span></span>'
            f'<button type="button" data-act="toggle">开始</button>'
            f'<button type="button" data-act="reset">重置</button></div>')


def reveal(key, summary, inner):
    return (f'<details class="reveal" data-reveal="{key}"><summary>{summary}</summary>'
            f'<div class="reveal-body">{inner}</div></details>')


def ref_link(scheme, target, note, known_units, catalog_ids):
    if scheme == 'unit':
        if target not in catalog_ids:
            raise BuildError(f'回链指向目录外的单元：{target}')
        if target in known_units:
            return f'<li><a href="{target}.html"><span class="ref-tag">{target}</span></a> {inline(note)}</li>'
        return f'<li><span class="ref-tag planned" title="尚未写成">{target}</span> {inline(note)}<span class="soon">待写</span></li>'
    book, url = EXTERNAL[scheme]
    if scheme == 'ai':
        m = re.match(r'^(\d)-(\d)-', target)
        tag = f'AI {m.group(1)}.{m.group(2)}' if m else target
    else:
        tag = f'{scheme.upper()} {target}'
    return (f'<li><a href="{url.format(target)}" rel="noopener"><span class="ref-tag">{tag}</span></a> '
            f'{inline(note)} <span class="ref-book">· {book}</span></li>')


def head(title, desc, depth):
    up = '../' * depth
    fonts = ('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700'
             '&family=Noto+Sans+SC:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap')
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">
<link rel="icon" type="image/svg+xml" href="{up}assets/favicon.svg">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{fonts}" rel="stylesheet" media="print" onload="this.media='all'">
<noscript><link href="{fonts}" rel="stylesheet"></noscript>
<link rel="stylesheet" href="{up}assets/handbook.css">
<link rel="stylesheet" href="{up}assets/interview.css">
<script src="{up}assets/theme.js"></script>
</head>
<body>
<button class="theme-toggle" type="button" aria-label="切换深色/浅色模式" title="切换深色/浅色模式">
  <span class="moon" aria-hidden="true">🌙</span><span class="sun" aria-hidden="true">☀️</span>
</button>
<div class="wrap">'''


def foot(depth, js=True):
    up = '../' * depth
    s = f'<script src="{up}assets/interview.js"></script>\n' if js else ''
    return f'</div>\n{s}</body>\n</html>\n'


# ---------------------------------------------------------------- 单元页

def render_unit(meta, slots, root, known_units, catalog):
    uid, kind = meta['id'], meta['kind']
    catalog_ids = [c['id'] for c in catalog]
    S = lambda k: md(slots.get(k, ''), root)
    followups = split_h3(slots['Follow-ups'])
    failures = split_h3(slots['Failure cards'])
    part = 'Part A · 端到端交卷' if kind == 'A' else 'Part B · 横切深挖'
    blocks = ''.join(f'<span class="{c}"></span>' for c in
                     ['', 'w', '', '', 'w', '', 'f', '', 'w', 'f'])
    pri = f'<span class="pri">{meta["priority"]}</span>' if meta.get('priority', '-') != '-' else ''

    out = [head(f'{uid} {meta["title_zh"]} · {SITE_TITLE}', meta['title'], 1)]
    out.append(f'<nav class="crumb"><a href="../index.html">← 目录</a> · {part}</nav>')
    out.append(f'''<main data-unit="{uid}" data-kind="{kind}">
<header class="ch">
  <div class="blockrow" aria-hidden="true">{blocks}</div>
  <div class="kicker">{part} · {uid} {pri}</div>
  <h1>{html.escape(meta["title"])}<span class="zh">{html.escape(meta["title_zh"])}</span></h1>
  <div class="meta">
    {f'<span>交卷 <b>{meta["submit_minutes"]} min</b></span>' if kind == 'A' else ''}
    <span>口述 <b>2 min</b></span>
    <span>追问 <b>{len(followups)} 层</b></span>
    <span>适合 <b>{html.escape(meta["role_tags"])}</b></span>
  </div>
</header>''')

    # 「**中途变化**」段落是答到一半才出现的约束变化，折叠起来，避免先看到
    cons, twist = slots['Constraints'], ''
    m = re.search(r'^\*\*中途变化\*\*[:：]?\s*(.+)$', cons, re.M)
    if m:
        cons = cons[:m.start()].rstrip()
        body = re.sub(r'^答到一半[，,]?\s*面试官补(了)?一句[——:：]*\s*', '', m.group(1))
        twist = reveal('twist', '答到一半再点开：面试官补了一句', f'<p data-twist>{inline(body)}</p>')
    out.append(section('prompt', 'Prompt 题面', '先读题，别急着画框图' if kind == 'A' else '先想清楚再开口',
                       f'<div data-prompt>{S("Prompt")}</div>\n<h3>约束</h3>{md(cons, root)}{twist}'))

    if kind == 'A':
        mins = int(meta['submit_minutes'])
        bench = f'''{S("Blank submission")}
<div class="bench" data-bench="{uid}">
  {timer(mins * 60, "交卷计时")}
  <label class="sr" for="sub-{uid}">你的交卷</label>
  <textarea id="sub-{uid}" data-submission rows="14" placeholder="在这里写你的澄清问题、架构、失败恢复、指标……（草稿默认不保存；需要时勾选下方「保存到此浏览器」）"></textarea>
  <div class="bench-ctl" hidden>
    <button type="button" data-act="export">导出为 .md</button>
    <label class="opt"><input type="checkbox" data-act="persist"> 保存到此浏览器</label>
    <button type="button" data-act="clear">清除此题草稿</button>
    <button type="button" data-act="clear-all">清除所有草稿</button>
  </div>
  <p class="bench-note">不要输入真实客户或机密材料。草稿只在你的浏览器里，页面不上传任何内容。</p>
</div>'''
        out.append(section('submit', 'Blank Submission 交卷', f'{mins} 分钟，从空白开始', bench))
        ref = (f'<h3>该先问的问题</h3>{S("Clarify")}'
               f'<h3>一句话框架</h3><div class="frame" data-frame>{S("One-line frame")}</div>'
               f'<h3>参考交卷</h3>{S("Reference submission")}'
               f'<h3>设计取舍表</h3>{S("Decision table")}'
               f'<h3>评分表</h3>{S("Rubric")}')
        out.append(section('reference', 'Reference 参考交卷', '交完再看',
                           f'<div data-reference>{reveal("reference", "揭晓参考交卷与评分表", ref)}</div>'))
    else:
        ref = (f'<h3>该先问的问题</h3>{S("Clarify")}'
               f'<h3>一句话框架</h3><div class="frame" data-frame>{S("One-line frame")}</div>'
               f'<h3>设计取舍表</h3>{S("Decision table")}')
        out.append(section('reference', 'Answer 参考回答', '先口答，再展开',
                           f'<div data-reference>{reveal("reference", "展开参考回答", ref)}</div>'))

    oral = (timer(120, '口述计时') +
            reveal('english', '展开 2 分钟英文口述稿', S('Two-minute English')))
    out.append(section('oral', 'Two-minute English 口述', '两分钟，先结论后展开',
                       f'<div data-oral>{oral}</div>'))

    fu = ['<ol class="followups" data-followups>']
    for n, (q, body) in enumerate(followups, 1):
        m = re.match(r'^\[([^\]]+)\]\s*(.*)$', q)
        tag, qtext = (m.group(1), m.group(2)) if m else ('追问', q)
        fu.append(f'<li data-layer="{n}"><div class="fq"><span class="qtype">{html.escape(tag)}</span>'
                  f'{inline(qtext)}</div>{reveal(f"f{n}", "先口答，再展开要点", md(body, root))}</li>')
    fu.append('</ol><button type="button" class="next-layer" data-act="next-layer" hidden>下一层追问 ↓</button>')
    out.append(section('followups', 'Follow-ups 追问', '一层一层往下问', ''.join(fu)))

    fc = ['<div class="fail-grid">']
    for t, body in failures:
        fc.append(f'<div class="case fail-card"><div class="case-head"><span class="cell"></span>{inline(t)}</div>'
                  f'<div class="case-body">{md(body, root)}</div></div>')
    fc.append('</div>')
    out.append(section('failures', 'Failure Modes 失败模式', '这些地方最容易栽', ''.join(fc)))

    if slots.get('Estimate'):
        out.append(section('estimate', 'Estimate 估算', '带着量纲算一遍', S('Estimate')))

    refs = parse_refs(slots['Cross-references'])
    lis = ''.join(ref_link(s, t, n, known_units, catalog_ids) for s, t, n in refs)
    out.append(section('refs', 'Cross-references 回链', '原理去哪里补', f'<ul class="refs">{lis}</ul>'))

    mine = (f'<div class="mine" data-mine>{S("My example")}</div>'
            f'<h3>练习记录</h3><div class="mine">{S("Practice log")}</div>')
    out.append(section('mine', 'Your Turn 本人填写', '只写真实经历', mine))
    out.append('</main>')

    ids = [c['id'] for c in catalog]
    i = ids.index(uid)
    prev_ = catalog[i - 1] if i > 0 else None
    next_ = catalog[i + 1] if i + 1 < len(catalog) else None
    def nav(c, arrow_left):
        if not c:
            return '<span class="disabled"></span>'
        label = f'{c["id"]} {c["title_zh"]}'
        label = f'← {label}' if arrow_left else f'{label} →'
        if c['id'] in known_units:
            return f'<a href="{c["id"]}.html">{label}</a>'
        return f'<span class="disabled">{label}（待写）</span>'
    out.append(f'<nav class="next">{nav(prev_, True)}{nav(next_, False)}</nav>')
    out.append(foot(1))
    return '\n'.join(out)


# ---------------------------------------------------------------- 目录页

def render_index(catalog, known_units):
    out = [head(SITE_TITLE, '面向面试的 Agent 设计训练：先交卷，再看参考，再接追问。', 0)]
    out.append(f'''<header class="book-head">
  <div class="blockrow" aria-hidden="true"><span></span><span class="w"></span><span></span><span></span><span class="w"></span><span class="f"></span></div>
  <div class="kicker">Agent Design Interview Handbook</div>
  <h1>{SITE_TITLE}<span class="zh">先交卷，再揭晓，再接追问</span></h1>
  <p class="lede">这不是又一本讲 ReAct 的书。每个单元是一道没见过的 Agent 设计题：限时交一版方案，对照参考交卷和评分表，用两分钟英文讲出来，再一层一层接面试官的追问。原理部分回链到本系列的 AI 系统工程手册和两本 Claude 认证手册，这里不重讲。</p>
</header>''')
    out.append('''<section class="how">
<div class="sec-tag"><span class="cell"></span><span class="lab">30 Minutes 考前半小时</span></div>
<h2>挑一道端到端题，配两张深挖卡</h2>
<ol>
<li>按场景选 <b>1 个 Part A 题</b>：看任务类型、错误代价、动作是否可逆。</li>
<li>从它的追问里挑 <b>2 张 Part B 卡</b>，看一句话框架和取舍表（约 15 分钟）。</li>
<li>打开计时器口述一遍（约 5 分钟）。</li>
<li>最后 10 分钟只做一件事：接一条没见过的反例追问，或者写一版交卷提纲。</li>
</ol>
<div class="tbl-scroll"><table><thead><tr><th>岗位类型</th><th>建议组合（示例）</th></tr></thead><tbody>
<tr><td>垂直 Agent 研发</td><td>A06 长任务 + B06 评估 + B03 上下文</td></tr>
<tr><td>Forward Deployed / 交付工程</td><td>A04 或 A03 + B07 放行点 + B01 编排光谱</td></tr>
<tr><td>Solutions / 售前架构</td><td>A02 或 A04 + B01 编排光谱 + B09 成本</td></tr>
</tbody></table></div>
<p class="note">组合是准备建议，不是任何公司的出题规律。收到面试邀请后按实际轮次调整。</p>
</section>''')
    for kind, no, name, tag in (('A', 'Part A', '端到端交卷', '6 题 · 每题 20–30 分钟'),
                                ('B', 'Part B', '横切深挖', '10 张 · 被追问时翻')):
        out.append(f'<div class="part"><div class="part-head"><span class="no">{no}</span>'
                   f'<h2>{name}</h2><span class="tag">{tag}</span></div><ul class="toc">')
        for c in (c for c in catalog if c['kind'] == kind):
            pri = ' <span class="pri">P0</span>' if c['priority'] == 'P0' else ''
            inner = (f'<span class="n">{c["id"]}</span><span class="t">{html.escape(c["title_zh"])}{pri}</span>'
                     f'<span class="d">{html.escape(c["hook"])}</span>')
            if c['id'] in known_units:
                out.append(f'<li><a href="units/{c["id"]}.html">{inner}</a></li>')
            else:
                out.append(f'<li><a aria-disabled="true">{inner}<span class="soon">待写</span></a></li>')
        out.append('</ul></div>')
    out.append('<p class="colophon">题目均为自拟训练题，场景与数字为虚构练习设定，不代表任何公司的真实面试题或真实系统。</p>')
    out.append(foot(0, js=False))
    return '\n'.join(out)


# ---------------------------------------------------------------- 空白口练卡

def render_card(meta, slots):
    fu = split_h3(slots['Follow-ups'])
    lines = [f'# {meta["id"]} · {meta["title_zh"]}（口练卡）', '',
             f'> {meta["title"]} · 由 content/{meta["id"]}.md 生成，勿手改。', '',
             '## 题面', '', slots['Prompt'], '', slots['Constraints'], '',
             '## 一句话框架', '', slots['One-line frame'], '',
             '## 追问（先口答，答不上的记进练习记录）', '']
    lines += [f'{n}. {q}' for n, (q, _) in enumerate(fu, 1)]
    lines += ['', '## 我的例子', '', slots['My example'], '', '## 练习记录', '', slots['Practice log'], '']
    return '\n'.join(lines)


# ---------------------------------------------------------------- 入口

def build(root):
    root = Path(root)
    catalog = load_catalog(root)
    units = {}
    for p in sorted((root / 'content').glob('*.md')):
        meta, slots, order = parse_unit(p)
        units[meta['id']] = (meta, slots, order)
    known = set(units)
    (root / 'units').mkdir(exist_ok=True)
    (root / 'cards').mkdir(exist_ok=True)
    for uid, (meta, slots, _) in units.items():
        (root / 'units' / f'{uid}.html').write_text(render_unit(meta, slots, root, known, catalog), encoding='utf-8')
        (root / 'cards' / f'{uid}.md').write_text(render_card(meta, slots), encoding='utf-8')
    (root / 'index.html').write_text(render_index(catalog, known), encoding='utf-8')
    return units, catalog


if __name__ == '__main__':
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    try:
        units, catalog = build(root)
    except BuildError as e:
        print(f'BUILD ERROR: {e}', file=sys.stderr)
        sys.exit(1)
    print(f'built {len(units)} unit(s) of {len(catalog)} in catalog → units/, cards/, index.html')
