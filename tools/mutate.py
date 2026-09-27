#!/usr/bin/env python3
"""对门禁本身的 mutation test：在临时副本里逐条注入违规，断言 check.py 会变红。

改动 check.py / build.py 后必跑。任何一条「存活」（注入后仍全绿）都说明门禁有盲区。
用法：python3 tools/mutate.py
"""
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import check as C  # noqa: E402


def sub(path, old, new, count=1, regex=False):
    def f(root):
        p = root / path
        t = p.read_text(encoding='utf-8')
        t2 = re.sub(old, new, t, count=count, flags=re.M | re.S) if regex else t.replace(old, new, count)
        if t2 == t:
            raise RuntimeError(f'变异没有命中：{path} {old[:30]!r}')
        p.write_text(t2, encoding='utf-8')
    return f


def drop_section(path, heading):
    """删掉某个 ### 小节（追问或失败卡）。"""
    return sub(path, rf'^### {re.escape(heading)}.*?(?=^### |^## )', '', regex=True)


U = 'content/A04.md'
MUTATIONS = [
    ('删一条追问（7→6 仍合法，再删到 4）',
     lambda r: [drop_section(U, t)(r) for t in ('[运行]', '[评估]', '[数据权限]')]),
    ('删掉「需求变化」类追问标签', sub(U, '### [需求变化]', '### [变化]')),
    ('Prompt 去掉「自拟」声明', sub(U, '题面为本书自拟的训练题', '题面为本书的训练题')),
    ('Prompt 里写入公司名', sub(U, '某持牌金融机构', 'Microsoft 这样的公司里的持牌金融机构')),
    ('Prompt 里写入本地私有路径', sub(U, '请在白板上设计这个系统。', '请在白板上设计这个系统。参见 ~/Documents/private-notes。')),
    ('把「自拟」题改说成官方真题（语义类，预期脚本抓不到→人工审）', None),
    ('Clarify 删到 2 条', sub(U, r'^3\. .*?\n4\. .*?\n5\. .*?\n', '', regex=True)),
    ('One-line frame 变成两行', sub(U, '放行权留给签字人。', '放行权留给签字人。\n另外还要考虑成本。')),
    ('Decision table 删到 3 行', sub(U, r'^\| 证据校验.*?\n\| 「缺失」.*?\n\| 权限与数据.*?\n\| 人工放行.*?\n', '', regex=True)),
    ('英文口述稿超长', sub(U, 'argue about cost.', 'argue about cost. ' + 'This sentence pads the script. ' * 12)),
    ('删掉参考交卷的图', sub(U, r'^!\[\[fig:A04-flow\|.*?\]\]\n', '', regex=True)),
    ('图文件引用不存在', sub(U, 'fig:A04-flow|', 'fig:A04-missing|')),
    ('中途变化失去标记（折叠块消失）', sub(U, '**中途变化**', '**中途补充**')),
    ('followups_to 与回链不一致', sub(U, 'followups_to: B01,', 'followups_to: B05, B01,')),
    ('外部回链文件名写错', sub(U, '[ai:4-2-planning-loop]', '[ai:4-2-planing-loop]')),
    ('A 卡练习记录丢了交卷列', sub(U, '| 日期 | 交卷用时 | 口述用时 |', '| 日期 | 口述用时 |')),
    ('删掉基线', sub(U, '**基线与升级条件。**', '**升级条件。**')),
    ('评分表删一个维度', sub(U, r'^\| 表达 .*?\n', '', regex=True)),
    ('失败卡只剩 1 张', lambda r: [drop_section(U, t)(r) for t in ('引用真实，但证明不了结论', '人审变成橡皮图章')]),
    ('失败卡缺「根因」', sub(U, '- **根因**：把「top-k', '- 把「top-k')),
    ('估算缺敏感性', sub(U, '**敏感性**', '**补充**')),
    ('回链指向目录外单元', sub(U, '[unit:B07]', '[unit:B99]')),
    ('回链只剩内部单元', sub(U, r'^- \[(ai|dv|ar):.*?\n', '', count=0, regex=True)),
    ('本人例子被代填', sub(U, '| 权限或数据边界在设计时差点漏掉 | | | | |', '| 权限或数据边界在设计时差点漏掉 | 在某项目里 | 我设计了 ACL | 上线无事故 | 加了测试 |')),
    ('出现原始 HTML', sub(U, '## Constraints\n', '## Constraints\n\n<script>alert(1)</script>\n')),
    ('槽位顺序被打乱', sub(U, '## Rubric', '## Rubrics')),
    ('catalog 少一个单元', sub('content/catalog.tsv', r'^B10\t.*?\n', '', regex=True)),
    ('P0 集合被改', sub('content/catalog.tsv', 'B07\tB\tP0', 'B07\tB\t-')),
    ('交卷草稿改成默认持久化', sub('assets/interview.js', 'function save() { if (persist.checked) store(',
                                     'function save() { if (true) store(')),
    ('生成器丢了交卷 textarea', sub('tools/build.py', '<textarea id="sub-{uid}" data-submission', '<textarea id="sub-{uid}"')),
    ('生成器丢了追问层标记', sub('tools/build.py', "fu.append(f'<li data-layer=\"{n}\">", "fu.append(f'<li>")),
    ('样式表链接失效', sub('tools/build.py', 'assets/interview.css', 'assets/interview-missing.css')),
]


def main():
    survived, semantic = [], []
    for name, mut in MUTATIONS:
        if mut is None:
            semantic.append(name)
            print(f'  SKIP  {name}')
            continue
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for d in ('content', 'assets', 'tools'):
                shutil.copytree(ROOT / d, root / d, ignore=shutil.ignore_patterns('__pycache__'))
            mut(root)
            # 被变异的 build.py 需要从副本加载
            sys.modules.pop('build', None)
            sys.path.insert(0, str(root / 'tools'))
            import build as B2  # noqa: F401
            C.B = B2
            errors, _ = C.check(root)
            sys.path.pop(0)
        ok = bool(errors)
        print(f'  {"KILL " if ok else "ALIVE"} {name}' + (f'  ← {errors[0][:70]}' if ok else ''))
        if not ok:
            survived.append(name)
    sys.modules.pop('build', None)
    print(f'\n{len(MUTATIONS) - len(semantic) - len(survived)} killed, {len(survived)} survived, '
          f'{len(semantic)} semantic (needs human review)')
    sys.exit(1 if survived else 0)


if __name__ == '__main__':
    main()
