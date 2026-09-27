#!/usr/bin/env python3
"""程序化门禁：先构建，再分别核对内容源与渲染产物。

只验证可计算的形式与不变量；事实归因、答案质量、口述时长由人工/独立审查负责（见 CLAUDE.md）。
用法：python3 tools/check.py [ROOT]      退出码 0 = 全绿，1 = 有错误
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build as B  # noqa: E402

# 公开产物里不得出现的具体公司名（用户决定：只按岗位类型公开）。
# 仓库里只放通用厂商名；与个人求职相关的名单放在不入库的 .private/company-blocklist.txt（一行一个）。
COMPANY_BLOCKLIST = ['Anthropic', 'OpenAI', 'Google', 'Microsoft']
_PRIVATE_BLOCKLIST = Path(__file__).resolve().parent.parent / '.private' / 'company-blocklist.txt'
# 绝对化措辞只警告，交人工复核（QUALITY.md 第 2 条）
ABSOLUTE_WORDS = ['一定', '必然', '绝对', '完全', '最可靠', '永远', '100%']
REQUIRED_FOLLOWUP_TAGS = ['需求变化', '失败反证', '为何不用备选']
WORDS_RANGE = (200, 230)


def check(root):
    root = Path(root)
    errors, warnings = [], []
    E = errors.append
    W = warnings.append

    try:
        units, catalog = B.build(root)
    except B.BuildError as e:
        return [f'build: {e}'], []

    ids = [c['id'] for c in catalog]
    if len(catalog) != 16 or len(set(ids)) != 16:
        E(f'catalog: 应为 16 个不重复单元，实际 {len(catalog)} / {len(set(ids))}')
    if sum(c['kind'] == 'A' for c in catalog) != 6:
        E('catalog: Part A 应为 6 个')
    if [c['id'] for c in catalog if c['priority'] == 'P0'] != ['A02', 'A03', 'A04', 'B01', 'B06', 'B07']:
        E('catalog: P0 集合与 spec 不一致（A02 A03 A04 B01 B06 B07）')

    for uid, (meta, slots, order) in units.items():
        p = f'content/{uid}.md'
        if uid not in ids:
            E(f'{p}: id 不在 catalog.tsv 中')
            continue
        cat = catalog[ids.index(uid)]
        for k in B.FRONTMATTER_KEYS + (B.FRONTMATTER_KEYS_A if meta.get('kind') == 'A' else []):
            if k not in meta:
                E(f'{p}: frontmatter 缺 {k}')
        kind = meta.get('kind')
        if kind not in B.SLOTS:
            E(f'{p}: kind 必须是 A 或 B')
            continue
        if kind != cat['kind'] or meta.get('priority') != cat['priority']:
            E(f'{p}: kind/priority 与 catalog 不一致')

        # 槽位：必须齐全、顺序固定、不多不少
        expected = [s for s in B.SLOTS[kind] if s in order or s not in B.OPTIONAL_SLOTS]
        if order != expected:
            E(f'{p}: 槽位顺序/集合不符。\n    期望 {expected}\n    实际 {order}')
            continue
        for s in expected:
            if not slots[s]:
                E(f'{p}: 槽位 {s} 为空')

        if '自拟' not in slots['Prompt']:
            E(f'{p}: Prompt 须声明「自拟」训练题')
        n = len(B.list_items(slots['Clarify'], ordered=True))
        if not 3 <= n <= 5:
            E(f'{p}: Clarify 应 3–5 条，实际 {n}')
        frame = [l for l in slots['One-line frame'].splitlines() if l.strip()]
        if len(frame) != 1:
            E(f'{p}: One-line frame 应恰好 1 行')
        n = len(B.table_rows(slots['Decision table']))
        if not 4 <= n <= 7:
            E(f'{p}: Decision table 设计点应 4–7 行，实际 {n}')
        words = len(slots['Two-minute English'].split())
        if not WORDS_RANGE[0] <= words <= WORDS_RANGE[1]:
            E(f'{p}: 英文口述稿 {words} 词，应在 {WORDS_RANGE[0]}–{WORDS_RANGE[1]}（词数只是预警，最终以真人计时为准）')

        fus = B.split_h3(slots['Follow-ups'])
        if not 5 <= len(fus) <= 7:
            E(f'{p}: 追问应 5–7 个，实际 {len(fus)}')
        tags = [re.match(r'^\[([^\]]+)\]', q).group(1) if re.match(r'^\[([^\]]+)\]', q) else None for q, _ in fus]
        for t in REQUIRED_FOLLOWUP_TAGS:
            if t not in tags:
                E(f'{p}: 追问缺少「{t}」类')
        for q, body in fus:
            if len(B.list_items(body, ordered=False)) < 2:
                E(f'{p}: 追问「{q[:20]}」的要点少于 2 条')

        fails = B.split_h3(slots['Failure cards'])
        if len(fails) < 2:
            E(f'{p}: 失败卡至少 2 张，实际 {len(fails)}')
        for t, body in fails:
            for f in ('症状', '根因', '防线'):
                if f'**{f}**' not in body:
                    E(f'{p}: 失败卡「{t}」缺「{f}」')

        refs = B.parse_refs(slots['Cross-references'])
        if not any(s != 'unit' for s, _, _ in refs):
            E(f'{p}: 至少 1 条到既有手册的回链')
        for s, t, _ in refs:
            if s == 'unit' and t not in ids:
                E(f'{p}: 回链 unit:{t} 不在 catalog')
            elif s != 'unit':
                local = Path(B.EXTERNAL_LOCAL[s].format(t)).expanduser()
                if not local.parent.exists():
                    W(f'{p}: 无法核对 {s}:{t}（本机没有该手册仓库）')
                elif not local.exists():
                    E(f'{p}: 外部回链 {s}:{t} 在该手册里不存在')
        unit_refs = {t for s, t, _ in refs if s == 'unit'}
        for f in (meta.get('followups_to') or '').split(','):
            f = f.strip()
            if f and f not in ids:
                E(f'{p}: followups_to 含未知单元 {f}')
            elif f and f not in unit_refs:
                E(f'{p}: followups_to 的 {f} 没有出现在 Cross-references 的 unit 回链里')

        if kind == 'A':
            if not re.search(r'!\[\[fig:[\w-]+\|', slots['Reference submission']):
                E(f'{p}: 参考交卷必须含数据/控制流图')
            if not re.search(r'^\*\*基线', slots['Reference submission'], re.M):
                E(f'{p}: 参考交卷必须给出比 Agent 更简单的基线')
            n = len(B.table_rows(slots['Rubric']))
            if n != 5:
                E(f'{p}: 评分表应 5 个维度，实际 {n}')
            if not meta.get('submit_minutes', '').isdigit() or not 20 <= int(meta['submit_minutes']) <= 30:
                E(f'{p}: submit_minutes 应在 20–30')
        if slots.get('Estimate'):
            for f in ('假设', '```', '敏感性', '怎么实测'):
                if f not in slots['Estimate']:
                    E(f'{p}: 估算缺「{f}」')

        head = B.cells([l for l in slots['Practice log'].splitlines() if l.startswith('|')][0])
        if ('交卷用时' in head) != (kind == 'A'):
            E(f'{p}: Practice log 表头：A 卡要有「交卷用时」列，B 卡不要')

        # 本人专属字段在公开源里必须是空表
        for s in ('My example', 'Practice log'):
            for row in B.table_rows(slots[s]):
                start = 1 if s == 'My example' else 0
                if any(c for c in row[start:]):
                    E(f'{p}: {s} 表格有已填内容——本人经历不进公开源')

        for w in ABSOLUTE_WORDS:
            for line in open(root / p, encoding='utf-8'):
                if w in line:
                    W(f'{p}: 绝对化措辞「{w}」待人工复核：{line.strip()[:50]}')

        # ---------- 渲染产物 ----------
        h = (root / 'units' / f'{uid}.html').read_text(encoding='utf-8')
        need = ['data-unit="%s"' % uid, 'data-prompt', 'data-reference', 'data-followups', 'data-frame', 'data-oral']
        if kind == 'A':
            need += ['data-submission', 'data-bench', 'data-fig=', 'data-twist']
        for n_ in need:
            if n_ not in h:
                E(f'units/{uid}.html: 缺少 {n_}')
        if h.count('data-layer=') != len(fus):
            E(f'units/{uid}.html: 追问层数 {h.count("data-layer=")} ≠ 源 {len(fus)}')
        timers = h.count('data-timer ')
        if timers != (2 if kind == 'A' else 1):
            E(f'units/{uid}.html: 计时器数量不对（{timers}）')
        if 'localStorage' in h:
            E(f'units/{uid}.html: 页面内联了 localStorage 调用；持久化只能在 interview.js 里且默认关闭')

    # ---------- 全站 ----------
    js = (root / 'assets' / 'interview.js').read_text(encoding='utf-8')
    if 'function save() { if (persist.checked)' not in js:
        E('assets/interview.js: 草稿写入必须受「保存到此浏览器」开关控制')
    blocklist = list(COMPANY_BLOCKLIST)
    if _PRIVATE_BLOCKLIST.exists():
        blocklist += [l.strip() for l in _PRIVATE_BLOCKLIST.read_text(encoding='utf-8').splitlines() if l.strip()]
    else:
        W('未找到 .private/company-blocklist.txt，只检查了通用厂商名')
    public = [root / 'index.html'] + sorted((root / 'units').glob('*.html')) + sorted((root / 'cards').glob('*.md'))
    for f in public:
        t = f.read_text(encoding='utf-8')
        rel = f.relative_to(root)
        for c in blocklist:
            if re.search(rf'(?<![A-Za-z]){re.escape(c)}(?![A-Za-z])', t):
                E(f'{rel}: 公开产物出现公司名「{c}」')
        if re.search(r'/Users/|~/Documents', t):
            E(f'{rel}: 公开产物出现本地私有路径')
        if f.suffix == '.html':
            for href in re.findall(r'(?:href|src)="([^"#]+)"', t):
                if href.startswith(('http://', 'https://', 'data:')):
                    continue
                if not (f.parent / href).resolve().exists():
                    E(f'{rel}: 本地链接失效 {href}')
    idx = (root / 'index.html').read_text(encoding='utf-8')
    n_toc = idx.count('class="n"')
    if n_toc != len(catalog):
        E(f'index.html: 目录条目 {n_toc} ≠ catalog {len(catalog)}')
    return errors, warnings


if __name__ == '__main__':
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    errors, warnings = check(root)
    for w in warnings:
        print(f'WARN  {w}')
    for e in errors:
        print(f'ERROR {e}')
    print(f'{len(errors)} error(s), {len(warnings)} warning(s)')
    sys.exit(1 if errors else 0)
