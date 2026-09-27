# Agent 设计面试手册 · Agent Design Interview Handbook

手册系列新一本。不是又一本讲 ReAct 的书：每个单元是一道没见过的 Agent 设计题——限时交卷 → 揭晓参考交卷与评分表 → 2 分钟英文口述 → 逐层追问。原理回链到 AI 系统工程手册与 CCDV / CCAR 手册。

**状态**：16 个单元全部完成（6 道端到端交卷 + 10 张横切深挖），均过 Codex 独立审查与复核。在线阅读：<https://xxxxxthhh.github.io/agent-interview-handbook/>（推到 `main` 由 `.github/workflows/pages.yml` 按白名单发布 `index.html`、`units/`、`assets/`）。

## 结构

```
content/catalog.tsv     16 单元目录（唯一真值：编号、Part、P0、标题）
content/A04.md          单元内容源：扁平 frontmatter + 固定 ## 槽位（作者只改这里）
assets/fig/*.svg        参考交卷的数据流图（构建时内联，颜色全用 CSS 变量）
assets/handbook.css     系列共享样式（复制自 AI 系统工程手册，勿改）
assets/interview.css    本书专属组件：交卷台 / 计时器 / 揭晓 / 追问链 / 失败卡
assets/interview.js     Interview Bench 行为（渐进增强，草稿默认不存本地）
tools/build.py          生成 units/*.html、index.html、cards/*.md（只用标准库）
tools/check.py          程序门禁：源与渲染产物分别核对
tools/mutate.py         对门禁的 mutation test
units/ cards/ index.html  生成物，勿手改
reference/              构建期资源，不发布（交互行为测试页、窄屏预览页）
spec/ .private/         本地规格与私人名单，不入库
```

## 命令

```bash
python3 tools/build.py     # 生成
python3 tools/check.py     # 门禁（会先构建）；提交前必跑
python3 tools/mutate.py    # 改动 check.py / build.py 后必跑，须 0 survived
python3 -m http.server 8931   # 本地预览；交互测试页 /reference/bench-test.html
```
