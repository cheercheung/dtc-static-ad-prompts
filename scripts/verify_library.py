#!/usr/bin/env python3
"""Validate portable prompt data, generated pages, image mappings, and local navigation."""
from __future__ import annotations
import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import struct
import sys
from urllib.parse import unquote,urlsplit
sys.dont_write_bytecode=True
from build_library import ROOT,LOCALES,generated_files,read_json,readme_name,category_path,anchor

EXPECTED_COUNT=40
MEDIA_PREFIX='https://pub-62cf7640cd0f4066b60933bd2e9b85ef.r2.dev/github-repo-media/dtc-static-ad-prompts/assets/examples/'
UI_KEYS={'gallery_title','gallery_intro','example_label','alternate_label','prompt_link','full_image_link','disclaimer'}
FORBIDDEN_KEYS={'source_path','source_url','original_number','provenance','author','source'}

def flatten(value,prefix=''):
    if isinstance(value,dict):
        for key,item in value.items():yield from flatten(item,prefix+'.'+key)
    else:yield prefix,value

def keys(value):
    if isinstance(value,dict):
        for key,item in value.items():yield key;yield from keys(item)
    elif isinstance(value,list):
        for item in value:yield from keys(item)

def fenced_content(text):
    visible=[];blocks=[];lines=text.splitlines(keepends=True);i=0
    while i<len(lines):
        opening=re.fullmatch(r'(`{3,})([^\n]*)\n',lines[i])
        if not opening:visible.append(lines[i]);i+=1;continue
        i+=1;body=[]
        while i<len(lines) and not re.fullmatch(r'`{'+str(len(opening[1]))+r',}[ \t]*(?:\n)?',lines[i]):body.append(lines[i]);i+=1
        if i==len(lines):raise ValueError('Unclosed code fence')
        raw=''.join(body)
        if raw.endswith('\n'):raw=raw[:-1]
        blocks.append((raw,opening[2].strip()));visible.append('\n');i+=1
    return ''.join(visible),blocks

def strip_fences(text):return fenced_content(text)[0]

