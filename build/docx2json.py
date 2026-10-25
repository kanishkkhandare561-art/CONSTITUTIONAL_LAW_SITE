"""Convert the COLA exam-ready Word notes into structured JSON for the site.

Output: content/exam_notes.json
  { "chapters": [ {id, title, kind, sections: [{id, title, html, text}] } ],
    "cases":    [ {id, name, year, fields:{label: html}, chapter, section} ],
    "qa":       [ {id, kind: question|homework, q_html, a_html, chapter, section} ] }

Box colours in the Word file (single-cell tables, cell shading):
  FFF7E6 question (yellow)   EAF7EF homework (green)   EEF4FB case card (blue)
  FDECEC warning (amber/red) F3F0FF key points / snapshot (purple)
"""
import html, json, re, sys
from pathlib import Path
import docx
from docx.oxml.ns import qn

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else 'source/notes/COLA_Exam_Ready_Notes_Kanishk.docx')
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else 'content/exam_notes.json')

BOX = {'FFF7E6': 'question', 'EAF7EF': 'homework', 'EEF4FB': 'case',
       'FDECEC': 'warning', 'F3F0FF': 'key'}

d = docx.Document(str(SRC))
W = lambda t: qn('w:' + t)

# list numbering formats
numfmt = {}
try:
    nume = d.part.numbering_part.element
    absfmt = {}
    for a in nume.findall(W('abstractNum')):
        lv = a.find(W('lvl'))
        absfmt[a.get(W('abstractNumId'))] = lv.find(W('numFmt')).get(W('val'))
    for n in nume.findall(W('num')):
        numfmt[n.get(W('numId'))] = absfmt.get(n.find(W('abstractNumId')).get(W('val')), 'bullet')
except Exception:
    pass


def slug(s, n=60):
    s = re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')
    return s[:n].strip('-') or 'x'


def run_html(r):
    """r is a w:r element"""
    out = []
    for c in r:
        tag = c.tag.split('}')[1]
        if tag == 't':
            out.append(html.escape(c.text or ''))
        elif tag == 'tab':
            out.append(' ')
        elif tag in ('br', 'cr'):
            out.append('<br>')
    txt = ''.join(out)
    if not txt:
        return ''
    rpr = r.find(W('rPr'))
    if rpr is not None:
        def on(t):
            e = rpr.find(W(t))
            return e is not None and e.get(W('val')) not in ('0', 'false')
        if on('b'):
            txt = '<strong>' + txt + '</strong>'
        if on('i'):
            txt = '<em>' + txt + '</em>'
        if on('u'):
            txt = '<u>' + txt + '</u>'
    return txt


def para_inner(p):
    parts = []
    for c in p:
        tag = c.tag.split('}')[1]
        if tag == 'r':
            parts.append(run_html(c))
        elif tag == 'hyperlink':
            inner = ''.join(run_html(r) for r in c.findall(W('r')))
            rid = c.get(qn('r:id'))
            href = None
            if rid and rid in d.part.rels:
                href = d.part.rels[rid].target_ref
            if href and href.startswith('http'):
                parts.append(f'<a href="{html.escape(href)}" target="_blank" rel="noopener">{inner}</a>')
            else:
                parts.append(inner)
        elif tag in ('ins', 'smartTag', 'fldSimple'):
            parts.extend(run_html(r) for r in c.iter(W('r')))
    s = ''.join(parts)
    s = re.sub(r'</strong><strong>', '', s)
    s = re.sub(r'</em><em>', '', s)
    return s.strip()


def p_style(p):
    ppr = p.find(W('pPr'))
    if ppr is None:
        return 'Normal', None
    st = ppr.find(W('pStyle'))
    sid = st.get(W('val')) if st is not None else 'Normal'
    num = ppr.find(W('numPr'))
    lst = None
    if num is not None:
        ni = num.find(W('numId'))
        il = num.find(W('ilvl'))
        lst = (numfmt.get(ni.get(W('val')) if ni is not None else '', 'bullet'),
               int(il.get(W('val'))) if il is not None else 0)
    return sid, lst


STYLE_NAMES = {s.style_id: s.name for s in d.styles}


