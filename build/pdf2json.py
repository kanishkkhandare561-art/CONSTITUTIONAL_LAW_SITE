"""Convert the consolidated day-wise class notes PDF (PreCL.pdf) into structured JSON.

The PDF was typeset from HTML, so its layout is regular:
  * day band  : dark olive rectangle, white "DAY n", title (13.5pt), date (11.5pt), topic trail (8.8pt)
  * section   : bold 13.6pt olive heading           sub-heading: bold 11.4pt
  * case box  : filled rectangle, bold 10.8pt olive title, italic 8.8pt subtitle, "Facts · / Held · / Principle ·"
  * aside box : filled rectangle with a 7.6pt bold label (PROFESSOR'S ASIDE, HOMEWORK, KEY POINT ...)
  * Q&A       : "Q" / "A" badges (bold 11pt)
  * tables    : olive header row + alternating row rectangles
  * figures   : raster images (flowcharts) -> exported as PNG

Output: content/day_notes.json  and images in content/img/
"""
import html, json, re, sys
from pathlib import Path
import pymupdf as fitz

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else 'source/notes/PreCL.pdf')
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else 'content/day_notes.json')
IMGDIR = OUT.parent / 'img'
IMGDIR.mkdir(parents=True, exist_ok=True)

doc = fitz.open(str(SRC))
FIRST_BODY_PAGE = 6  # 0-based index of "How to Use These Notes" (page 7)

OLIVE_HDR = (0.46, 0.41, 0.28)
ROW_FILLS = {(1.0, 1.0, 1.0), (0.96, 0.96, 0.95)}
CASE_FILL = (0.95, 0.94, 0.91)


def rnd(c):
    return tuple(round(x, 2) for x in c)


def esc(s):
    return html.escape(s, quote=False)


def span_html(s):
    t = esc(s['text'])
    if not t.strip():
        return t
    f = s['font']
    lead = re.match(r'^\s*', t).group(0)
    trail = re.search(r'\s*$', t).group(0)
    core = t.strip()
    if 'Bold' in f:
        core = f'<strong>{core}</strong>'
    if 'Italic' in f:
        core = f'<em>{core}</em>'
    return lead + core + trail


class Line:
    def __init__(self, l, page):
        self.page = page
        sp = [s for s in l['spans'] if s['text'] != '']
        self.spans = sp
        self.bbox = fitz.Rect(l['bbox'])
        s0 = next((s for s in sp if s['text'].strip()), sp[0])
        self.size = round(s0['size'], 1)
        self.color = s0['color']
        self.font = s0['font']
        self.text = ''.join(s['text'] for s in sp)
        self.bold = 'Bold' in self.font
        self.italic = 'Italic' in self.font

    def html(self):
        h = ''.join(span_html(s) for s in self.spans)
        h = h.replace('</strong><strong>', '').replace('</em><em>', '')
        return re.sub(r'\s+', ' ', h).strip()


def role(line):
    s, c = line.size, line.color
    if s == 7.5 and c == 9210242:
        return 'skip'
    if c == 16777215 and s >= 14.5:
        return 'daynum'
    if c == 16777215 and s == 13.5:
        return 'daytitle'
    if c == 16777215 and s == 11.5:
        return 'daydate'
    if c == 15921126:
        return 'daytrail'
    if s == 13.6 and c == 7694663:
        return 'h3'
    if s == 11.4 and line.bold:
        return 'h4'
    if s == 10.8 and c == 7694663:
        return 'casetitle'
    if s == 7.6 and line.bold:
        return 'label'
    if s == 8.6 and line.italic and c == 9210242:
        return 'caption'
    if s == 8.8 and line.italic and c == 9210242:
        return 'casesub'
    if s == 11.0 and line.bold and line.text.strip() in ('Q', 'A'):
        return 'qa-' + line.text.strip()
    return 'text'


items = []  # (page, y, kind, payload)
img_count = 0

