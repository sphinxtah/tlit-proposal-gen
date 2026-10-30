"""Render both outputs from the same validated proposal and Decimal quote.

Both documents are the supplied, completed reference proposal with client values swapped in.
Design and formatting come entirely from templates/proposal.pptx and templates/agreement.docx
(see scripts/prepare_templates.py); nothing here adds slides, pages or styling.
"""
import copy
import io
from collections import OrderedDict
from decimal import Decimal
from pathlib import Path

from docx import Document
from docx.table import _Row
from pptx import Presentation
from pptx.util import Pt

from app.textfill import fill_lines, paragraphs, replace, text

TEMPLATES = Path(__file__).resolve().parents[1] / 'templates'
VERSION = '2026.10-v3'
STATUS = {'Included': 'YES', 'Excluded': 'NO', 'Not applicable': 'NA'}
# Shape ids on the pricing slide (slide 12) of the reference deck, for cards with nothing to show.
SECURITY_CARD = [5]
BACKUP_CARD = [9, 10, 15, 16, 17, 19, 6, 13, 31, 36]
PRICING_SLIDE, CURRENT_STATE_SLIDE = 11, 10


def money(x):
    return f'${x:,.2f}'


def money_short(x):
    """$500 for whole amounts, $500.50 otherwise (as written in the reference proposal)."""
    return f'${x:,.0f}' if x == x.to_integral_value() else money(x)


def us_date(d):
    return d.strftime('%m/%d/%Y') if d else '__________'


ONES = 'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
TENS = 'twenty thirty forty fifty sixty seventy eighty ninety'.split()


