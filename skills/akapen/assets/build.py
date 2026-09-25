#!/usr/bin/env python3
"""akapen 標準モード — ソース Markdown (.akapen.md) から自己完結の赤ペンシート HTML を作る。

  python3 build.py <topic-01.akapen.md> -o ./akapen/<topic>-01.html [--check] [--hosted]

- ソースの書式は references/source-format.md、図の DSL は references/fig-dsl.md
- 固定の CSS / JS (このディレクトリの sheet.css, sheet.js, fig.css, fig-layout.js) を埋め込む。agent はソースだけ書く
- 図は「文字は HTML、線は SVG」。箱の高さと線の座標はブラウザで実測して決める (fig-layout.js)
- 検査 (問の数・根拠・推奨・fig 参照・箱の幅・生 SVG の文字あふれ推定) の結果を stderr に出す。--check は検査だけ
- 標準ライブラリだけで動く (python3.8 以上)
"""
import argparse, html, json, re, sys, base64, mimetypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
WARN = []
ERR = []

def warn(msg): WARN.append(msg)
def err(msg): ERR.append(msg)
def esc(s): return html.escape(s, quote=False)
def attr(s): return html.escape(s, quote=True)

# ---------------------------------------------------------------- inline markdown
def inline(s):
    s = esc(s)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'==([^=]+)==', r'<span class="red">\1</span>', s)
    s = re.sub(r'~~([^~]+)~~', r'<del>\1</del>', s)
    s = re.sub(r'\[([^\]]+)\]\((https?://[^)\s]+|file://[^)\s]+)\)', r'<a href="\2" target="_blank">\1</a>', s)
    return s

# ---------------------------------------------------------------- frontmatter
def parse_frontmatter(text):
    m = re.match(r'---\n(.*?)\n---\n?', text, re.S)
    if not m:
        err('frontmatter (--- で囲んだ label/date/title/reader) が無い'); return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        line = re.sub(r'\s+#.*$', '', line)
        if ':' in line:
            k, _, v = line.partition(':'); fm[k.strip()] = v.strip()
    return fm, text[m.end():]

# ---------------------------------------------------------------- block splitter
FENCE = re.compile(r'^```(\w+)([^\n]*)\n(.*?)^```\s*$', re.S | re.M)

def split_blocks(body):
    """[('md', text) | ('fence', type, args, body)] の列に分ける"""
    out, pos = [], 0
    for m in FENCE.finditer(body):
        if m.start() > pos:
            out.append(('md', body[pos:m.start()]))
        out.append(('fence', m.group(1), m.group(2).strip(), m.group(3)))
        pos = m.end()
    if pos < len(body):
        out.append(('md', body[pos:]))
    return out

# ---------------------------------------------------------------- markdown → html (最小)
def render_md(text, ctx):
    lines = text.split('\n')
    out, i = [], 0
    def para_end(j):
        while j < len(lines) and lines[j].strip() and not re.match(r'^(#{1,3} |- |\||```)', lines[j]): j += 1
        return j
    while i < len(lines):
        ln = lines[i]
        if not ln.strip() or ln.lstrip().startswith('<!--'):
            i += 1; continue
        if ln.startswith('### '): out.append(f'<h3>{inline(ln[4:])}</h3>'); i += 1; continue
        if ln.startswith('## '): out.append(f'<h2>{inline(ln[3:])}</h2>'); i += 1; continue
        if ln.startswith('# '): i += 1; continue  # タイトルは frontmatter
        if ln.startswith('結論:'):
            j = para_end(i); txt = ' '.join(l.strip() for l in lines[i:j])[3:].strip()
            ctx['concl'] = True
            if len(re.findall(r'[。.!?]', txt)) > 4: warn('結論が 4 文以上 (3 文以内に)')
            out.append(f'<div class="concl"><b>結論:</b> {inline(txt)}</div>'); i = j; continue
        if ln.startswith('用語:'):
            j = i + 1; items = []
            while j < len(lines) and lines[j].startswith('- '): items.append(inline(lines[j][2:])); j += 1
            out.append('<div class="gl"><b>このシートで使う言葉</b><br>' + '<br>'.join(items) + '</div>'); i = j; continue
        if ln.startswith('- '):
            j = i; items = []
            while j < len(lines) and (lines[j].startswith('- ') or lines[j].startswith('  ')):
                if lines[j].startswith('- '): items.append([lines[j][2:], []])
                elif items and lines[j].strip().startswith('- '): items[-1][1].append(lines[j].strip()[2:])
                elif items: items[-1][0] += ' ' + lines[j].strip()
                j += 1
            lis = []
            for t, subs in items:
                sub = '<ul>' + ''.join(f'<li>{inline(s)}</li>' for s in subs) + '</ul>' if subs else ''
                lis.append(f'<li>{inline(t)}{sub}</li>')
            out.append('<ul>' + ''.join(lis) + '</ul>'); i = j; continue
        if ln.startswith('|'):
            j = i; rows = []
            while j < len(lines) and lines[j].startswith('|'): rows.append(lines[j]); j += 1
            out.append(render_table(rows)); i = j; continue
        j = para_end(i)
        if j == i: j = i + 1
        out.append(f'<p>{inline(" ".join(l.strip() for l in lines[i:j]))}</p>'); i = j
    return '\n'.join(out)