for pno in range(FIRST_BODY_PAGE, len(doc)):
    pg = doc[pno]
    drawings = [d for d in pg.get_drawings() if d.get('fill')]
    rects = [(fitz.Rect(d['rect']), rnd(d['fill'])) for d in drawings
             if d['rect'].width > 30 and d['rect'].height > 6]

    # ---- tables: olive header (or row stripes at page top = continuation) ----
    tables = []
    used = set()
    rects_sorted = sorted(range(len(rects)), key=lambda i: rects[i][0].y0)
    i = 0
    while i < len(rects_sorted):
        r, f = rects[rects_sorted[i]]
        if f == OLIVE_HDR and r.width > 300 and r.height < 40:
            rows = [r]
            j = i + 1
            while j < len(rects_sorted):
                r2, f2 = rects[rects_sorted[j]]
                if f2 in ROW_FILLS and abs(r2.y0 - rows[-1].y1) < 1.5 and abs(r2.x0 - r.x0) < 3:
                    rows.append(r2); j += 1
                else:
                    break
            tables.append({'header': True, 'rows': rows})
            for k in range(i, j):
                used.add(rects_sorted[k])
            i = j
            continue
        i += 1
    # continuation tables: stripe rows not attached to a header
    stripe = [rects_sorted[k] for k in range(len(rects_sorted))
              if rects_sorted[k] not in used and rects[rects_sorted[k]][1] in ROW_FILLS
              and rects[rects_sorted[k]][0].width > 300 and rects[rects_sorted[k]][0].x0 < 59]
    grp = []
    for k in stripe:
        r = rects[k][0]
        if grp and abs(r.y0 - grp[-1].y1) < 1.5:
            grp.append(r)
        else:
            if len(grp) >= 1:
                tables.append({'header': False, 'rows': grp})
            grp = [r]
        used.add(k)
    if grp:
        tables.append({'header': False, 'rows': grp})
    # discard "tables" that are really white box backgrounds (single white row, not at top)
    tables = [t for t in tables if t['header'] or len(t['rows']) >= 2 or t['rows'][0].y0 < 90]
    table_boxes = [fitz.Rect(t['rows'][0].x0, t['rows'][0].y0, t['rows'][-1].x1, t['rows'][-1].y1) for t in tables]

    boxes = [(r, f) for k, (r, f) in enumerate(rects)
             if k not in used and not (f in ROW_FILLS and r.x0 < 59) and f != (1.0, 1.0, 1.0) and not (f == OLIVE_HDR and r.height < 40)
             and not any(tb.contains(r) for tb in table_boxes)]
    # day band = dark box
    lines = []
    blocks = pg.get_text('dict')['blocks']
    for b in blocks:
        if b['type'] == 1:
            bb = fitz.Rect(b['bbox'])
            if bb.height < 20 or bb.width < 100:
                continue
            img_count += 1
            name = f'precl-p{pno + 1}-{img_count}.png'
            pix = pg.get_pixmap(clip=bb, dpi=160)
            pix.save(str(IMGDIR / name))
            items.append((pno, bb.y0, 'img', {'src': 'img/' + name, 'w': pix.width, 'h': pix.height}))
            continue
        for l in b['lines']:
            ln = Line(l, pno)
            if not ln.spans or not ln.text.strip():
                continue
            lines.append(ln)

    # assign lines to tables
    for t, tb in zip(tables, table_boxes):
        tl = [ln for ln in lines if tb.contains(fitz.Point((ln.bbox.x0 + ln.bbox.x1) / 2, (ln.bbox.y0 + ln.bbox.y1) / 2))]
        for ln in tl:
            ln.in_table = True
        rows_html = []
        # columns from header row (or from min x positions)
        hdr_lines = [ln for ln in tl if t['rows'][0].contains(fitz.Point(ln.bbox.x0 + 1, (ln.bbox.y0 + ln.bbox.y1) / 2))] if t['header'] else []
        if hdr_lines:
            cols = sorted({round(ln.bbox.x0) for ln in hdr_lines})
        else:
            xs = sorted({round(ln.bbox.x0) for ln in tl})
            cols = []
            for x in xs:
                if not cols or x - cols[-1] > 25:
                    cols.append(x)
        cols = cols or [0]
        for ri, rr in enumerate(t['rows']):
            cells = [[] for _ in cols]
            for ln in tl:
                cy = (ln.bbox.y0 + ln.bbox.y1) / 2
                if rr.y0 <= cy <= rr.y1:
                    ci = max([k for k, cx in enumerate(cols) if ln.bbox.x0 >= cx - 4] or [0])
                    cells[ci].append(ln)
            if not any(cells):
                continue
            tag = 'th' if (t['header'] and ri == 0) else 'td'
            ch = []
            for c in cells:
                c.sort(key=lambda ln: (round(ln.bbox.y0), ln.bbox.x0))
                ch.append(' '.join(ln.html() for ln in c))
            rows_html.append((tag, ch))
        items.append((pno, tb.y0, 'table', {'header': t['header'], 'rows': rows_html}))

    lines = [ln for ln in lines if not getattr(ln, 'in_table', False)]
    # day bands: tall olive rectangles -> one item each
    for r, f in rects:
        if f == OLIVE_HDR and r.height >= 40:
            inb = [ln for ln in lines if r.contains(fitz.Point((ln.bbox.x0 + ln.bbox.x1) / 2, (ln.bbox.y0 + ln.bbox.y1) / 2))]
            for ln in inb:
                ln.in_band = True
            band = {'num': '', 'title': [], 'date': [], 'trail': []}
            for ln in sorted(inb, key=lambda l: (l.bbox.y0, l.bbox.x0)):
                rl = role(ln)
                if rl == 'daynum':
                    m = re.search(r'DAY\s+(\d+)', ln.text)
                    band['num'] = m.group(1) if m else ln.text.strip()
                elif rl == 'daytitle':
                    band['title'].append(ln.text.strip())
                elif rl == 'daydate':
                    band['date'].append(ln.text.strip())
                else:
                    band['trail'].append(ln.text.strip())
            items.append((pno, r.y0, 'band', band))
    lines = [ln for ln in lines if not getattr(ln, 'in_band', False)]
    for ln in lines:
        ln.box = None
        cy = (ln.bbox.y0 + ln.bbox.y1) / 2
        cx = (ln.bbox.x0 + ln.bbox.x1) / 2
        for bi, (r, f) in enumerate(boxes):
            if r.contains(fitz.Point(cx, cy)):
                ln.box = (pno, bi, f)
        items.append((pno, ln.bbox.y0, 'line', ln))

