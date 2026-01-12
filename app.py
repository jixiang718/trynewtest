from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Iterable

from flask import Flask, render_template, request
from PIL import Image
import pytesseract

app = Flask(__name__)


@dataclass(frozen=True)
class MenuItem:
    name: str
    price: float
    tags: tuple[str, ...]


TASTE_KEYWORDS = {
    "辣": "spicy",
    "麻": "numbing",
    "甜": "sweet",
    "酸": "sour",
    "咸": "salty",
    "清淡": "light",
    "香": "fragrant",
    "牛": "beef",
    "鸡": "chicken",
    "猪": "pork",
    "羊": "lamb",
    "鱼": "fish",
    "虾": "shrimp",
    "素": "vegetarian",
    "豆腐": "tofu",
    "蔬菜": "vegetable",
}


def extract_text(image_bytes: bytes) -> tuple[str, str | None]:
    try:
        image = Image.open(io.BytesIO(image_bytes))
    except OSError:
        return "", "无法读取图片，请确认上传的是有效的图片文件。"

    try:
        text = pytesseract.image_to_string(image, lang="chi_sim+eng")
    except pytesseract.TesseractNotFoundError:
        return (
            "",
            "OCR 服务未就绪：服务器未安装 Tesseract。请联系部署者安装后重试。",
        )
    except RuntimeError:
        return "", "OCR 处理失败，请尝试更清晰的图片或稍后再试。"

    return text, None


def derive_tags(name: str) -> tuple[str, ...]:
    tags = []
    for keyword, tag in TASTE_KEYWORDS.items():
        if keyword in name:
            tags.append(tag)
    return tuple(sorted(set(tags)))


def parse_menu(text: str) -> list[MenuItem]:
    items = []
    for line in text.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        match = re.search(r"(\d+(?:\.\d{1,2})?)", cleaned)
        if not match:
            continue
        price = float(match.group(1))
        name = cleaned[: match.start()].strip(" -—:：￥$·")
        if not name:
            continue
        items.append(MenuItem(name=name, price=price, tags=derive_tags(name)))
    return items


def normalize_keywords(raw: str) -> list[str]:
    if not raw:
        return []
    tokens = re.split(r"[,，、\s]+", raw)
    return [token.strip().lower() for token in tokens if token.strip()]


def score_item(item: MenuItem, tastes: Iterable[str], must_include: list[str]) -> int:
    score = 0
    name_lower = item.name.lower()
    for taste in tastes:
        if taste in name_lower or taste in item.tags:
            score += 2
    for ingredient in must_include:
        if ingredient in name_lower:
            score += 3
    return score


def recommend_items(
    items: list[MenuItem],
    tastes: list[str],
    must_include: list[str],
    avoid: list[str],
    min_price: float | None,
    max_price: float | None,
) -> list[MenuItem]:
    filtered = []
    for item in items:
        if min_price is not None and item.price < min_price:
            continue
        if max_price is not None and item.price > max_price:
            continue
        name_lower = item.name.lower()
        if any(term in name_lower for term in avoid):
            continue
        if must_include and not all(term in name_lower for term in must_include):
            continue
        filtered.append(item)

    scored = sorted(
        filtered,
        key=lambda item: (score_item(item, tastes, must_include), -item.price),
        reverse=True,
    )
    return scored[:8]


@app.route("/", methods=["GET", "POST"])
def index():
    recommendations: list[MenuItem] | None = None
    message = None
    raw_text = ""

    if request.method == "POST":
        uploaded = request.files.get("menu_image")
        if not uploaded or uploaded.filename == "":
            message = "请先上传菜单截图。"
        else:
            raw_text, error_message = extract_text(uploaded.read())
            if error_message:
                message = error_message
            elif not raw_text.strip():
                message = "没有识别到菜单内容，请换一张更清晰的截图再试。"
            else:
                items = parse_menu(raw_text)
                if not items:
                    message = "没有解析出菜品和价格，请尝试更清晰的截图或裁剪后再上传。"
                else:
                    tastes = normalize_keywords(request.form.get("tastes", ""))
                    must_include = normalize_keywords(request.form.get("must_include", ""))
                    avoid = normalize_keywords(request.form.get("avoid", ""))
                    min_price = request.form.get("min_price")
                    max_price = request.form.get("max_price")
                    min_price_value = float(min_price) if min_price else None
                    max_price_value = float(max_price) if max_price else None
                    recommendations = recommend_items(
                        items,
                        tastes=tastes,
                        must_include=must_include,
                        avoid=avoid,
                        min_price=min_price_value,
                        max_price=max_price_value,
                    )
                    if not recommendations:
                        message = "暂时没有符合条件的菜品，请调整口味或价格范围。"

    return render_template(
        "index.html",
        recommendations=recommendations,
        message=message,
        raw_text_preview="\n".join(raw_text.splitlines()[:12]),
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
