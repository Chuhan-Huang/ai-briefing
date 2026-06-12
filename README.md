# AI算力简报 · 自动每日更新

每天北京时间 08:00 自动用 Claude + 网络搜索生成一份AI算力投资简报，发布为一个公开网页。

---

## 部署步骤（只需做一次）

### 1. 在 GitHub 上新建一个仓库

打开 https://github.com/new

- Repository name: 比如 `ai-briefing`
- 选择 **Public**（GitHub Pages 免费版要求仓库公开；API Key 不会放在代码里，安全）
- 不要勾选 "Add a README file"
- 点击 **Create repository**

### 2. 把这些文件推送到仓库

在终端里：

```bash
cd ~/Downloads/ai-briefing-pages

git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/你的用户名/ai-briefing.git
git push -u origin main
```

如果 `git push` 时要求登录，按提示用浏览器登录你的 GitHub 账号即可。

### 3. 添加 API Key（作为 Secret，不会被任何人看到）

1. 打开仓库页面 → **Settings**
2. 左侧菜单 → **Secrets and variables** → **Actions**
3. 点击 **New repository secret**
4. Name 填：`ANTHROPIC_API_KEY`
5. Value 填：你的 API Key（`sk-ant-...`）
6. 点击 **Add secret**

### 4. 开启 GitHub Pages

1. 仓库页面 → **Settings** → **Pages**
2. **Source** 选择 **Deploy from a branch**
3. **Branch** 选择 `main`，文件夹选择 `/docs`
4. 点击 **Save**

几分钟后，页面顶部会显示你的网址，格式类似：
```
https://你的用户名.github.io/ai-briefing/
```

### 5. 手动触发第一次生成

1. 仓库页面 → **Actions** 标签
2. 左侧选择 **Daily Briefing**
3. 点击右侧 **Run workflow** 按钮 → 再点一次绿色的 **Run workflow**
4. 等待约1-2分钟，刷新页面看到绿色 ✓ 表示成功
5. 打开第4步拿到的网址，就能看到今天的简报了

---

## 日常使用

- **完全自动**：每天北京时间早上8点自动生成一次，之后无论你打开几次网页都是当天缓存内容，不会重复花钱
- **想立刻刷新**：去仓库的 Actions 页面，点 "Daily Briefing" → "Run workflow" 手动跑一次
- **修改简报内容/格式**：编辑 `generate.py` 里的 `SYSTEM_PROMPT` / `USER_PROMPT_TEMPLATE` / `render_body`，推送到 GitHub 后下次生成自动生效
- **修改网页样式**：编辑 `templates/briefing.html`

---

## 费用

- GitHub Pages + Actions：完全免费（公开仓库不限额）
- Anthropic API：每天调用一次，约 $0.10–0.20，$5 大约够用一个月

---

## 本地测试（可选）

```bash
pip3 install -r requirements.txt
ANTHROPIC_API_KEY="sk-ant-你的key" python3 generate.py
```

生成完打开 `docs/index.html` 即可在浏览器预览效果。