def render_table(rows):
    cells = [[c.strip() for c in r.strip().strip('|').split('|')] for r in rows]
    cells = [r for r in cells if not all(re.match(r'^:?-+:?$', c) for c in r)]
    if not cells: return ''
    h = '<table><tr>' + ''.join(f'<th>{inline(c)}</th>' for c in cells[0]) + '</tr>'
    for r in cells[1:]:
        hl = r and r[0].startswith('!')
        if hl: r = [r[0][1:].strip()] + r[1:]
        h += '<tr' + (' class="hl"' if hl else '') + '>' + ''.join(
            f'<td class="n">{inline(c)}</td>' if re.match(r'^[\d,.\-〜~%円秒msKB ]+$', c) and any(ch.isdigit() for ch in c) else f'<td>{inline(c)}</td>' for c in r) + '</tr>'
    return h + '</table>'

# ---------------------------------------------------------------- fig DSL
def parse_fig(args, body, kind='fig'):
    parts = args.split()
    if not parts: err(f'{kind} ブロックに id が無い'); parts = ['noid']
    fig = {'kind': kind, 'id': parts[0], 'w': 720.0, 'fs': 11.0, 'title': '', 'caption': '', 'nodes': [], 'edges': [], 'marks': [], 'static': [], 'raw': ''}
    for k, v in re.findall(r'(\w+)=(\S+)', ' '.join(parts[1:])):
        if k in ('w', 'fs'): fig[k] = float(v)
    cur = None
    for raw in body.splitlines():
        if not raw.strip(): continue
        if raw[0] in ' \t' and cur is not None: cur['lines'].append(raw.strip()); continue
        line = raw.strip()
        if line.startswith('title:'): fig['title'] = line[6:].strip(); cur = None
        elif line.startswith('caption:'): fig['caption'] = line[8:].strip(); cur = None
        elif line.startswith(('node ', 'note ')):
            spec, _, heading = line[5:].partition('|'); p = spec.split()
            try: n = {'kind': line[:4], 'id': p[0], 'x': float(p[1]), 'y': float(p[2]), 'w': float(p[3])}
            except (IndexError, ValueError): err(f'fig {fig["id"]}: node/note は「id x y 幅」: {line}'); continue
            flags = p[4:]
            n.update({'heading': heading.strip(), 'lines': [], 'red': 'red' in flags, 'dashed': 'dashed' in flags, 'zone': 'zone' in flags,
                      'in': next((f[3:] for f in flags if f.startswith('in=')), None)})
            fig['nodes'].append(n); cur = n
        elif line.startswith('edge '):
            cur = None; rest = line[5:]; label = None
            lm = re.search(r'"([^"]*)"\s*$', rest)
            if lm: label = lm.group(1); rest = rest[:lm.start()]
            a, _, b = rest.partition('->'); bp = b.split()
            if not bp: err(f'fig {fig["id"]}: edge は「a:辺 -> b:辺」: {line}'); continue
            fig['edges'].append({'from': a.strip(), 'to': bp[0], 'label': label, 'red': 'red' in bp, 'dashed': 'dashed' in bp,
                                 'noarrow': 'noarrow' in bp, 'route': next((f for f in bp if f in ('straight', 'curve', 'wrap')), 'ortho')})
        elif line.startswith('mark '):
            cur = None; p = line[5:].split()
            try: fig['marks'].append({'n': p[0], 'at': p[1], 'dx': float(p[2]), 'dy': float(p[3])})
            except (IndexError, ValueError): err(f'fig {fig["id"]}: mark は「番号 nodeId dx dy」: {line}')
        elif line.split()[0] in ('axis', 'dot', 'vline', 'hline', 'bars'):
            cur = None; fig['static'].append(line.split())
        else:
            err(f'fig {fig["id"]}: 読めない行: {line}')
    # 検査
    ids = {n['id'] for n in fig['nodes']}
    for n in fig['nodes']:
        if n['x'] + n['w'] > fig['w'] + 0.5: warn(f'fig {fig["id"]}: 箱 {n["id"]} が右端を超える (x+w={n["x"]+n["w"]:g} > {fig["w"]:g})')
        if n['in'] and n['in'] not in ids: err(f'fig {fig["id"]}: in={n["in"]} の zone が無い')
        if n['w'] < 40: warn(f'fig {fig["id"]}: 箱 {n["id"]} の幅 {n["w"]:g} は狭すぎて 1 文字ずつ折れる')
    for e in fig['edges']:
        for end in (e['from'], e['to']):
            if end.split(':')[0] not in ids: err(f'fig {fig["id"]}: edge の {end} が無い')
    for m in fig['marks']:
        if m['at'] not in ids: err(f'fig {fig["id"]}: mark {m["n"]} の {m["at"]} が無い')
    return fig

