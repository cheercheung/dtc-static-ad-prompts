#!/usr/bin/env python3
"""Validate the complete portable text library using only Python's standard library."""
from __future__ import annotations
import argparse
import collections
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit
sys.dont_write_bytecode = True
from build_library import ROOT, LOCALES, generated_files, read_json, readme_name, category_path, anchor

EXPECTED_COUNT = 40
FORBIDDEN_KEYS = {'source_path', 'source_url', 'original_number', 'provenance', 'author', 'source'}

def flatten(value, prefix=''):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from flatten(item, prefix + '.' + key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from flatten(item, prefix + '.' + str(index))
    else:
        yield prefix, value

def keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from keys(item)

def strip_fences(text):
    result=[];fence=None
    for line in text.splitlines():
        opening=re.fullmatch(r'(`{3,})([^`]*)', line)
        if fence is None and opening:
            fence=opening[1];continue
        if fence is not None:
            if re.fullmatch(re.escape(fence)+r'`*\s*',line):fence=None
            continue
        result.append(line)
    if fence is not None:raise ValueError('Unclosed code fence')
    return '\n'.join(result)

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--english-only', action='store_true', help='Check an English draft before localization')
    args=parser.parse_args(); errors=[]
    def need(condition, message):
        if not condition:errors.append(message)
    try:
        payload=read_json(ROOT/'data/prompts.json');prompts=payload['prompts']
        need(set(payload)=={'schema_version','prompts'} and payload['schema_version']==1,'Invalid canonical data schema')
        need(len(prompts)==EXPECTED_COUNT,'Expected exactly 40 prompts')
        need([p['number'] for p in prompts]==list(range(1,EXPECTED_COUNT+1)),'Case numbering must be 1–40 in canonical order')
        need(len({p['id'] for p in prompts})==EXPECTED_COUNT,'Stable IDs must be unique')
        need(len({p['prompt'] for p in prompts})==EXPECTED_COUNT,'Prompt bodies must be unique')
        for p in prompts:
            need(set(p)=={'id','number','category','subcategory','title','prompt'},f'Unexpected fields for {p["id"]}')
            need(p['subcategory'] is None,f'Unexpected subcategory for {p["id"]}')
            need(bool(p['prompt'].strip()) and p['prompt'].endswith('aspect ratio.'),f'Incomplete prompt {p["id"]}')
        layout=read_json(ROOT/'data/content-layout.json')
        need(set(layout)=={'schema_version','layout','categories'} and layout['schema_version']==1 and layout['layout']=='split-category','Invalid routing manifest')
        categories=list(dict.fromkeys(p['category'] for p in prompts))
        need(layout['categories']==categories,'Category manifest differs from canonical ordering')
        need(len(categories)==6 and all(re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', c) for c in categories),'Six safe categories required')
        en=read_json(ROOT/'data/locales/en.json');en_flat=dict(flatten(en))
        need(en['titles']=={p['id']:p['title'] for p in prompts},'English titles differ from canonical data')
        locales=('en',) if args.english_only else LOCALES
        expected_locale_files={f'{loc}.json' for loc in locales}
        actual_locale_files={p.name for p in (ROOT/'data/locales').glob('*.json')}
        need(expected_locale_files<=actual_locale_files if args.english_only else expected_locale_files==actual_locale_files,'Locale data set differs')
        for loc in locales:
            ui=read_json(ROOT/'data/locales'/f'{loc}.json');flat=dict(flatten(ui))
            need(set(flat)==set(en_flat),f'{loc}: UI schema differs')
            need(all(isinstance(v,str) and v.strip() for v in flat.values()),f'{loc}: every UI value must be nonempty text')
            need(set(ui['titles'])=={p['id'] for p in prompts} and len(set(ui['titles'].values()))==EXPECTED_COUNT,f'{loc}: title identities missing or duplicated')
            if loc!='en':
                need(all(ui['titles'][p['id']]!=en['titles'][p['id']] for p in prompts),f'{loc}: untranslated title')
        expected=generated_files()
        for rel,content in expected.items():
            need((ROOT/rel).is_file() and (ROOT/rel).read_bytes()==content.encode(),f'Generated content differs: {rel}')
        actual_cases={p.relative_to(ROOT).as_posix() for p in (ROOT/'cases').rglob('*.md')}
        expected_cases={category_path(c,loc) for loc in locales for c in categories}
        need(expected_cases<=actual_cases if args.english_only else actual_cases==expected_cases,'Category page set differs')
        baseline=('LICENSE','.gitignore','CONTRIBUTING.md','docs/usage.md','docs/maintenance.md','.github/PULL_REQUEST_TEMPLATE.md','.github/ISSUE_TEMPLATE/prompt_issue.yml','.github/ISSUE_TEMPLATE/translation_issue.yml','.github/workflows/validate-library.yml','scripts/build_library.py','scripts/verify_library.py')
        for rel in baseline:need((ROOT/rel).is_file() and (ROOT/rel).stat().st_size>0,f'Missing baseline file {rel}')
        for path in ROOT.rglob('*'):
            if '.git' in path.relative_to(ROOT).parts:continue
            need(not path.is_symlink(),f'Symlink forbidden: {path.relative_to(ROOT)}')
            if path.is_file() and path.suffix=='.json':need(not FORBIDDEN_KEYS.intersection(keys(read_json(path))),f'Private metadata in {path.relative_to(ROOT)}')
            if not path.is_file() or path.suffix!='.md':continue
            need(path.stat().st_size<450*1024,f'Oversized Markdown: {path.relative_to(ROOT)}')
            clean=strip_fences(path.read_text(encoding='utf-8'))
            need(not re.search(r'\b(?:TODO|TBD)\b|\{\{[^}]+\}\}',clean),f'Unfinished prose: {path.relative_to(ROOT)}')
            ids=re.findall(r'<a id="([^"]+)"></a>',clean)
            need(len(ids)==len(set(ids)),f'Duplicate anchor: {path.relative_to(ROOT)}')
            # Badge image URLs are decorative. Validate every functional local link.
            links=re.sub(r'!\[[^]]*\]\([^\s)]+\)','badge',clean)
            for _,href in re.findall(r'\[([^]\n]+)\]\(([^\s)]+)\)',links):
                parts=urlsplit(href)
                need(not parts.scheme,f'External functional link: {path.relative_to(ROOT)} -> {href}')
                if parts.scheme:continue
                dest=(path.parent/unquote(parts.path)).resolve() if parts.path else path
                need(dest.is_relative_to(ROOT),f'Escaping link: {path.relative_to(ROOT)} -> {href}')
                if args.english_only and dest.name in {readme_name(loc) for loc in LOCALES if loc!='en'}:continue
                need(dest.is_file(),f'Broken link: {path.relative_to(ROOT)} -> {href}')
                if parts.fragment and dest.is_file():need(f'<a id="{unquote(parts.fragment)}"></a>' in strip_fences(dest.read_text(encoding='utf-8')),f'Broken anchor: {path.relative_to(ROOT)} -> {href}')
    except (OSError,ValueError,KeyError,TypeError) as exc:
        errors.append(str(exc))
    if errors:
        print('\n'.join('ERROR: '+err for err in errors));return 1
    print(f'Validated 40 prompts across {len(locales)} language edition(s), {len(expected_cases)} category pages, generated bytes, local links, and repository data.')
    return 0

if __name__=='__main__':raise SystemExit(main())