items.sort(key=lambda it: (it[0], it[1], it[3].bbox.x0 if it[2] == 'line' else 0))

# ---- assemble into days / sections / blocks ----
days = []
cur_day = None
cur_sec = None


def new_day(num):
    global cur_day, cur_sec
    cur_day = {'num': num, 'title': '', 'date': '', 'trail': '', 'sections': []}
    days.append(cur_day)
    cur_sec = None


def sec():
    global cur_sec
    if cur_day is None:
        new_day('intro')
        cur_day['title'] = 'How to Use These Notes'
    if cur_sec is None:
        cur_sec = {'title': 'Overview', 'blocks': []}
        cur_day['sections'].append(cur_sec)
    return cur_sec


# group lines into paragraphs
para = None  # dict(kind, box, lines)
blocks_out = []


def flush_para():
    global para
    if para is not None:
        sec()['blocks'].append(para)
    para = None


prev_line = None
for pno, y, kind, payload in items:
    if kind == 'band':
        flush_para()
        new_day(payload['num'])
        cur_day['title'] = ' '.join(payload['title'])
        cur_day['date'] = ' '.join(payload['date'])
        cur_day['trail'] = ' '.join(payload['trail'])
        prev_line = None
        continue
    if kind in ('img', 'table'):
        flush_para()
        sec()['blocks'].append({'kind': kind, 'data': payload, 'box': None, 'page': pno})
        prev_line = None
        continue
    ln = payload
    r = role(ln)
    if r == 'skip':
        continue
    if r == 'daynum':
        flush_para()
        m = re.search(r'DAY\s+(\d+)', ln.text)
        new_day(m.group(1) if m else ln.text.strip())
        prev_line = None
        continue
    if r in ('daytitle', 'daydate', 'daytrail') and cur_day is not None:
        flush_para()
        key = {'daytitle': 'title', 'daydate': 'date', 'daytrail': 'trail'}[r]
        cur_day[key] = (cur_day[key] + ' ' + ln.text.strip()).strip()
        continue
    if r == 'h3':
        flush_para()
        if cur_sec is not None and cur_sec['blocks'] == [] and cur_sec['title'] and prev_line is not None and role(prev_line) == 'h3':
            cur_sec['title'] += ' ' + ln.text.strip()
        else:
            if cur_day is None:
                new_day('intro')
                cur_day['title'] = 'How to Use These Notes'
            cur_sec = {'title': ln.text.strip(), 'blocks': []}
            cur_day['sections'].append(cur_sec)
        prev_line = ln
        continue
    # paragraph grouping
    bullet = ln.text.lstrip().startswith('●')
    start_new = (para is None or bullet or r in ('h4', 'casetitle', 'label', 'caption', 'casesub', 'qa-Q', 'qa-A')
                 or para['role'] in ('h4', 'casetitle', 'label', 'caption', 'casesub', 'qa-Q', 'qa-A')
                 or (ln.box[1:] if ln.box else None) != (para['box'][1:] if para['box'] else None) and not (
                     ln.box and para['box'] and ln.box[2] == para['box'][2] and ln.page != para['lines'][-1].page)
                 or abs(ln.size - para['lines'][-1].size) > 0.3 and not bullet
                 )
    if not start_new:
        last = para['lines'][-1]
        if ln.page == last.page:
            gap = ln.bbox.y0 - last.bbox.y0
            if gap > 1.75 * ln.size or gap < -2:
                start_new = True
            # "Facts ·", "Held ·", "Principle ·" start new paragraphs inside case boxes
            if re.match(r'^(Facts|Held|Principle|Issue|Issues|Ratio|Significance|Note|Bench|Reasoning|Answer|Why|Verdict|Test applied)\s*·', ln.text.strip()):
                start_new = True
        else:
            # page break: continue paragraph only if previous line did not end a sentence
            if re.search(r'[.!?:”"]\s*$', last.text.strip()) or ln.text.strip()[:1].isupper() and para['role'] != 'text':
                start_new = True
    # a line that sits to the right of a Q/A badge on the same baseline belongs to it
    if para is not None and para['role'] in ('qa-Q', 'qa-A') and r == 'text' and abs(ln.bbox.y0 - para['lines'][-1].bbox.y0) < 6:
        para['lines'].append(ln)
        prev_line = ln
        continue
    if start_new:
        flush_para()
        para = {'kind': 'para', 'role': r if not bullet else 'li', 'box': ln.box, 'lines': [ln], 'page': ln.page}
    else:
        para['lines'].append(ln)
    prev_line = ln