def static_svg(items, fid):
    out = []
    for p in items:
        k = p[0]; red = 'red' in p; dashed = 'dashed' in p
        col = '#DC2626' if red else '#64707C'
        dash = ' stroke-dasharray="3 2"' if dashed else ''
        try:
            if k == 'axis':
                out.append(f'<line x1="{float(p[1]):g}" y1="{float(p[2]):g}" x2="{float(p[3]):g}" y2="{float(p[2]):g}" stroke="#64707C" stroke-width="1.2" marker-end="url(#ah-{attr(fid)})"/>')
            elif k == 'dot':
                out.append(f'<circle cx="{float(p[1]):g}" cy="{float(p[2]):g}" r="4" fill="{col}"/>')
            elif k == 'vline':
                out.append(f'<line x1="{float(p[1]):g}" y1="{float(p[2]):g}" x2="{float(p[1]):g}" y2="{float(p[3]):g}" stroke="{col}" stroke-width="1.2"{dash}/>')
            elif k == 'hline':
                out.append(f'<line x1="{float(p[1]):g}" y1="{float(p[2]):g}" x2="{float(p[3]):g}" y2="{float(p[2]):g}" stroke="{col}" stroke-width="1.2"{dash}/>')
            elif k == 'bars':
                x, y, w, gap = float(p[1]), float(p[2]), float(p[3]), float(p[4])
                for i, h in enumerate(p[5].split(',')):
                    h = float(h)
                    out.append(f'<rect x="{x + i*(w+gap):g}" y="{y-h:g}" width="{w:g}" height="{h:g}" fill="{"#FCA5A5" if red else "#CBD5E1"}"/>')
        except (IndexError, ValueError):
            err(f'fig {fid}: {k} の引数が足りない: {" ".join(p)}')
    return '<g class="static">' + ''.join(out) + '</g>' if out else ''

