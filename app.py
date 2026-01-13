from __future__ import annotations

import base64
import io
import os
import re
import time
from dataclasses import dataclass
from typing import Iterable

from flask import Flask, render_template, request
from PIL import Image
import pytesseract
import requests

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


def extract_text_with_openai(image_bytes: bytes) -> tuple[str, str | None]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return "", "OCR 服务未就绪：未配置 OpenAI API Key。"

    encoded = base64.b64encode(image_bytes).decode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    responses_payload = {
        "model": "gpt-4o-mini",
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": "你是菜单 OCR 助手，只输出菜单文本原文，不要添加解释。",
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请提取图片中的菜单文本。"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{encoded}"},
                    },
                ],
            },
        ],
        "max_output_tokens": 1200,
        "temperature": 0,
    }
    chat_payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": "你是菜单 OCR 助手，只输出菜单文本原文，不要添加解释。",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请提取图片中的菜单文本。"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{encoded}"
                        },
                    },
                ],
            },
        ],
        "max_tokens": 1200,
        "temperature": 0,
    }
    try:
        response = _post_openai_with_retries(
            "https://api.openai.com/v1/responses",
            responses_payload,
            headers,
        )
        data = response.json()
        content = data.get("output_text", "").strip()
    except requests.RequestException:
        try:
            response = _post_openai_with_retries(
                "https://api.openai.com/v1/chat/completions",
                chat_payload,
                headers,
            )
            data = response.json()
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
        except requests.RequestException as exc:
            status = getattr(exc.response, "status_code", None)
            if status == 429:
                return (
                    "",
                    "OCR 服务请求过于频繁（HTTP 429）。请稍后再试或改用手动输入。",
                )
            if status:
                return (
                    "",
                    f"OCR 服务请求失败（HTTP {status}），请稍后再试或改用手动输入。",
                )
            return "", "OCR 服务请求失败，请稍后再试或改用手动输入。"
    if not content:
        return "", "OCR 服务未返回有效文本，请改用手动输入。"
    return content, None


def _post_openai_with_retries(
    url: str,
    payload: dict,
    headers: dict,
    *,
    retries: int = 2,
    timeout: int = 45,
) -> requests.Response:
    last_exc: requests.RequestException | None = None
    for attempt in range(retries + 1):
        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=timeout,
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_exc = exc
            status = getattr(exc.response, "status_code", None)
            if status == 429 and attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
    raise last_exc if last_exc else requests.RequestException("请求失败")


def extract_text(image_bytes: bytes) -> tuple[str, str | None]:
    try:
        image = Image.open(io.BytesIO(image_bytes))
    except OSError:
        return "", "无法读取图片，请确认上传的是有效的图片文件。"

    try:
        text = pytesseract.image_to_string(image, lang="chi_sim+eng")
    except (pytesseract.TesseractNotFoundError, pytesseract.TesseractError, RuntimeError):
        return extract_text_with_openai(image_bytes)

    if not text.strip():
        openai_text, error_message = extract_text_with_openai(image_bytes)
        if error_message:
            return "", error_message
        return openai_text, None

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
        manual_text = request.form.get("menu_text", "").strip()
        uploaded = request.files.get("menu_image")
        if manual_text:
            raw_text = manual_text
        elif not uploaded or uploaded.filename == "":
            message = "请上传菜单截图或手动输入菜单文字。"
        else:
            raw_text, error_message = extract_text(uploaded.read())
            if error_message:
                message = f"{error_message} 你也可以改用手动输入菜单文字。"
            elif not raw_text.strip():
                message = "没有识别到菜单内容，请换一张更清晰的截图再试。"

        if raw_text and not message:
            items = parse_menu(raw_text)
            if not items:
                if manual_text:
                    message = "没有解析出菜品和价格，请检查输入的菜单格式。"
                else:
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
