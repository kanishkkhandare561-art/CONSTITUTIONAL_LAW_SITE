"""Build the encrypted static site in docs/.

    SITE_PASSWORD='your password' python3 build/build.py

Steps
  1. read the converted notes (content/*.json, produced by docx2json.py, pdf2json.py, articles.py)
  2. link every case mention to the case registry (build/cases_master.py) and mark corrections
  3. assemble one content bundle (JSON), gzip it, encrypt it with a fresh random key (AES-256-GCM)
  4. encrypt every source file (lecture PDFs, Word files) with the same key
  5. wrap the key with a key derived from the password (PBKDF2-SHA256) -> docs/data/key.json

Nothing readable is written to docs/: without the password the site only shows the lock screen.
"""
import base64, gzip, hashlib, html, io, json, os, re, secrets, subprocess, sys
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'build'))
from cases_master import CASES, JUSTIA  # noqa: E402
from corrections import CORRECTIONS  # noqa: E402
from extras import AMENDMENTS, SOLVERS, SOURCES_META  # noqa: E402

C = ROOT / 'content'
DOCS = ROOT / 'docs'
DATA = DOCS / 'data'
PBKDF2_ITER = 310000

password = os.environ.get('SITE_PASSWORD')
if not password:
    sys.exit('Set SITE_PASSWORD (the password you will type to open the site).')

exam = json.loads((C / 'exam_notes.json').read_text())
day = json.loads((C / 'day_notes.json').read_text())
articles = json.loads((C / 'articles.json').read_text())
ik = {}
for line in (ROOT / 'build' / 'ik_links.txt').read_text().splitlines():
    if line.strip():
        k, url, title, date = line.split('|')
        ik[k] = {'url': url, 'title': title, 'date': date}

# ------------------------------------------------------------------ case registry
REG = {}
for key, name, year, court, topics, holding, aliases in CASES:
    url = ik.get(key, {}).get('url') or JUSTIA.get(key)
    REG[key] = {'k': key, 'name': name, 'year': year, 'court': court, 'topics': topics, 'holding': holding,
                'url': url, 'src': 'ik' if key in ik else ('justia' if key in JUSTIA else None),
                'date': ik.get(key, {}).get('date', str(year)), 'aliases': aliases, 'seen': [], 'cards': []}

# one big regex; longer, more specific aliases first
alias_list = []
for key, c in REG.items():
    for a in c['aliases']:
        alias_list.append((a, key))
alias_list.sort(key=lambda x: -len(x[0]))
ALIAS_RE = re.compile('|'.join(f'(?P<g{i}>{a})' for i, (a, _) in enumerate(alias_list)))
GROUP_KEY = {f'g{i}': k for i, (_, k) in enumerate(alias_list)}


def match_key(text):
    m = ALIAS_RE.search(text)
    return GROUP_KEY[m.lastgroup] if m else None


# ------------------------------------------------------------------ corrections
FIX_COUNT = {c['id']: 0 for c in CORRECTIONS}


FIX_STRINGS = sorted({(v, c['id']) for c in CORRECTIONS for s in c['match']
                      for v in (s, html.escape(s, quote=False))}, key=lambda x: -len(x[0]))


def apply_fixes(h):
    # longest strings first; matched text is swapped for a placeholder so shorter strings cannot nest inside
    found = []
    for v, cid in FIX_STRINGS:
        if v in h:
            FIX_COUNT[cid] += h.count(v)
            h = h.replace(v, f'\x00{len(found)}\x00')
            found.append((v, cid))
    for i, (v, cid) in enumerate(found):
        h = h.replace(f'\x00{i}\x00', f'<mark class="fix" data-fix="{cid}" tabindex="0">{v}</mark>')
    return h


# ------------------------------------------------------------------ case links inside HTML text
TAG_RE = re.compile(r'(<[^>]+>)')