def render_fig(fig, inst=''):
    fid = fig['id'] + (f'-{inst}' if inst else '')
    if fig['kind'] == 'svg':
        return (f'<figure class="rawsvg" id="fig-{attr(fid)}" style="max-width:{fig["w"]:g}px">{fig["raw"]}' + (f'<figcaption>{inline(fig["caption"])}</figcaption>' if fig['caption'] else '') + '</figure>')
    if fig['kind'] == 'seq':
        return render_seq(fig, fid)
    if fig['kind'] == 'shot':
        return render_shot(fig, fid)
    out = [f'<figure class="fig" id="fig-{attr(fid)}" data-w="{fig["w"]:g}"><div class="fwrap"><div class="fcanvas" style="font-size:{fig["fs"]:g}px">']
    out.append('<svg class="lines"><defs>'
               f'<marker id="ah-{attr(fid)}" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#64707C"/></marker>'
               f'<marker id="ahr-{attr(fid)}" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#DC2626"/></marker>'
               '</defs>' + static_svg(fig['static'], fid) + '</svg>')
    if fig['title']: out.append(f'<div class="ttl">{inline(fig["title"])}</div>')
    for n in fig['nodes']:
        cls = ['node' if n['kind'] == 'node' else 'note'] + [c for c, f in (('r', 'red'), ('dashed', 'dashed'), ('zone', 'zone')) if n[f]]
        a = f'class="{" ".join(cls)}" id="{attr(fid)}-{attr(n["id"])}" data-x="{n["x"]:g}" data-y="{n["y"]:g}" data-w="{n["w"]:g}"'
        if n['in']: a += f' data-in="{attr(fid)}-{attr(n["in"])}"'
        body = [f'<span class="rd">{inline(l[1:].strip())}</span>' if l.startswith('!') else inline(l) for l in n['lines']]
        hd = n['heading']
        h = (f'<b class="rd">{inline(hd[1:].strip())}</b>' if hd.startswith('!') else f'<b>{inline(hd)}</b>') if hd else ''
        out.append(f'<div {a}>{h}{"<br>".join(body)}</div>')
    for m in fig['marks']:
        out.append(f'<span class="mark" data-at="{attr(fid)}-{attr(m["at"])}" data-dx="{m["dx"]:g}" data-dy="{m["dy"]:g}">{esc(m["n"])}</span>')
    for e in fig['edges']:
        a = f'data-from="{attr(fid + "-" + e["from"])}" data-to="{attr(fid + "-" + e["to"])}" data-route="{e["route"]}"'
        for k, f in (('data-red', 'red'), ('data-dash', 'dashed'), ('data-noarrow', 'noarrow')):
            if e[f]: a += f' {k}="1"'
        if e['label']: a += f' data-label="{attr(e["label"])}"'
        out.append(f'<i class="edge" {a}></i>')
    out.append('</div></div>')
    if fig['caption']: out.append(f'<figcaption>{inline(fig["caption"])}</figcaption>')
    out.append('</figure>')
    return '\n'.join(out)

# ---------------------------------------------------------------- seq (シーケンス図: 座標なし)
def parse_seq(args, body):
    fig = parse_fig(args.split()[0] if args else '', '', 'seq')
    for k, v in re.findall(r'(\w+)=(\S+)', args):
        if k in ('w', 'fs'): fig[k] = float(v)
    fig['w'] = fig['w'] if 'w=' in args else 360.0
    fig['fs'] = fig['fs'] if 'fs=' in args else 10.5
    fig['actors'] = []; fig['items'] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line: continue
        if line.startswith('title:'): fig['title'] = line[6:].strip()
        elif line.startswith('caption:'): fig['caption'] = line[8:].strip()
        elif line.startswith('actors:'): fig['actors'] = [a.strip() for a in line[7:].split(',') if a.strip()]
        elif line.startswith('note '):
            who, _, txt = line[5:].partition(':'); txt, _, flags = txt.partition('|')
            fig['items'].append({'kind': 'note', 'at': who.strip(), 'text': txt.strip(), 'red': 'red' in flags})
        elif line.startswith('gap'):
            fig['items'].append({'kind': 'gap'})
        elif '->' in line:
            ab, _, txt = line.partition(':'); a, _, b = ab.partition('->'); txt, _, flags = txt.partition('|')
            fig['items'].append({'kind': 'msg', 'a': a.strip(), 'b': b.strip(), 'text': txt.strip(), 'red': 'red' in flags, 'dashed': 'dashed' in flags})
        else: err(f'seq {fig["id"]}: 読めない行: {line}')
    if len(fig['actors']) < 2: err(f'seq {fig["id"]}: actors: に参加者を 2 つ以上')
    for it in fig['items']:
        for who in [it.get('a'), it.get('b'), it.get('at')]:
            if who and who not in fig['actors']: err(f'seq {fig["id"]}: 参加者 {who} が actors: に無い')
    return fig