def blocks_to_html(elems):
    """Convert a sequence of w:p / w:tbl into HTML, grouping list items."""
    out = []
    list_stack = []  # (tag)

    def close_lists(level=-1):
        while len(list_stack) > level + 1:
            out.append('</li></%s>' % list_stack.pop())

    for e in elems:
        tag = e.tag.split('}')[1]
        if tag == 'p':
            sid, lst = p_style(e)
            name = STYLE_NAMES.get(sid, sid)
            inner = para_inner(e)
            if lst is None and name == 'List Paragraph':
                lst = ('bullet', 0)
            if lst:
                fmt, lvl = lst
                ltag = 'ol' if fmt == 'decimal' else 'ul'
                if len(list_stack) > lvl + 1:
                    close_lists(lvl)
                if len(list_stack) == lvl + 1:
                    out.append('</li><li>' + inner)
                else:
                    while len(list_stack) < lvl + 1:
                        list_stack.append(ltag)
                        out.append('<%s><li>' % ltag)
                    out.append(inner)
                continue
            close_lists()
            if not inner:
                continue
            if name.startswith('Heading 3'):
                out.append(f'<h4>{inner}</h4>')
            elif name.startswith('Heading 4'):
                out.append(f'<h5>{inner}</h5>')
            else:
                out.append(f'<p>{inner}</p>')
        elif tag == 'tbl':
            close_lists()
            out.append(table_html(e))
    close_lists()
    return '\n'.join(out)


def cell_fill(tc):
    shd = tc.find('.//' + W('shd'))
    return shd.get(W('fill')) if shd is not None else None


def table_html(tbl):
    rows = tbl.findall(W('tr'))
    cells0 = rows[0].findall(W('tc')) if rows else []
    if len(rows) == 1 and len(cells0) == 1:
        tc = cells0[0]
        kind = BOX.get((cell_fill(tc) or '').upper(), 'note')
        inner_elems = [c for c in tc if c.tag.split('}')[1] in ('p', 'tbl')]
        return box_html(kind, inner_elems)
    h = ['<div class="tbl-wrap"><table>']
    for i, tr in enumerate(rows):
        h.append('<tr>')
        for tc in tr.findall(W('tc')):
            span = tc.find('.//' + W('gridSpan'))
            cs = f' colspan="{span.get(W("val"))}"' if span is not None else ''
            content = blocks_to_html([c for c in tc if c.tag.split('}')[1] in ('p', 'tbl')])
            content = re.sub(r'^<p>(.*)</p>$', r'\1', content, flags=re.S) if content.count('<p>') == 1 else content
            t = 'th' if i == 0 else 'td'
            h.append(f'<{t}{cs}>{content}</{t}>')
        h.append('</tr>')
    h.append('</table></div>')
    return ''.join(h)


CASES, QA = [], []
CUR = {'chapter': None, 'section': None}


def box_html(kind, elems):
    body = blocks_to_html(elems)
    if kind == 'case':
        return case_html(elems, body)
    if kind in ('question', 'homework'):
        return qa_html(kind, elems, body)
    label = {'warning': 'Note', 'key': 'Key points', 'note': 'Note'}[kind]
    return f'<aside class="box box-{kind}">{body}</aside>'


def text_of(e):
    return ''.join(t.text or '' for t in e.iter(W('t')))


def case_html(elems, body):
    # first paragraph: "CASE: Name (year) - extra"
    first = text_of(elems[0]).strip() if elems else ''
    name = re.sub(r'^CASE:\s*', '', first).strip()
    m = re.search(r'\((\d{4})\)', name)
    year = int(m.group(1)) if m else None
    cid = 'case-' + slug(name, 50)
    base, k = cid, 2
    while any(c['id'] == cid for c in CASES):
        cid = f'{base}-{k}'; k += 1
    # split fields: bold-only paragraphs are labels
    fields, cur_label, cur = [], None, []
    for e in elems[1:]:
        if e.tag.split('}')[1] == 'p':
            t = text_of(e).strip()
            inner = para_inner(e)
            sid, lst = p_style(e)
            is_label = (inner.startswith('<strong>') and inner.endswith('</strong>')
                        and inner.count('<strong>') == 1 and len(t) < 60 and not lst
                        and STYLE_NAMES.get(sid, sid) != 'List Paragraph')
            m2 = re.match(r'^<strong>([^<]{2,40}):</strong>\s*(.+)$', inner)
            if is_label:
                if cur_label is not None or cur:
                    fields.append((cur_label, cur))
                cur_label, cur = t.rstrip(':'), []
                continue
            if m2 and not lst:
                if cur_label is not None or cur:
                    fields.append((cur_label, cur))
                fields.append((m2.group(1), [('html', '<p>' + m2.group(2) + '</p>')]))
                cur_label, cur = None, []
                continue
        cur.append(('el', e))
    if cur_label is not None or cur:
        fields.append((cur_label, cur))
    fd = []
    for label, items in fields:
        h = []
        els = []
        for kind, x in items:
            if kind == 'html':
                h.append(x)
            else:
                els.append(x)
        if els:
            h.append(blocks_to_html(els))
        fd.append({'label': label or '', 'html': '\n'.join(h)})
    CASES.append({'id': cid, 'name': name, 'year': year, 'fields': fd,
                  'chapter': CUR['chapter'], 'section': CUR['section'], 'source': 'exam'})
    rows = ''.join(f'<div class="cf"><div class="cf-l">{html.escape(f["label"])}</div><div class="cf-v">{f["html"]}</div></div>' for f in fd)
    return (f'<article class="box box-case" id="{cid}" data-case="{cid}">'
            f'<header class="case-h"><span class="tag">Case</span><h4>{html.escape(name)}</h4>'
            f'<span class="ik" data-q="{html.escape(name)}"></span></header>{rows}</article>')