def link_cases(h, where):
    out, inside_a, inside_h = [], 0, 0
    for part in TAG_RE.split(h):
        if not part:
            continue
        if part.startswith('<'):
            t = part[1:].split()[0].lower() if len(part) > 2 else ''
            if t == 'a' or t.startswith('a>'):
                inside_a += 1
            elif t in ('/a', '/a>'):
                inside_a = max(0, inside_a - 1)
            if re.match(r'<header class="case-h"', part):
                inside_h += 1
            elif part == '</header>':
                inside_h = max(0, inside_h - 1)
            out.append(part)
            continue
        if inside_a or inside_h:
            out.append(part)
            continue

        def rep(m):
            k = GROUP_KEY[m.lastgroup]
            if where and where not in REG[k]['seen']:
                REG[k]['seen'].append(where)
            return f'<a class="cref" data-k="{k}" href="#/case/{k}">{m.group(0)}</a>'
        out.append(ALIAS_RE.sub(rep, part))
    return ''.join(out)


def strip_tags(h):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', h))).strip()


# ------------------------------------------------------------------ images (diagrams) -> webp data URIs
def img_data_uri(rel):
    from PIL import Image
    im = Image.open(C / rel).convert('RGB')
    buf = io.BytesIO()
    im.save(buf, 'WEBP', quality=82, method=6)
    return 'data:image/webp;base64,' + base64.b64encode(buf.getvalue()).decode()


# ------------------------------------------------------------------ notes
def process_doc(doc_key, chapters, title_of):
    out = []
    for ch in chapters:
        secs = []
        for s in ch['sections']:
            where = f'{doc_key}/{ch["id"]}/{s["id"]}'
            h = s['html']
            # case cards -> registry
            def card(m):
                name = html.unescape(m.group(1))
                k = match_key(name)
                if k:
                    REG[k]['cards'].append(where)
                    return f'<span class="ik" data-k="{k}"></span>'
                return f'<span class="ik" data-q="{m.group(1)}"></span>'
            h = re.sub(r'<span class="ik" data-q="([^"]*)"></span>', card, h)
            h = re.sub(r'data-src="(img/[^"]+)"', lambda m: f'src="{img_data_uri(m.group(1))}"', h)
            h = apply_fixes(h)
            h = link_cases(h, where)
            secs.append({'id': s['id'], 'title': s['title'], 'html': h, 'text': strip_tags(h)})
        o = {k: v for k, v in ch.items() if k != 'sections'}
        o['title'] = title_of(ch)
        o['sections'] = secs
        out.append(o)
    return out


def exam_title(ch):
    t = ch['title']
    t = re.sub(r'^LECTURE (\d+) \((.*?)\):\s*', r'', t)
    return t[0] + t[1:] if t else t


exam_ch = process_doc('exam', exam['chapters'], lambda ch: ch['title'].title() if ch['kind'] == 'front' else ch['title'])
for ch in exam_ch:
    m = re.match(r'LECTURE (\d+) \((.*?)\):\s*(.*)$', ch['title'])
    if m:
        ch['num'], ch['tag'], ch['title'] = m.group(1), m.group(2), m.group(3)
    elif ch['kind'] == 'toolkit':
        ch['num'], ch['tag'], ch['title'] = '', '', 'Revision toolkit'
    else:
        ch['num'], ch['tag'], ch['title'] = '', '', 'How to use these notes'

day_ch = process_doc('day', day['days'], lambda ch: ch['title'])
for ch in day_ch:
    if ch['id'] == 'D0':
        ch['title'] = 'Master case index and doctrines'

# worksheet case map (SOLUTION CASES.docx)
ws_html = subprocess.run(['pandoc', str(ROOT / 'source/lectures/SOLUTION CASES.docx'), '-t', 'html', '--wrap=none'],
                         capture_output=True, text=True, check=True).stdout
ws_html = apply_fixes(ws_html)
ws_html = link_cases(ws_html, 'day/WS/WS-1')
day_ch.append({'id': 'WS', 'num': 'W', 'title': 'Article 14 worksheet — case map', 'date': 'Handout',
               'trail': 'Which decided case each of the 21 worksheet problems is modelled on',
               'sections': [{'id': 'WS-1', 'title': 'Case map for the 21 problems', 'html': ws_html, 'text': strip_tags(ws_html)}]})