def render_seq(fig, fid):
    n = max(len(fig['actors']), 1); col = lambda i: (i + 0.5) / n * 100
    idx = {a: i for i, a in enumerate(fig['actors'])}
    out = [f'<figure class="fig seq" id="fig-{attr(fid)}" style="font-size:{fig["fs"]:g}px;max-width:{fig["w"]:g}px">']
    if fig['title']: out.append(f'<div class="ttl">{inline(fig["title"])}</div>')
    out.append('<div class="actors">' + ''.join(f'<div class="actor" style="left:{col(i):.2f}%">{inline(a)}</div>' for i, a in enumerate(fig['actors'])) + '</div>')
    out.append('<div class="lanes">' + ''.join(f'<i class="life" style="left:{col(i):.2f}%"></i>' for i in range(n)))
    for it in fig['items']:
        if it['kind'] == 'gap': out.append('<div class="gap"></div>'); continue
        if it['kind'] == 'note':
            c = col(idx.get(it['at'], 0)); w = 100 / n * 0.9
            out.append(f'<div class="snote{" r" if it["red"] else ""}" style="left:{max(0, c - w/2):.2f}%;width:{w:.2f}%">{inline(it["text"])}</div>'); continue
        ia, ib = idx.get(it['a'], 0), idx.get(it['b'], 0)
        l, r = col(min(ia, ib)), col(max(ia, ib)); direction = 'l2r' if ib > ia else 'r2l'
        cls = 'msg ' + direction + (' r' if it['red'] else '') + (' dashed' if it['dashed'] else '')
        out.append(f'<div class="{cls}" style="left:{l:.2f}%;width:{r - l:.2f}%"><div class="lbl">{inline(it["text"])}</div></div>')
    out.append('</div>')
    if fig['caption']: out.append(f'<figcaption>{inline(fig["caption"])}</figcaption>')
    out.append('</figure>')
    return '\n'.join(out)

# ---------------------------------------------------------------- shot (スクショ + 赤の overlay)
def parse_shot(args, body, src_dir):
    fig = parse_fig(args.split()[0] if args else '', '', 'shot'); fig['w'] = 720.0
    fig['src'] = ''; fig['shotmarks'] = []; fig['alt'] = ''
    for raw in body.splitlines():
        line = raw.strip()
        if not line: continue
        if line.startswith('src:'): fig['src'] = line[4:].strip()
        elif line.startswith('alt:'): fig['alt'] = line[4:].strip()
        elif line.startswith('caption:'): fig['caption'] = line[8:].strip()
        elif line.startswith('mark '):
            m = re.match(r'mark\s+(\S+)\s+([\d.]+)%?\s+([\d.]+)%?(?:\s+"([^"]*)")?', line)
            if m: fig['shotmarks'].append({'n': m.group(1), 'x': float(m.group(2)), 'y': float(m.group(3)), 'label': m.group(4)})
            else: err(f'shot {fig["id"]}: mark は「番号 x% y% "ラベル"」: {line}')
        else: err(f'shot {fig["id"]}: 読めない行: {line}')
    if not fig['src']: err(f'shot {fig["id"]}: src: が無い')
    elif not fig['src'].startswith(('data:', 'https://')):
        p = (src_dir / fig['src']).resolve()
        if not p.is_file(): err(f'shot {fig["id"]}: 画像が無い: {p}')
        else:
            mt = mimetypes.guess_type(str(p))[0] or 'image/png'
            fig['src'] = f'data:{mt};base64,' + base64.b64encode(p.read_bytes()).decode('ascii')
            if p.stat().st_size > 1_500_000: warn(f'shot {fig["id"]}: 画像が {p.stat().st_size//1000}KB — 縮小を検討 (シートが重くなる)')
    return fig

def render_shot(fig, fid):
    out = [f'<figure class="shot" id="fig-{attr(fid)}"><div class="shotwrap"><img src="{attr(fig["src"])}" alt="{attr(fig["alt"] or fig["caption"])}">']
    for m in fig['shotmarks']:
        out.append(f'<span class="mark" style="left:{m["x"]:g}%;top:{m["y"]:g}%">{esc(m["n"])}</span>')
        if m['label']: out.append(f'<span class="lbl" style="left:{m["x"]:g}%;top:{m["y"] + 6:g}%">{esc(m["label"])}</span>')
    out.append('</div>')
    if fig['caption']: out.append(f'<figcaption>{inline(fig["caption"])}</figcaption>')
    out.append('</figure>')
    return '\n'.join(out)