class Markup(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.links=[];self.images=[];self.pairs=[];self.cells=[];self.current_cell=None;self.hrefs=[];self.rows=[];self.current_row=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='a':
            self.hrefs.append(a.get('href',''))
            if 'href' in a:self.links.append(a['href'])
            if self.current_cell is not None and 'href' in a:self.current_cell['links'].append(a['href'])
        elif tag=='img':
            self.images.append(a);self.pairs.append((a.get('src',''),self.hrefs[-1] if self.hrefs else ''))
            if self.current_cell is not None:self.current_cell['images'].append(a)
        elif tag=='tr':self.current_row=[]
        elif tag=='td':self.current_cell={'images':[],'links':[],'text':''}
    def handle_endtag(self,tag):
        if tag=='a' and self.hrefs:self.hrefs.pop()
        elif tag=='td' and self.current_cell is not None:
            self.cells.append(self.current_cell)
            if self.current_row is not None:self.current_row.append(self.current_cell)
            self.current_cell=None
        elif tag=='tr' and self.current_row is not None:self.rows.append(self.current_row);self.current_row=None
    def handle_data(self,data):
        if self.current_cell is not None:self.current_cell['text']+=data

def markup(text):
    p=Markup();p.feed(text);return p

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--english-only',action='store_true');args=parser.parse_args();errors=[]
    def need(ok,message):
        if not ok:errors.append(message)
    try:
        payload=read_json(ROOT/'data/prompts.json');prompts=payload['prompts']
        need(set(payload)=={'schema_version','prompts'} and payload['schema_version']==1,'Invalid canonical data schema')
        need(len(prompts)==40 and [p['number'] for p in prompts]==list(range(1,41)),'Exactly 40 ordered templates numbered 1–40 required')
        need(len({p['id'] for p in prompts})==40 and len({p['prompt'] for p in prompts})==40,'Prompt IDs and bodies must be unique')
        for p in prompts:
            need(set(p)=={'id','number','category','subcategory','title','prompt'} and p['subcategory'] is None,f'Unexpected prompt fields: {p["id"]}')
            need(bool(p['prompt'].strip()) and p['prompt'].endswith('aspect ratio.'),f'Incomplete prompt: {p["id"]}')
        layout=read_json(ROOT/'data/content-layout.json');categories=list(dict.fromkeys(p['category'] for p in prompts))
        need(set(layout)=={'schema_version','layout','categories'} and layout['schema_version']==1 and layout['layout']=='split-category' and layout['categories']==categories,'Invalid category layout')
        need(len(categories)==6 and all(re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',c) for c in categories),'Six safe categories required')
        media=read_json(ROOT/'data/examples.json');examples=media['examples']
        need(set(media)=={'schema_version','media_policy','prompt_presentation','examples'} and media['schema_version']==1 and media['media_policy']=='owner-provided-r2-static-images' and media['prompt_presentation']=='fenced','Invalid static example manifest')
        need(len(examples)==40,'Exactly 40 example-case mappings required')
        urls=[];hashes=[]
        for p,e in zip(prompts,examples):
            need(set(e)=={'prompt_id','case_number','category','outputs'} and (e['prompt_id'],e['case_number'],e['category'])==(p['id'],p['number'],p['category']),f'Example case identity differs: {p["id"]}')
            outputs=e['outputs'];roles=[o['role'] for o in outputs]
            need(roles==(['main','alternate'] if p['number']==37 else ['main']),f'Unexpected example roles/count: {p["id"]}')
            for o in outputs:
                need(set(o)=={'role','url','sha256','width','height','mime_type'},f'Unexpected image metadata: {p["id"]}')
                need(isinstance(o['sha256'],str) and re.fullmatch(r'[0-9a-f]{64}',o['sha256']),f'Invalid image SHA: {p["id"]}')
                need(o['mime_type']=='image/png' and all(type(o[k]) is int and o[k]>0 for k in ('width','height')),f'Invalid PNG dimensions/type: {p["id"]}')
                need(o['url']==MEDIA_PREFIX+f'case{p["number"]:02d}-{o["role"]}-{o["sha256"][:12]}.png',f'Image URL is not the declared repository object: {p["id"]}')
                urls.append(o['url']);hashes.append(o['sha256'])
        need(len(urls)==41 and len(set(urls))==41 and len(set(hashes))==41,'41 unique original PNG outputs required')
        allowed_media=set(urls)
        example_ui=read_json(ROOT/'data/examples-ui.json')
        need(set(example_ui)=={'schema_version','locales'} and example_ui['schema_version']==1 and set(example_ui['locales'])==set(LOCALES),'Invalid eleven-language example UI')
        for loc,x in example_ui['locales'].items():need(set(x)==UI_KEYS and all(isinstance(v,str) and v.strip() for v in x.values()),f'{loc}: complete nonempty example UI required')
        banner=(ROOT/'assets/banner.png').read_bytes()
        need(banner[:8]==b'\x89PNG\r\n\x1a\n' and len(banner)>33,'Missing PNG banner')
        width,height=struct.unpack('>II',banner[16:24])
        need(width>0 and height>0 and abs(width*2-height*5)<=2,'Banner must have 5:2 proportions within integer-pixel rounding')
        en=read_json(ROOT/'data/locales/en.json');en_flat=dict(flatten(en));locales=('en',) if args.english_only else LOCALES
        need(en['titles']=={p['id']:p['title'] for p in prompts},'English titles differ from canonical data')
        need({f'{loc}.json' for loc in LOCALES}=={p.name for p in (ROOT/'data/locales').glob('*.json')},'Locale data set differs')
        for loc in locales:
            ui=read_json(ROOT/'data/locales'/f'{loc}.json');flat=dict(flatten(ui))
            need(set(flat)==set(en_flat) and all(isinstance(v,str) and v.strip() for v in flat.values()),f'{loc}: locale UI schema differs')
            need(set(ui['titles'])=={p['id'] for p in prompts} and len(set(ui['titles'].values()))==40,f'{loc}: title identities missing or duplicated')
            if loc!='en':need(all(ui['titles'][p['id']]!=en['titles'][p['id']] for p in prompts),f'{loc}: untranslated title')
            readme=(ROOT/readme_name(loc)).read_text(encoding='utf-8');clean=strip_fences(readme)
            need(readme.count('](assets/banner.png)')==1,f'{loc}: expected one shared banner')
            need('<a id="static-examples"></a>' in clean and '](#static-examples)' in clean,f'{loc}: gallery anchor/menu missing')
            gallery=clean.split('<a id="static-examples"></a>',1)[1].split('<a id="related-resources"></a>',1)[0];parsed=markup(gallery)
            need(len(parsed.cells)==40 and len(parsed.rows)==20 and all(len(row)==2 for row in parsed.rows),f'{loc}: gallery must be twenty real two-cell rows')
            for p,e,cell in zip(prompts,examples,parsed.cells):
                url=e['outputs'][0]['url'];dest=category_path(p['category'],loc)+'#'+anchor(p)
                need(len(cell['images'])==1 and cell['images'][0].get('src')==url and url in cell['links'] and dest in cell['links'] and bool(cell['text'].strip()),f'{loc}: gallery mapping differs for {p["id"]}')
            need(parsed.pairs==[(e['outputs'][0]['url'],e['outputs'][0]['url']) for e in examples],f'{loc}: gallery image/full-size pairing differs')
            for category in categories:
                rel=category_path(category,loc);page=(ROOT/rel).read_text(encoding='utf-8');outside,bodies=fenced_content(page);selected=[p for p in prompts if p['category']==category]
                need(bodies==[(p['prompt'],'') for p in selected],f'{rel}: complete prompt bytes differ')
                expected_outputs=[o for p,e in zip(prompts,examples) if p['category']==category for o in e['outputs']]
                parsed=markup(outside)
                need(parsed.pairs==[(o['url'],o['url']) for o in expected_outputs],f'{rel}: case images missing, extra, reordered or linked incorrectly')
                for p in selected:
                    need(f'### Case {p["number"]}: {ui["titles"][p["id"]]}' in outside and f'<a id="{anchor(p)}"></a>' in outside,f'{rel}: case heading/anchor differs')
                need(outside.count('**'+example_ui['locales'][loc]['example_label']+':**')==len(selected),f'{rel}: main image labels differ')
                need(outside.count('**'+example_ui['locales'][loc]['alternate_label']+':**')==(1 if category==prompts[36]['category'] else 0),f'{rel}: alternate image labels differ')
        expected=generated_files()
        for rel,content in expected.items():need((ROOT/rel).is_file() and (ROOT/rel).read_bytes()==content.encode('utf-8'),f'Generated content differs: {rel}')
        need({p.relative_to(ROOT).as_posix() for p in (ROOT/'cases').rglob('*.md')}=={category_path(c,l) for l in LOCALES for c in categories},'Category page set differs')
        for rel in ('LICENSE','.gitignore','CONTRIBUTING.md','docs/usage.md','docs/maintenance.md','.github/PULL_REQUEST_TEMPLATE.md','.github/ISSUE_TEMPLATE/prompt_issue.yml','.github/ISSUE_TEMPLATE/translation_issue.yml','.github/workflows/validate-library.yml','scripts/build_library.py','scripts/verify_library.py'):
            need((ROOT/rel).is_file() and (ROOT/rel).stat().st_size>0,f'Missing baseline file: {rel}')
        def verify_link(path,href):
            parts=urlsplit(href)
            if parts.scheme:
                need(href in allowed_media,f'Undeclared external functional link: {path.relative_to(ROOT)} -> {href}')
                return
            dest=(path.parent/unquote(parts.path)).resolve() if parts.path else path
            need(dest.is_relative_to(ROOT) and dest.is_file(),f'Broken/escaping link: {path.relative_to(ROOT)} -> {href}')
            if parts.fragment and dest.is_file():need(f'<a id="{unquote(parts.fragment)}"></a>' in strip_fences(dest.read_text(encoding='utf-8')),f'Broken anchor: {path.relative_to(ROOT)} -> {href}')
        for path in ROOT.rglob('*'):
            if '.git' in path.relative_to(ROOT).parts:continue
            need(not path.is_symlink(),f'Symlink forbidden: {path.relative_to(ROOT)}')
            if path.is_file() and path.suffix=='.json':need(not FORBIDDEN_KEYS.intersection(keys(read_json(path))),f'Private metadata in {path.relative_to(ROOT)}')
            if not path.is_file() or path.suffix!='.md':continue
            need(path.stat().st_size<450*1024,f'Oversized Markdown: {path.relative_to(ROOT)}');clean=strip_fences(path.read_text(encoding='utf-8'))
            need(not re.search(r'\b(?:TODO|TBD)\b|\{\{[^}]+\}\}',clean),f'Unfinished prose: {path.relative_to(ROOT)}')
            ids=re.findall(r'<a id="([^"]+)"></a>',clean);need(len(ids)==len(set(ids)),f'Duplicate anchor: {path.relative_to(ROOT)}')
            parsed=markup(clean)
            for image in parsed.images:need(image.get('src') in allowed_media,f'Undeclared HTML image: {path.relative_to(ROOT)}')
            for href in parsed.links:verify_link(path,href)
            links=re.sub(r'!\[[^]]*\]\([^\s)]+\)','badge',clean)
            for _,href in re.findall(r'\[([^]\n]+)\]\(([^\s)]+)\)',links):verify_link(path,href)
    except (OSError,ValueError,KeyError,TypeError,struct.error) as exc:errors.append(str(exc))
    if errors:print('\n'.join('ERROR: '+error for error in errors));return 1
    print(f'Validated 40 exact prompt bodies across {len(locales)} language edition(s), 41 mapped PNG outputs, 40-cell galleries, the shared 5:2 banner, generated bytes, and local links. Remote bytes and semantic translation review require separate publication audits.')
    return 0

if __name__=='__main__':raise SystemExit(main())