# Q&A from both note sets
qa = []
for src, items in (('exam', exam['qa']), ('day', day['qa'])):
    for q in items:
        qa.append({'id': q['id'], 'kind': q['kind'], 'src': src, 'ch': q['chapter'], 'sec': q['section'],
                   'q': link_cases(apply_fixes(q['q_html']), None), 'a': link_cases(apply_fixes(q['a_html']), None)})

# corrections that never matched are a build error (the notes changed or the match string is wrong)
missing = [k for k, n in FIX_COUNT.items() if n == 0]
if missing:
    sys.exit(f'corrections not found in the notes: {missing}')

# ------------------------------------------------------------------ sources (lecture PDFs etc.)
import pymupdf  # noqa: E402

key = AESGCM.generate_key(bit_length=256)
aes = AESGCM(key)


def seal(raw: bytes) -> bytes:
    iv = secrets.token_bytes(12)
    return iv + aes.encrypt(iv, raw, None)


DATA.mkdir(parents=True, exist_ok=True)
(DATA / 's').mkdir(exist_ok=True)
for old in (DATA / 's').glob('*.bin'):
    old.unlink()

sources, pages = [], []
for i, meta in enumerate(SOURCES_META):
    p = ROOT / meta['path']
    raw = p.read_bytes()
    fid = hashlib.sha256(raw).hexdigest()[:16]
    (DATA / 's' / f'{fid}.bin').write_bytes(seal(raw))
    entry = {'id': fid, 'title': meta['title'], 'date': meta['date'], 'group': meta['group'],
             'topics': meta['topics'], 'kind': 'pdf' if p.suffix == '.pdf' else 'docx',
             'file': p.name, 'size': len(raw)}
    if p.suffix == '.pdf':
        d = pymupdf.open(str(p))
        entry['pages'] = len(d)
        for pn, pg in enumerate(d, 1):
            t = re.sub(r'\s+', ' ', pg.get_text()).strip()
            if len(t) > 40:
                pages.append({'s': fid, 'p': pn, 't': t})
    sources.append(entry)

# ------------------------------------------------------------------ bundle
for c in REG.values():
    c.pop('aliases')
bundle = {
    'built': __import__('datetime').date.today().isoformat(),
    'exam': exam_ch, 'day': day_ch, 'cases': list(REG.values()),
    'cards': exam['cases'] + day['cases'],
    'qa': qa, 'articles': articles, 'corrections': CORRECTIONS, 'amendments': AMENDMENTS,
    'solvers': SOLVERS, 'sources': sources, 'pages': pages,
}
for card in bundle['cards']:
    card['reg'] = match_key(card['name'])
raw = json.dumps(bundle, ensure_ascii=False, separators=(',', ':')).encode()
(DATA / 'c.bin').write_bytes(seal(gzip.compress(raw, 9)))

# ------------------------------------------------------------------ key wrapping
salt = secrets.token_bytes(16)
kek = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, PBKDF2_ITER, dklen=32)
wiv = secrets.token_bytes(12)
wrapped = AESGCM(kek).encrypt(wiv, key, b'cln-key-v1')
(DATA / 'key.json').write_text(json.dumps({
    'v': 1, 'kdf': 'PBKDF2-SHA256', 'iter': PBKDF2_ITER,
    'salt': base64.b64encode(salt).decode(), 'iv': base64.b64encode(wiv).decode(),
    'wrapped': base64.b64encode(wrapped).decode(), 'aad': 'cln-key-v1'}, indent=1))

print(f'content {len(raw)/1e6:.2f} MB raw -> {(DATA / "c.bin").stat().st_size/1e6:.2f} MB sealed; '
      f'{len(sources)} sources, {len(pages)} source pages; {len(REG)} cases '
      f'({sum(1 for c in REG.values() if c["seen"])} linked in notes); {len(qa)} Q&A; '
      f'{sum(FIX_COUNT.values())} correction marks')
