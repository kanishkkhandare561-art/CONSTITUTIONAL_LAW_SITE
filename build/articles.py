"""Bare text of the Articles covered in the course, for the Article explorer.

Source: civictech-India/constitution-of-india (public dataset, source/data/constitution_of_india.json).
That dataset is not fully up to date, so the Articles used here were checked against the amendments that
touch them, and three places are patched below (97th Amendment: Art 19(1)(c) and Art 43B; 86th
Amendment: Art 45).  Notes record later judicial developments.
"""
import json, re, sys
from pathlib import Path

SRC = Path('source/data/constitution_of_india.json')
OUT = Path('content/articles.json')

PART = {
 '0': 'Preamble',
}
for a in list(range(12, 36)) + ['21A', '31A', '31B', '31C', '31D', '32A']:
    PART[str(a)] = 'Part III — Fundamental Rights'
for a in list(range(36, 52)) + ['39A', '43A', '43B', '48A']:
    PART[str(a)] = 'Part IV — Directive Principles'
PART['51A'] = 'Part IVA — Fundamental Duties'
PART['300A'] = 'Part XII — Right to Property'
for a in ('352', '358', '359'):
    PART[a] = 'Part XVIII — Emergency Provisions'
PART['368'] = 'Part XX — Amendment'

PATCH = {
 '19': [('(c) to form associations or unions;', '(c) to form associations or unions or co-operative societies;'),
        ('sovereignty andintegrity', 'sovereignty and integrity')],
 '45': [('The State shall endeavour to provide, within a period of ten years from the commencement of this Constitution, for free and compulsory education for all children until they complete the age of fourteen years.',
         'The State shall endeavour to provide early childhood care and education for all children until they complete the age of six years.')],
}
TITLE = {'45': 'Provision for early childhood care and education to children below the age of six years'}
ADD = {
 '43B': ('Promotion of co-operative societies',
         'The State shall endeavour to promote voluntary formation, autonomous functioning, democratic control and professional management of co-operative societies.'),
}
NOTES = {
 '0': 'The words "SOCIALIST SECULAR" and "and integrity" were added by the 42nd Amendment (1976). Kesavananda Bharati (1973) held the Preamble is part of the Constitution.',
 '12': 'Tests for "other authorities": Ajay Hasia (1981) and Pradeep Kumar Biswas (2002, deep and pervasive control).',
 '13': 'Clause (4) was inserted by the 24th Amendment (1971) after Golak Nath. Doctrines: eclipse (pre-Constitution laws), severability, waiver.',
 '15': 'Clause (4): 1st Amendment (1951) after Champakam Dorairajan. Clause (5): 93rd Amendment (2005). Clause (6) and the Explanation (EWS): 103rd Amendment (2019), upheld in Janhit Abhiyan (2022).',
 '16': 'Clause (4A): 77th (1995) and 85th (2001) Amendments; clause (4B): 81st (2000); clause (6) EWS: 103rd (2019). See Indra Sawhney (1992), M. Nagaraj (2006), Jarnail Singh (2018).',
 '19': 'Sub-clause (f) (property) was omitted by the 44th Amendment (1978). Clause (2) was widened by the 1st Amendment (1951: public order, friendly relations, incitement to an offence) and the 16th Amendment (1963: sovereignty and integrity). "Or co-operative societies" in sub-clause (c) was added by the 97th Amendment (2011).',
 '21': 'Read with Arts 14 and 19 since Maneka Gandhi (1978). Cannot be suspended in an Emergency (Art 359, as amended by the 44th Amendment).',
 '21A': 'Inserted by the 86th Amendment (2002), in force from 1 April 2010 with the RTE Act, 2009.',
 '31': 'Repealed by the 44th Amendment (1978, w.e.f. 20 June 1979); the right to property now lives in Art 300A.',
 '31C': 'The 42nd Amendment\'s extension of Art 31C to "all or any of the principles laid down in Part IV" was struck down in Minerva Mills (1980). In Property Owners Association v. State of Maharashtra (5 November 2024) a nine-judge bench held that Art 31C continues in the form upheld in Kesavananda — protecting laws giving effect to Art 39(b) and (c). The dataset text below shows the struck-down 42nd-Amendment wording.',
 '39': 'On clause (b): Property Owners Association (2024) held, 8:1, that not every item of private property is a "material resource of the community".',
 '43B': 'Inserted by the 97th Amendment (2011). Parts of that amendment (Part IXB, as applied to State co-operative societies) were struck down in Union of India v. Rajendra N. Shah (2021); Art 43B was not.',
 '45': 'Substituted by the 86th Amendment (2002). The original Art 45 (free and compulsory education up to 14 within ten years) became the Fundamental Right in Art 21A.',
 '300A': 'Inserted by the 44th Amendment (1978). A constitutional (not fundamental) right: K.T. Plantation (2011), Vidya Devi (2020), Bimal Kumar Shah (2024).',
 '359': 'The words "(except articles 20 and 21)" were added by the 44th Amendment (1978), after ADM Jabalpur.',
 '368': 'Clauses (4) and (5), inserted by the 42nd Amendment, were struck down in Minerva Mills (1980) but remain printed in the text. Clause (3) and the word "constituent power" were added by the 24th Amendment (1971).',
 '17': 'PUDR (1982): Arts 17, 23 and 24 operate against private persons too.',
 '20': 'Clause (3) — right against self-incrimination: Nandini Satpathy (1978).',
 '22': 'The 44th Amendment\'s changes to Art 22(4) and (7) have never been brought into force; the original text still applies.',
}

KEEP = ['0'] + [str(a) for a in range(12, 36)] + ['21A', '31A', '31B', '31C', '32A'] + \
       [str(a) for a in range(36, 52)] + ['39A', '43A', '43B', '48A', '51A', '300A', '352', '358', '359', '368']


def clean(t):
    t = t.replace('\xa0', ' ').replace('’’', '”')
    t = re.sub(r'\b\d+\s*\[', '', t)            # footnote markers like "4 ["
    # drop unbalanced brackets left over from amendment markers
    out, depth = [], 0
    for ch in t:
        if ch == '[':
            depth += 1; out.append(ch)
        elif ch == ']':
            if depth:
                depth -= 1; out.append(ch)
        else:
            out.append(ch)
    t = ''.join(out)
    t = re.sub(r'\(\s*$', '', t.strip())
    t = re.sub(r'[ \t]+\n', '\n', t)
    t = re.sub(r'\n{2,}', '\n', t)
    return '\n'.join(l.rstrip() for l in t.split('\n') if l.strip())


def key(k):
    m = re.match(r'(\d+)(\w*)', k)
    return (int(m.group(1)), m.group(2))


def main():
    data = json.loads(SRC.read_text())
    A = {str(a['article']): a for a in data}
    out = []
    for k in sorted(set(KEEP) | set(ADD), key=key):
        if k in ADD:
            title, text = ADD[k]
        elif k in A:
            title, text = A[k]['title'], A[k]['description']
        else:
            continue
        title = TITLE.get(k, title)
        text = clean(text)
        for old, new in PATCH.get(k, []):
            if old not in text:
                sys.exit(f'patch for Art {k} did not apply')
            text = text.replace(old, new)
        out.append({'n': k, 'label': 'Preamble' if k == '0' else f'Article {k}', 'title': title.strip().rstrip('.'),
                    'part': PART.get(k, ''), 'text': text, 'note': NOTES.get(k, '')})
    OUT.write_text(json.dumps(out, ensure_ascii=False))
    print(len(out), 'articles ->', OUT)


main()