flush_para()


def para_html(p):
    parts = []
    for ln in p['lines']:
        h = ln.html()
        parts.append(h)
    h = ' '.join(parts)
    h = h.replace('</strong> <strong>', ' ').replace('</em> <em>', ' ')
    h = re.sub(r'^●\s*', '', h)
    return re.sub(r'\s+', ' ', h).strip()


def plain(h):
    return html.unescape(re.sub(r'<[^>]+>', '', h))


def slug(s, n=48):
    s = re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')
    return s[:n].strip('-') or 'x'


CASES = []
QA = []


def render_blocks(blocks, day_id, sec_id):
    out = []
    i = 0
    n = len(blocks)
    while i < n:
        b = blocks[i]
        if b['kind'] == 'img':
            d = b['data']
            out.append(f'<figure class="fig"><img data-src="{d["src"]}" alt="Diagram from the class notes" width="{d["w"]}" height="{d["h"]}" loading="lazy"></figure>')
            i += 1; continue
        if b['kind'] == 'table':
            rows = b['data']['rows']
            # merge with following continuation table
            j = i + 1
            while j < n and blocks[j]['kind'] == 'table' and not blocks[j]['data']['header']:
                rows = rows + blocks[j]['data']['rows']; j += 1
            h = ['<div class="tbl-wrap"><table>']
            for tag, cells in rows:
                h.append('<tr>' + ''.join(f'<{tag}>{c}</{tag}>' for c in cells) + '</tr>')
            h.append('</table></div>')
            out.append(''.join(h))
            i = j; continue
        if b['box'] is not None:
            # gather consecutive paragraphs in the same (or page-continued) box
            box_key = b['box']
            grp = [b]
            j = i + 1
            while j < n and blocks[j]['kind'] == 'para' and blocks[j]['box'] is not None and (
                    blocks[j]['box'] == grp[-1]['box'] or (
                    blocks[j]['box'][2] == grp[-1]['box'][2] and blocks[j]['box'][0] == grp[-1]['box'][0] + 1
                    and blocks[j]['lines'][0].bbox.y0 < 120 and blocks[j]['role'] not in ('casetitle', 'label'))):
                grp.append(blocks[j]); j += 1
            out.append(render_box(grp, day_id, sec_id))
            i = j; continue
        # list items
        if b['role'] == 'li':
            lis = []
            j = i
            while j < n and blocks[j]['kind'] == 'para' and blocks[j]['box'] is None and blocks[j]['role'] in ('li', 'text'):
                if blocks[j]['role'] == 'li':
                    lis.append(para_html(blocks[j]))
                elif blocks[j]['lines'][0].bbox.x0 > 75 and lis:  # continuation of the bullet across a page
                    lis[-1] += ' ' + para_html(blocks[j])
                else:
                    break
                j += 1
            out.append('<ul>' + ''.join(f'<li>{x}</li>' for x in lis) + '</ul>')
            i = j; continue
        out.append(simple_para(b))
        i += 1
    return '\n'.join(out)