# ---------------------------------------------------------------- svg (生 SVG の逃げ道)
def parse_rawsvg(args, body):
    fig = parse_fig(args.split()[0] if args else '', '', 'svg')
    lines = body.splitlines(); raw = []
    for line in lines:
        if line.strip().startswith('caption:') and not raw: fig['caption'] = line.strip()[8:].strip()
        else: raw.append(line)
    fig['raw'] = '\n'.join(raw).strip()
    m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', fig['raw'])
    if not fig['raw'].startswith('<svg') or not m: err(f'svg {fig["id"]}: <svg viewBox="0 0 W H"> で始める')
    else:
        W = float(m.group(1)); fig['w'] = W; over = 0
        for tm in re.finditer(r'<text([^>]*)>([^<]*)</text>', fig['raw']):
            x = re.search(r'\bx="([\d.]+)"', tm.group(1)); x = float(x.group(1)) if x else 0
            fs = re.search(r'font-size="([\d.]+)"', tm.group(1)) or re.search(r'(\d+(?:\.\d+)?)px', tm.group(1)); fs = float(fs.group(1)) if fs else 11
            if x + len(tm.group(2)) * fs * 0.95 > W: over += 1
        warn(f'svg {fig["id"]}: 生 SVG (文字のはみ出し検査は推定)' + (f' — はみ出しそうな text が {over} 本' if over else ''))
    return fig

# ---------------------------------------------------------------- q (問い)
def parse_q(body, qno):
    q = {'no': qno, 'text': '', 'opts': [], 'evidence': '', 'numbers': '', 'extra': []}
    for raw in body.splitlines():
        line = raw.strip()
        if not line: continue
        if not q['text']:
            q['text'] = re.sub(r'^問\s*\d+[.．]\s*', '', line); continue
        m = re.match(r'^([A-Z])(\*?)\s+(.*)$', line)
        if m and m.group(1) not in ('X',) and '|' in line or (m and not q['opts']):
            segs = [s.strip() for s in m.group(3).split('|')]
            o = {'id': m.group(1), 'rec': m.group(2) == '*', 'label': segs[0], 'pro': '', 'con': '', 'fig': None, 'desc': []}
            for s in segs[1:]:
                if s.startswith('利点:'): o['pro'] = s[3:].strip()
                elif s.startswith('代償:'): o['con'] = s[3:].strip()
                elif s.startswith('fig:'): o['fig'] = s[4:].strip()
                elif s: o['desc'].append(s)
            q['opts'].append(o); continue
        if line.startswith('根拠:'): q['evidence'] = line[3:].strip()
        elif line.startswith('数値:'): q['numbers'] = line[3:].strip()
        else: q['extra'].append(line)
    if len(q['opts']) < 2: warn(f'問 {qno}: 選択肢が {len(q["opts"])} 個 (2 個以上、A と B の対立軸を)')
    if not any(o['rec'] for o in q['opts']): warn(f'問 {qno}: 推奨 (A*) が無い — 最初に選んでおく案が無く、人が全部自分で選ぶことになる')
    if not q['evidence']: warn(f'問 {qno}: 根拠: (file:line か実行結果) が無い — 事実を人に聞いていないか確認')
    for o in q['opts']:
        if o['rec'] is False and not o['pro']: warn(f'問 {qno} {o["id"]}: 非推奨の選択肢に「利点:」が無い (実質 1 択になっていないか)')
    return q

def render_q(q, figs):
    """問いカード = 判断材料 + 回答欄 (択一 / 保留 / 補足) を 1 か所に。絵 (fig:) は選択肢の直下に 1 回だけ出す"""
    n = q['no']
    out = [f'<div class="qcard" id="qc{n}" data-qid="q{n}"><p class="qt">問 {n}. {inline(q["text"])}</p>']
    if q['numbers']: out.append(f'<p class="m">数値: {inline(q["numbers"])}</p>')
    for x in q['extra']: out.append(f'<p class="m">{inline(x)}</p>')
    for o in q['opts']:
        d = ' / '.join(x for x in ([f'利点: {o["pro"]}'] if o['pro'] else []) + ([f'代償: {o["con"]}'] if o['con'] else []) + o['desc'])
        chk = ' checked' if o['rec'] else ''
        out.append(f'<label><input type="radio" name="q{n}" value="{o["id"]}"{chk}><b>{o["id"]}. {inline(o["label"])}</b>' + ('<span class="rec">推奨</span>' if o['rec'] else ''))
        if d: out.append(f'<div class="opt-d">{inline(d)}</div>')
        if o['fig']:
            if o['fig'] in figs:
                out.append('<figure class="thumb">' + render_fig(figs[o['fig']], 'q%s%s' % (n, o['id'])) + '</figure>')
            else: err(f'問 {n} {o["id"]}: fig: {o["fig"]} が無い')
        out.append('</label>')
    out.append(f'<label class="hold"><input type="radio" name="q{n}" value="hold"><b>保留 — 決める前に聞きたいことがある</b>'
               f'<div class="opt-d">推奨で確定せず、次の往復に回す。聞きたいことを下に書く</div>'
               f'<textarea name="q{n}_hold" placeholder="聞きたいこと・確認したいこと"></textarea></label>')
    out.append(f'<textarea name="q{n}_note" placeholder="補足 (任意)"></textarea>')
    if q['evidence']: out.append(f'<p class="m">根拠: {inline(q["evidence"])}</p>')
    out.append('</div>')
    return '\n'.join(out)