def qa_html(kind, elems, body):
    # question = first paragraph (or until a paragraph starting with Answer/Solution)
    q_el, a_el = [], []
    split = None
    for i, e in enumerate(elems):
        t = text_of(e).strip()
        if i > 0 and re.match(r'^(Model answer|Answer|Solution|Solved|A\s*[:.-])', t, re.I):
            split = i
            break
    if split is None:
        split = 1
    q_el, a_el = elems[:split], elems[split:]
    a_label = 'Model answer'
    if a_el and re.match(r'^(Model answer|Answer|Solution|Solved)\s*[:.]?\s*$', text_of(a_el[0]).strip(), re.I):
        a_label = text_of(a_el[0]).strip().rstrip(':.')
        a_el = a_el[1:]
    qh, ah = blocks_to_html(q_el), blocks_to_html(a_el)
    qid = f'{kind}-{len(QA) + 1}'
    QA.append({'id': qid, 'kind': kind, 'q_html': qh, 'a_html': ah,
               'q_text': ' '.join(text_of(e) for e in q_el).strip(),
               'chapter': CUR['chapter'], 'section': CUR['section']})
    lab = 'Question asked in class' if kind == 'question' else 'Homework / instruction'
    return (f'<div class="box box-{kind}" id="{qid}"><div class="qa-q"><span class="tag">{lab}</span>{qh}</div>'
            f'<details class="qa-a" open><summary>{html.escape(a_label)}</summary>{ah}</details></div>')


# ---- walk the body ----
chapters = []
chap = None
sec = None
buf = []


def flush():
    global buf
    if sec is not None:
        sec['_elems'].extend(buf)
    elif chap is not None and buf:
        chap['_intro'].extend(buf)
    buf = []


for e in d.element.body:
    tag = e.tag.split('}')[1]
    if tag == 'sdt' or tag == 'sectPr':
        continue
    if tag == 'p':
        sid, _ = p_style(e)
        name = STYLE_NAMES.get(sid, sid)
        t = text_of(e).strip()
        if name == 'Heading 1' or name == 'TOC Heading':
            flush()
            if 'TABLE OF CONTENTS' in t.upper():
                chap = None; sec = None
                continue
            chap = {'title': t, 'sections': [], '_intro': []}
            chapters.append(chap)
            sec = None
            continue
        if name == 'Heading 2' and chap is not None:
            flush()
            sec = {'title': t, '_elems': []}
            chap['sections'].append(sec)
            continue
    if chap is None:
        continue  # cover page
    buf.append(e)
flush()

out_ch = []
for ci, ch in enumerate(chapters):
    t = ch['title']
    m = re.match(r'LECTURE (\d+)', t)
    cid = f'L{m.group(1)}' if m else ('toolkit' if 'TOOLKIT' in t.upper() else slug(t, 30))
    kind = 'lecture' if m else ('toolkit' if 'TOOLKIT' in t.upper() else 'front')
    secs = []
    if ch['_intro']:
        CUR['chapter'], CUR['section'] = cid, f'{cid}-intro'
        secs.append({'id': f'{cid}-intro', 'title': 'Overview', 'elems': ch['_intro']})
    for si, s in enumerate(ch['sections']):
        m2 = re.match(r'^([0-9]+\.[0-9]+|[A-G]\.)\s', s['title'])
        sid = f'{cid}-' + (m2.group(1).rstrip('.').replace('.', '-') if m2 else slug(s['title'], 30))
        secs.append({'id': sid, 'title': s['title'], 'elems': s['_elems']})
    rs = []
    for s in secs:
        CUR['chapter'], CUR['section'] = cid, s['id']
        h = blocks_to_html(s['elems'])
        txt = re.sub(r'<[^>]+>', ' ', h)
        txt = html.unescape(re.sub(r'\s+', ' ', txt)).strip()
        rs.append({'id': s['id'], 'title': s['title'], 'html': h, 'text': txt})
    out_ch.append({'id': cid, 'title': t, 'kind': kind, 'sections': rs})

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps({'chapters': out_ch, 'cases': CASES, 'qa': QA}, ensure_ascii=False))
print(f'{len(out_ch)} chapters, {sum(len(c["sections"]) for c in out_ch)} sections, '
      f'{len(CASES)} case cards, {len(QA)} Q&A boxes -> {OUT}')