def simple_para(b):
    h = para_html(b)
    r = b['role']
    if r == 'h4':
        return f'<h4>{h}</h4>'
    if r == 'caption':
        return f'<p class="caption">{h}</p>'
    if r == 'casetitle':
        return f'<h4>{h}</h4>'
    if r == 'label':
        return f'<p class="label">{h}</p>'
    return f'<p>{h}</p>'


def render_box(grp, day_id, sec_id):
    roles = [g['role'] for g in grp]
    if 'casetitle' in roles:
        ti = roles.index('casetitle')
        pre = grp[:ti]
        title = plain(para_html(grp[ti]))
        rest = grp[ti + 1:]
        sub = ''
        if rest and rest[0]['role'] == 'casesub':
            sub = para_html(rest[0]); rest = rest[1:]
        m = re.search(r'\((\d{4})\)', title + ' ' + plain(sub))
        year = int(m.group(1)) if m else None
        cid = f'{day_id}-case-' + slug(title, 40)
        base, k = cid, 2
        while any(c['id'] == cid for c in CASES):
            cid = f'{base}-{k}'; k += 1
        fields = []
        body = []
        for g in rest:
            h = para_html(g)
            m2 = re.match(r'^<strong>([A-Za-z /]+?)\s*·\s*</strong>\s*(.*)$', h) or re.match(r'^<strong>([A-Za-z /]+?)\s*·\s*(.*?)</strong>(.*)$', h)
            if m2 and m2.lastindex == 2:
                fields.append({'label': m2.group(1).strip(), 'html': m2.group(2)})
            elif m2:
                fields.append({'label': m2.group(1).strip(), 'html': '<strong>' + m2.group(2) + '</strong>' + m2.group(3)})
            elif fields and g['role'] in ('text', 'li'):
                fields[-1]['html'] += ' ' + (('• ' + h) if g['role'] == 'li' else h)
            else:
                body.append(h)
        CASES.append({'id': cid, 'name': title, 'sub': plain(sub), 'year': year, 'fields': fields,
                      'chapter': day_id, 'section': sec_id, 'source': 'day'})
        fh = ''.join(f'<div class="cf"><div class="cf-l">{esc(f["label"])}</div><div class="cf-v">{f["html"]}</div></div>' for f in fields)
        bh = ''.join(f'<p>{x}</p>' for x in body)
        preh = ''.join(simple_para(p) for p in pre)
        return (preh + f'<article class="box box-case" id="{cid}" data-case="{cid}"><header class="case-h"><span class="tag">Case</span>'
                f'<h4>{esc(title)}</h4><span class="ik" data-q="{esc(title)}"></span></header>'
                + (f'<p class="case-sub">{sub}</p>' if sub else '') + fh + bh + '</article>')
    if 'qa-Q' in roles or 'qa-A' in roles:
        return render_qa(grp, day_id, sec_id)
    label = ''
    body = []
    for g in grp:
        if g['role'] == 'label' and not label:
            h = para_html(g)
            # label line may carry the first words of the body
            m = re.match(r'^<strong>([A-Z’\'& ]+?)</strong>\s*(.*)$', h)
            if m:
                label = m.group(1).strip(); rest = m.group(2).strip()
                if rest:
                    body.append(f'<p>{rest}</p>')
            else:
                label = plain(h)
            continue
        if g['role'] == 'li':
            body.append(f'<ul><li>{para_html(g)}</li></ul>')
        else:
            body.append(simple_para(g))
    html_body = '\n'.join(body).replace('</ul>\n<ul>', '')
    kind = {'PROFESSOR\'S ASIDE': 'aside', 'PROFESSOR’S ASIDE': 'aside', 'HOMEWORK': 'homework', 'KEY POINT': 'key',
            'EXAM TIPS': 'key', 'EXAM DIRECTIVE': 'key', 'EXAM DIRECTIVES': 'key', 'CORRECTIONS': 'warning',
            'RESEARCH TASK': 'homework', 'FIND OUT': 'homework', 'THE OPEN QUESTION': 'key', 'QUOTES': 'key',
            'APPENDIX': 'note'}.get(label.upper(), 'note')
    lab = f'<span class="tag">{esc(label.title() if label.isupper() else label)}</span>' if label else ''
    return f'<aside class="box box-{kind}">{lab}{html_body}</aside>'


