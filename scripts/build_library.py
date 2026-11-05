#!/usr/bin/env python3
"""Rebuild navigation and category pages from the public JSON data (Python 3.10+)."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ('en', 'es', 'pt', 'ja', 'ko', 'de', 'fr', 'tr', 'zh-TW', 'zh-CN', 'ru')
LANGUAGES = ('English', 'Español', 'Português', '日本語', '한국어', 'Deutsch', 'Français', 'Türkçe', '繁體中文', '简体中文', 'Русский')
SECTIONS = ('introduction', 'quick-start', 'news', 'menu', 'related-resources', 'acknowledge')

def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))

def readme_name(locale: str) -> str:
    return 'README.md' if locale == 'en' else f'README_{locale}.md'

def category_path(category: str, locale: str) -> str:
    return f'cases/{category}.md' if locale == 'en' else f'cases/{locale}/{category}.md'

def anchor(case: dict) -> str:
    return f'{case["category"]}-case-{case["number"]}'

def prompt_fence(prompt: str) -> str:
    runs = [len(m[0]) for m in re.finditer(r'`+', prompt)]
    fence = '`' * max(3, max(runs, default=0) + 1)
    return f'{fence}\n{prompt}\n{fence}'

def aspect_ratio(prompt: str) -> str:
    match = re.search(r'(\d+:\d+(?: or \d+:\d+)?) aspect ratio\.\s*$', prompt)
    if not match:
        raise ValueError('Prompt has no terminal aspect-ratio instruction')
    return match[1]

def badges() -> str:
    result = ['[![License: no public license granted](https://img.shields.io/badge/License-no_public_license_granted-lightgrey)](LICENSE)']
    for code, name in zip(LOCALES, LANGUAGES):
        label = quote(name.replace('-', '--'), safe='')
        result.append(f'[![{name}](https://img.shields.io/badge/{label}-blue)]({readme_name(code)})')
    return '\n'.join(result)

def render_readme(prompts: list, categories: list, ui: dict, locale: str) -> str:
    usage_path = 'docs/usage_zh-CN.md' if locale == 'zh-CN' else 'docs/usage.md'
    parts = ['<div align="center">', '', f'# {ui["name"]}', '', ui['tagline'], '', badges(), '', '</div>', '']
    def section(key: str, emoji: str):
        parts.extend([f'<a id="{key}"></a>', f'## {emoji} {ui["sections"][key]}', ''])
    section('introduction', '📚')
    parts.extend([ui['intro'], ''])
    section('quick-start', '⚡')
    parts.extend(f'{key}. {value}' for key, value in ui['quick_steps'].items())
    parts.extend(['', ui['quick_note'], '', f'[{ui["resources"]["usage"]}]({usage_path})', ''])
    section('news', '🗞️')
    parts.extend([ui['news'], ''])
    section('menu', '📑')
    parts.extend([ui['menu_intro'], ''])
    parts.extend(f'- [{ui["sections"][key]}](#{key})' for key in SECTIONS)
    parts.append('')
    for category in categories:
        rel = category_path(category, locale)
        selected = [p for p in prompts if p['category'] == category]
        parts.extend([f'**[{ui["categories"][category]}]({rel}) · {len(selected)} {ui["labels"]["templates"]}**', '', ui['category_descriptions'][category], ''])
        parts.extend(f'- [Case {p["number"]}: {ui["titles"][p["id"]]}]({rel}#{anchor(p)})' for p in selected)
        parts.append('')
    section('related-resources', '🔎')
    for key, path in [('usage', usage_path), ('maintenance', 'docs/maintenance.md'), ('data', 'data/prompts.json'), ('contributing', 'CONTRIBUTING.md')]:
        parts.append(f'- [{ui["resources"][key]}]({path})')
    parts.append('')
    section('acknowledge', '🙏')
    parts.extend([ui['acknowledge'], ''])
    return '\n'.join(parts)

def render_category(prompts: list, category: str, ui: dict, locale: str) -> str:
    selected = [p for p in prompts if p['category'] == category]
    back = '../README.md' if locale == 'en' else f'../../README_{locale}.md'
    parts = [f'# {ui["categories"][category]}', '', f'[{ui["labels"]["return"]}]({back})', '', ui['category_descriptions'][category], '', '<a id="category-menu"></a>', f'## 📑 {ui["labels"]["category_menu"]}', '']
    parts.extend(f'- [Case {p["number"]}: {ui["titles"][p["id"]]}](#{anchor(p)})' for p in selected)
    parts.extend(['', ui['labels']['prompt_note'], '', '---', ''])
    for p in selected:
        parts.extend([f'<a id="{anchor(p)}"></a>', f'### Case {p["number"]}: {ui["titles"][p["id"]]}', '', f'**{ui["labels"]["ratio"]}:** {aspect_ratio(p["prompt"])}', '', '**Prompt:**', '', prompt_fence(p['prompt']), '', '---', ''])
    parts.extend([f'[{ui["labels"]["return"]}]({back})', ''])
    return '\n'.join(parts)

def generated_files(root: Path = ROOT) -> dict[str, str]:
    payload = read_json(root/'data/prompts.json')
    layout = read_json(root/'data/content-layout.json')
    prompts = payload['prompts']; categories = layout['categories']
    files = {}
    for locale in LOCALES:
        ui_path = root/'data/locales'/f'{locale}.json'
        if not ui_path.is_file():
            continue
        ui = read_json(ui_path)
        files[readme_name(locale)] = render_readme(prompts, categories, ui, locale)
        for category in categories:
            files[category_path(category, locale)] = render_category(prompts, category, ui, locale)
    return files

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check generated content without changing files')
    args = parser.parse_args()
    files = generated_files()
    stale = []
    for rel, contents in files.items():
        path = ROOT/rel
        expected = contents.encode('utf-8')
        if args.check:
            if not path.is_file() or path.read_bytes() != expected:
                stale.append(rel)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(expected)
    if stale:
        print('Generated pages differ: ' + ', '.join(stale))
        return 1
    print(f'{"Checked" if args.check else "Built"} {len(files)} navigation/category pages.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
