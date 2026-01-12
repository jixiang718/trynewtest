# 点菜推荐助手

一个简单的点菜管理与推荐系统：上传菜单截图，结合口味、预算与忌口，生成合适的菜品推荐！

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

> 识别效果依赖于图片清晰度与 OCR 环境，推荐上传裁剪清晰的菜单截图。