def render_qa(grp, day_id, sec_id):
    out = []
    q, a = [], []
    pairs = []
    mode = None
    for g in grp:
        if g['role'] == 'qa-Q':
            if q or a:
                pairs.append((q, a))
            q, a = [], []
            mode = 'q'
            rest = g['lines'][1:]
            if rest:
                q.append(' '.join(l.html() for l in rest))
            continue
        if g['role'] == 'qa-A':
            mode = 'a'
            rest = g['lines'][1:]
            if rest:
                a.append(' '.join(l.html() for l in rest))
            continue
        h = para_html(g)
        (a if mode == 'a' else q).append(h)
    if q or a:
        pairs.append((q, a))
    for q, a in pairs:
        qid = f'{day_id}-q{len(QA) + 1}'
        qh = ''.join(f'<p>{x}</p>' for x in q)
        ah = ''.join(f'<p>{x}</p>' for x in a)
        QA.append({'id': qid, 'kind': 'question', 'q_html': qh, 'a_html': ah, 'q_text': plain(qh),
                   'chapter': day_id, 'section': sec_id})
        out.append(f'<div class="box box-question" id="{qid}"><div class="qa-q"><span class="tag">Question</span>{qh}</div>'
                   f'<details class="qa-a" open><summary>Answer</summary>{ah}</details></div>')
    return '\n'.join(out)


out_days = []
for d in days:
    did = 'D' + str(d['num'])
    secs = []
    for si, s in enumerate(d['sections']):
        sid = f'{did}-{si + 1}'
        h = render_blocks(s['blocks'], did, sid)
        txt = re.sub(r'\s+', ' ', plain(re.sub(r'<(p|li|h4|tr|div)[^>]*>', ' ', h))).strip()
        secs.append({'id': sid, 'title': s['title'], 'html': h, 'text': txt})
    out_days.append({'id': did, 'num': d['num'], 'title': d['title'], 'date': d['date'],
                     'trail': d['trail'], 'sections': secs})

OUT.write_text(json.dumps({'days': out_days, 'cases': CASES, 'qa': QA}, ensure_ascii=False))
print(f'{len(out_days)} days, {sum(len(d["sections"]) for d in out_days)} sections, {len(CASES)} case boxes, '
      f'{len(QA)} Q&A, {img_count} images -> {OUT}')