# ---------------------------------------------------------------- 組み立て
def build(src_path, hosted=False):
    """hosted=True: ブラウザに配信する前提 (claude.ai の artifact 等)。mock リンクを相対パスにする。
    False: ローカルで file:// で開く前提 (mock リンクは file:// 絶対 URL)"""
    text = src_path.read_text(encoding='utf-8')
    fm, body = parse_frontmatter(text)
    for k in ('label', 'title'):
        if not fm.get(k): err(f'frontmatter に {k}: が無い')
    label = fm.get('label', 'CHANGE-ME'); date = fm.get('date', '')
    figs, qs, parts = {}, [], []
    ctx = {'concl': False}
    pending_small = []  # 連続する小図の id。描画は最後 (q の fig: で参照された図は本文に出さずカードにだけ出す)
    def flush_small():
        if pending_small:
            parts.append('\x00G' + ','.join(pending_small) + '\x00'); pending_small.clear()
    for blk in split_blocks(body):
        if blk[0] == 'md':
            if blk[1].strip(): flush_small(); parts.append(render_md(blk[1], ctx))
            continue
        _, typ, args, fbody = blk
        if typ in ('fig', 'seq', 'svg', 'shot'):
            fig = parse_fig(args, fbody) if typ == 'fig' else parse_seq(args, fbody) if typ == 'seq' else parse_rawsvg(args, fbody) if typ == 'svg' else parse_shot(args, fbody, src_path.parent)
            if fig['id'] in figs: err(f'図の id が重複: {fig["id"]}')
            figs[fig['id']] = fig
            if fig['w'] <= 360 and typ != 'shot': pending_small.append(fig['id'])
            else: flush_small(); parts.append('\x00G' + fig['id'] + '\x00')
        elif typ == 'q':
            flush_small(); q = parse_q(fbody, len(qs) + 1); qs.append(q); parts.append(f'\x00Q{q["no"]}\x00')  # fig: が後で定義されても引けるよう、描画は最後に
        elif typ == 'details':
            flush_small()
            if not args or args in ('詳細', 'その他'): warn('details の見出しは中身と分量を予告する文言に (「詳細」「その他」は禁止)')
            parts.append(f'<details><summary>{inline(args or "補足")}</summary>{render_md(fbody, ctx)}</details>')
        else:
            err(f'知らないブロック: ```{typ}')
    flush_small()
    if not ctx['concl']: warn('「結論:」で始まる段落が無い (骨格の 3 番目)')
    if len(qs) >= 5: warn(f'問が {len(qs)} 問 — 1 ラウンドのシートは 4 問まで。残りは次のラウンドか chat へ')
    if len(figs) == 0: warn('図が 1 枚も無い — 方針や優先度だけの論点でなければ全体図を')
    # mock ボタン
    mock = ''
    if fm.get('mock'):
        rel = fm['mock'].lstrip('./')
        mp = Path(fm['mock'])
        if not mp.is_absolute(): mp = (src_path.parent / mp).resolve()
        if not mp.exists(): warn(f'mock: {mp} が無い')
        if hosted:
            # 配信先では file:// は開けない。モックもシートと一緒に公開し、相対パスで指す
            href = attr(rel)
            warn(f'mock: 配信時は {rel} もシートと一緒に公開する (artifact なら files に {rel} を渡す)')
        else:
            href = 'file://' + attr(str(mp))
        mock = f'<p><a class="btn" href="{href}" target="_blank">▶ モックを触って確認</a></p>'
    css = ''.join((HERE / f).read_text(encoding='utf-8') for f in ('sheet.css', 'fig.css'))
    js = ''.join((HERE / f).read_text(encoding='utf-8') for f in ('fig-layout.js', 'sheet.js'))
    questions_js = json.dumps({f'q{q["no"]}': f'Q{q["no"]}. {q["text"]}' for q in qs}, ensure_ascii=False)
    referenced = {o['fig'] for q in qs for o in q['opts'] if o['fig']}
    def resolve(p):
        if p.startswith('\x00Q'):
            return render_q(qs[int(p[2:-1]) - 1], figs)
        if p.startswith('\x00G'):
            hs = [render_fig(figs[i]) for i in p[2:-1].split(',') if i not in referenced]
            return '<div class="ab">' + '\n'.join(hs) + '</div>' if len(hs) > 1 else (hs[0] if hs else '')
        return p
    parts = [resolve(p) for p in parts]
    form = ''
    if qs:
        form = '<p class="m">問いはそれぞれのカードで答える。推奨の案があらかじめ選んである (そのままなら推奨で確定)。まだ決めたくない問いは「選択を解除」で未回答にすると、推奨では確定せず次の往復に回る。決める前に聞きたいことがあれば「保留」を選んで書く。</p>'
    html_out = f'''<!DOCTYPE html>
<html lang="ja">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<!-- akapen-format: v4 (built from {attr(src_path.name)}) -->
<title>{esc(fm.get('title', ''))} — 赤ペン</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+JP:wght@400;500;700&family=IBM+Plex+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
{css}
</style></head>
<body><main>
<section id="akSheet">
<div class="kicker">✎ AKAPEN — {esc(date)}{(" — " + esc(fm["round"]) + " 巡目") if fm.get("round") else ""}</div>
<h1>{inline(fm.get('title', ''))}</h1>
{mock}
{chr(10).join(parts)}
<footer class="m">{inline(fm.get('source', 'このシートは ' + src_path.name + ' から生成'))}。回答は各カードから。推奨があらかじめ選んであり、選択を解除した問は推奨で確定しない。</footer>
</section>
<section id="akForm">
{form}
<h2>全体への赤ペン</h2>
<div class="q redpen"><p class="m" style="margin-top:0">訂正・追加要望・「そもそも」の指摘はここへ。複数行でよい。</p><textarea name="global_note"></textarea></div>
<div class="sendbar"><button id="genBtn" type="button" onclick="generatePrompt()">貼り付ける文章を作る</button><div id="status" class="status"></div><textarea id="out" readonly onclick="this.select()"></textarea></div>
</section>
</main>
<script>
var QUESTIONS = {questions_js};
var DRAFT_KEY = "akapen-draft-{attr(label)}";
var DOC = "{attr(label)}";
{js}
</script>
</body></html>'''
    return html_out, {'figs': len(figs), 'qs': len(qs)}

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('src', help='ソース (<topic>-01.akapen.md)')
    ap.add_argument('-o', '--out', help='出力 HTML (省略時は src と同じ場所に <label>.html)')
    ap.add_argument('--check', action='store_true', help='検査だけ (HTML を書かない)')
    ap.add_argument('--hosted', action='store_true',
                    help='配信用に作る (claude.ai の artifact 等)。mock リンクを相対パスにする。省略時はローカルの file:// 前提')
    a = ap.parse_args()
    src = Path(a.src)
    if not src.is_file(): sys.exit(f'build: ソースが無い: {src}')
    html_out, info = build(src, hosted=a.hosted)
    for w in WARN: print(f'警告: {w}', file=sys.stderr)
    for e in ERR: print(f'エラー: {e}', file=sys.stderr)
    if ERR: sys.exit(f'build: エラー {len(ERR)} 件 — 直してから再実行')
    if a.check:
        print(f'check: 図 {info["figs"]} 枚 / 問 {info["qs"]} 問 / 警告 {len(WARN)} 件', file=sys.stderr); return
    out = Path(a.out) if a.out else src.with_name(re.sub(r'\.akapen\.md$|\.md$', '', src.name) + '.html')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_out, encoding='utf-8')
    where = '配信用 (Artifact で公開する)' if a.hosted else f'file://{out.resolve()}'
    print(f'sheet: {out} ({len(html_out.encode("utf-8"))//1000}KB, 図 {info["figs"]} 枚 / 問 {info["qs"]} 問 / 警告 {len(WARN)} 件) — {where}', file=sys.stderr)

if __name__ == '__main__':
    main()
