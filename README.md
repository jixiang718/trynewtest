# 点菜推荐助手

一个简单的点菜管理与推荐系统：上传菜单截图，结合口味、预算与忌口，生成合适的菜品推荐。

## 功能
- 上传菜单截图并自动识别菜名和价格
- 根据口味偏好、必点食材、忌口与价格范围筛选
- 输出推荐菜品列表与识别文本预览

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

浏览器打开 <http://localhost:8000>。

## 部署到 Vercel

1. 确保根目录包含 `vercel.json` 与 `api/index.py`。
2. 在 Vercel 新建项目并选择该仓库。
3. 使用默认设置部署即可，根路径 `/` 会被重写到 `/api/index`。
4. 部署环境需要安装 Tesseract OCR，否则可改用手动输入菜单文字。
5. 如需使用 OpenAI OCR 兜底，请在环境变量中配置 `OPENAI_API_KEY`，并在修改后重新部署以生效。

> 识别效果依赖于图片清晰度与 OCR 环境，推荐上传裁剪清晰的菜单截图。