def number_words(n):
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10 - 2] + ('-' + ONES[n % 10] if n % 10 else '')
    return ONES[n // 100] + ' hundred' + (' ' + number_words(n % 100) if n % 100 else '')


def term(months):
    n, unit = (months // 12, 'year') if months % 12 == 0 else (months, 'month')
    return f'{number_words(n)} ({n}) {unit}{"" if n == 1 else "s"}'


def monthly_lines(q, category):
    return [x for x in q['lines'] if x['category'] == category and x['cadence'] == 'monthly']


def detail(lines, separator=' '):
    """'2 users × $25.00', grouping lines with the same unit and rate."""
    groups = OrderedDict()
    for x in lines:
        key = (x['unit'], Decimal(x['rate']))
        groups[key] = groups.get(key, 0) + x['quantity']
    return [f'{qty}{separator}{unit} × {money(rate)}' for (unit, rate), qty in groups.items()]


def total(lines):
    return sum((x['total'] for x in lines), Decimal('0'))


def device_count(p):
    return p.workstations + p.servers


def pricing_basis(p):
    return {'devices': f'{device_count(p)} Devices', 'users': f'{p.users} Users'}.get(
        p.billing_mode, f'{p.users} Users / {device_count(p)} Devices')


def fee_basis(p):
    return {'devices': f'Workstation/Server - {device_count(p):02d}', 'users': f'Users - {p.users:02d}'}.get(
        p.billing_mode, f'Users - {p.users:02d}, Workstation/Server - {device_count(p):02d}')


def fee_components(q):
    parts = ['Managed Services']
    if monthly_lines(q, 'security'):
        parts.append('Cybersecurity')
    if monthly_lines(q, 'backup'):
        parts.append('Backup')
    parts += [x['description'] for x in monthly_lines(q, 'other')]
    return ', '.join(parts)


def current_state(p):
    lines = [line.strip() for line in p.current_state.splitlines() if line.strip()]
    if lines:
        return lines
    derived = [f'{p.workstations} desktops/laptops'] if p.workstations else []
    if p.servers:
        derived.append(f'{p.servers} server{"s" if p.servers != 1 else ""}')
    return derived or ['']


def fill_tokens(root, values, multiline=None):
    multiline = multiline or {}
    for p in paragraphs(root):
        content = text(p)
        if '{{' not in content:
            continue
        for token, lines in multiline.items():
            if token in content:
                fill_lines(p, token, lines)
        for token, value in values.items():
            if token in content:
                replace(p, token, value)


def all_shapes(shapes):
    for shape in shapes:
        yield shape
        if shape.shape_type == 6:
            yield from all_shapes(shape.shapes)


HEADING_FIT = len('PROPOSAL PRICING – 4 Devices')  # The longest heading that clears the setup card at 12 pt.


def fit_heading(shape):
    """Shrink the pricing heading (font and letter spacing) only when it is longer than the reference one."""
    content = shape.text_frame.text
    if not content.startswith('PROPOSAL PRICING') or len(content) <= HEADING_FIT:
        return
    scale = max(HEADING_FIT / len(content), 0.55)
    for para in shape.text_frame.paragraphs:
        for run in para.runs:
            if run.font.size:
                run.font.size = int(run.font.size * scale)
            spacing = run.font._rPr.get('spc')
            if spacing:
                run.font._rPr.set('spc', str(int(int(spacing) * scale)))


def pptx_bytes(p, q):
    prs = Presentation(TEMPLATES / 'proposal.pptx')
    security, backup, core = monthly_lines(q, 'security'), monthly_lines(q, 'backup'), monthly_lines(q, 'core')
    values = {
        '{{client}}': p.client, '{{proposal_month}}': p.proposal_date.strftime('%B %Y'),
        '{{pricing_basis}}': pricing_basis(p), '{{monthly}}': money(q['net']),
        '{{core_monthly}}': money(total(core)), '{{core_total}}': money(total(core)),
        '{{onboarding}}': money_short(p.onboarding),
        '{{security_monthly}}': money(total(security)), '{{security_total}}': money(total(security)),
        '{{backup_label}}': p.backup_label, '{{backup_monthly}}': money(total(backup)), '{{backup_total}}': money(total(backup)),
        '{{hourly_rate}}': money_short(p.hourly_rate), '{{after_hours_rate}}': money_short(p.after_hours_rate),
    }
    multiline = {'{{current_state}}': current_state(p), '{{core_detail}}': detail(core, '  ') or [''],
                 '{{security_detail}}': detail(security) or [''], '{{backup_detail}}': detail(backup) or ['']}
    for index, slide in enumerate(prs.slides):
        if index == PRICING_SLIDE:
            hidden = (SECURITY_CARD if not security else []) + (BACKUP_CARD if not backup else [])
            for shape in list(all_shapes(slide.shapes)):
                if shape.shape_id in hidden:
                    shape._element.getparent().remove(shape._element)
        for shape in all_shapes(slide.shapes):
            if shape.has_text_frame:
                fill_tokens(shape._element, values, multiline)
                if index == PRICING_SLIDE:
                    fit_heading(shape)
                # Long company names wrap inside the original cover text box.
                if index == 0 and p.client in shape.text_frame.text and len(p.client) > 30:
                    shape.text_frame.word_wrap = True
                    for para in shape.text_frame.paragraphs:
                        for run in para.runs:
                            if p.client in run.text:
                                run.font.size = Pt(20)
    prs.core_properties.title = f'Managed IT services proposal - {p.client}'
    stream = io.BytesIO()
    prs.save(stream)
    return stream.getvalue()


def _cells(row):
    seen, out = set(), []
    for cell in row.cells:
        if id(cell._tc) not in seen:
            seen.add(id(cell._tc))
            out.append(cell)
    return out


def _set_cell(cell, value):
    first = cell.paragraphs[0]
    replace(first._p, text(first._p), value)


def schedule_b(doc, services):
    """Set coverage on the reference Schedule B rows; drop rows not in scope; append custom services."""
    wanted = OrderedDict((s.description.strip(), s) for s in services)
    seen, last_table = set(), doc.tables[3]
    # Added services copy a single-line service row from the table they are appended to (same column grid).
    prototype = [copy.deepcopy(r._tr) for i, r in enumerate(last_table.rows) if _row_kind(r, i, 1) == 'item'
                 and all(len(c.paragraphs) == 1 for c in _cells(r))][-1]
    for table in doc.tables[2:4]:
        for row in list(table.rows):
            cells = _cells(row)
            if cells[-1].text.strip() not in STATUS.values():
                continue
            description = cells[0].text.strip()
            service = wanted.get(description)
            if service is None or description in seen:
                row._tr.getparent().remove(row._tr)
                continue
            seen.add(description)
            if cells[1].text.strip() != service.frequency:
                _set_cell(cells[1], service.frequency)
            _set_cell(cells[-1], STATUS[service.status])
    extra = [s for d, s in wanted.items() if d not in seen]
    rows = last_table._tbl.tr_lst
    anchor = rows[-2] if len(rows) > 1 and not ''.join(c.text for c in _cells(last_table.rows[-1])).strip() else rows[-1]
    if extra:
        heading = [r for i, r in enumerate(last_table.rows) if _row_kind(r, i, 1) == 'heading'][-1]
        clone = copy.deepcopy(heading._tr)
        anchor.addnext(clone)
        anchor = clone
        _set_cell(_cells(_Row(clone, last_table))[0], 'Additional Services')
    for service in extra:
        clone = copy.deepcopy(prototype)
        anchor.addnext(clone)
        anchor = clone
        cells = _cells(_Row(clone, last_table))
        _set_cell(cells[0], service.description)
        _set_cell(cells[1], service.frequency)
        _set_cell(cells[-1], STATUS[service.status])
    # Category headings ("Servers", "Disaster Recovery") whose services were all removed are dropped too.
    for table, first in ((doc.tables[2], 2), (doc.tables[3], 1)):
        rows = list(table.rows)
        kinds = [_row_kind(r, i, first) for i, r in enumerate(rows)]
        for i, kind in enumerate(kinds):
            following = [k for k in kinds[i + 1:] if k != 'blank']
            if kind == 'heading' and (not following or following[0] != 'item'):
                rows[i]._tr.getparent().remove(rows[i]._tr)


def _row_kind(row, index, first):
    cells = _cells(row)
    if index < first:
        return 'fixed'
    if cells[-1].text.strip() in STATUS.values():
        return 'item'
    return 'heading' if len(cells) == 1 and cells[0].text.strip() else 'blank'


def docx_bytes(p, q):
    doc = Document(TEMPLATES / 'agreement.docx')
    one_time = sum((x['total'] for x in q['lines'] if x['cadence'] == 'one-time'), Decimal('0'))
    values = {
        '{{client}}': p.client, '{{proposal_date}}': us_date(p.proposal_date), '{{contact}}': p.contact,
        '{{phone}}': p.phone, '{{prepared_by}}': p.prepared_by, '{{msa_date}}': us_date(p.msa_date),
        '{{effective_date}}': us_date(p.effective_date), '{{initial_term}}': term(p.term_months),
        '{{renewal_term}}': term(p.renewal_months), '{{notice_days}}': str(p.notice_days),
        '{{setup_fee}}': money_short(one_time), '{{monthly_fee}}': money(q['net']),
        '{{fee_basis}}': fee_basis(p), '{{fee_components}}': fee_components(q),
        '{{hourly_rate}}': money_short(p.hourly_rate), '{{after_hours_rate}}': money_short(p.after_hours_rate),
        '{{workstations}}': str(p.workstations), '{{networks}}': str(p.networks),
        '{{servers}}': str(p.servers), '{{mobile_devices}}': str(p.mobile_devices),
    }
    address = [line.strip() for line in p.address.splitlines() if line.strip()] or ['']
    fill_tokens(doc.element.body, values, {'{{address}}': address})
    schedule_b(doc, p.services)
    doc.core_properties.title = f'Managed IT Services - {p.client}'
    stream = io.BytesIO()
    doc.save(stream)
    return stream.getvalue()
