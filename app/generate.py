"""Render both outputs from the same validated proposal and Decimal quote.

Both documents are the supplied, completed reference proposal with client values swapped in.
Design and formatting come entirely from templates/proposal.pptx and templates/agreement.docx
(see scripts/prepare_templates.py); nothing here adds slides, pages or styling.
"""
import copy
import io
import re
from collections import OrderedDict
from decimal import Decimal
from pathlib import Path

from docx import Document
from docx.table import _Row
from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

from app.textfill import fill_lines, paragraphs, replace, text

TEMPLATES = Path(__file__).resolve().parents[1] / 'templates'
VERSION = '2026.10-v3'
STATUS = {'Included': 'YES', 'Excluded': 'NO', 'Not applicable': 'NA'}
# Shape ids on the pricing slide (slide 12) of the reference deck, for cards with nothing to show.
SECURITY_CARD = [5]
BACKUP_CARD = [9, 10, 15, 16, 17, 19, 6, 13, 31, 36]
PRICING_SLIDE, CURRENT_STATE_SLIDE, RATES_SLIDE = 11, 10, 12
ENVIRONMENT_SLIDE = 11  # Where the generated Your Environment slide(s) go: right after Current State.


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


def bullets(value):
    """One bullet per line, and per comma- or semicolon-separated item within a line."""
    return [item.strip() for line in value.splitlines() for item in re.split(r'[,;]', line) if item.strip()]


def current_state(p):
    """Current State bullets: the entered current state (or the device counts), then the pain points."""
    lines = bullets(p.current_state)
    if not lines:
        lines = [f'{p.workstations} desktops/laptops'] if p.workstations else []
        if p.servers:
            lines.append(f'{p.servers} server{"s" if p.servers != 1 else ""}')
    lines += bullets(p.needs)
    return lines or ['']


CURRENT_STATE_FIT = 10  # Bullets that fit the Current State card at the reference 11.5 pt.


def fit_bullets(shape, count):
    """Shrink the Current State bullets when there are more than fit at the reference size."""
    if count <= CURRENT_STATE_FIT:
        return
    scale = max(CURRENT_STATE_FIT / count, 0.6)
    for para in shape.text_frame.paragraphs:
        for run in para.runs:
            if run.font.size:
                run.font.size = int(run.font.size * scale)
        for spc in para._p.iter(qn('a:spcPts')):
            spc.set('val', str(int(int(spc.get('val')) * scale)))


CLIENT_FIT = 26  # Characters of the 48 pt client name that fit on one line of the closing slide.


def fit_client(shape, client):
    """Shrink a long client name on the closing slide so it stays on one line below "Thank you,";
    names too long even at the minimum size wrap downward instead of growing into the line above."""
    if len(client) <= CLIENT_FIT:
        return
    size = max(48 * CLIENT_FIT / len(client), 22)
    for para in shape.text_frame.paragraphs:
        for run in para.runs:
            run.font.size = Pt(size)
    if size * len(client) > 48 * CLIENT_FIT:  # Still wraps at the minimum size.
        shape.text_frame.word_wrap = True
        shape.text_frame.vertical_anchor = MSO_ANCHOR.TOP


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


# ---------------------------------------------------------------------------
# Inventory recap: an appendix slide assembled from copies of the deck's own elements
# (logo, heading styles and card from slide 11, colour tiles from slide 13), so fonts,
# colours and shadows match the reference slides exactly.
# ---------------------------------------------------------------------------
EMU_IN = 914400
LEFT, WIDTH = 457200, 8229600
TILE_TOP, TILE_H, TILE_GAP = 1280160, 1005840, 109728
CARD_BOTTOM, CARD_HEADER, ROW_H, CARD_PAD = 4617720, 411480, 228600, 182880
COLUMNS = [('TYPE', 1554480), ('DESCRIPTION', 3657600), ('LOCATION / CLOUD', 2011680), ('QTY', 640080)]
SLATE, MUTED, BORDER, BAND = '334155', '64748B', 'E2E8F0', 'F8FAFC'


def _clone(source_slide, shape_id, target):
    """Copy a shape (and the image it shows) from a reference slide onto target."""
    source = next(s for s in source_slide.shapes if s.shape_id == shape_id)
    element = copy.deepcopy(source._element)
    for blip in element.iter(qn('a:blip')):
        image_part = source_slide.part.related_part(blip.get(qn('r:embed')))
        blip.set(qn('r:embed'), target.part.relate_to(image_part, RT.IMAGE))
    target.shapes._spTree.append(element)
    shape = target.shapes[-1]
    shape._element.xpath('./*[1]/p:cNvPr')[0].set('id', str(max(s.shape_id for s in target.shapes) + 1))
    return shape


def _place(shape, x, y, w, h):
    shape.left, shape.top, shape.width, shape.height = int(x), int(y), int(w), int(h)
    return shape


def _set_text(shape, value):
    paras = paragraphs(shape._element)
    for extra in paras[1:]:
        extra.getparent().remove(extra)
    replace(paras[0], text(paras[0]), value)
    return shape


def _cell(cell, value, size, color, bold=False, spacing=None, fill=None, align=PP_ALIGN.LEFT):
    cell.margin_left = cell.margin_right = Emu(64008)
    cell.margin_top = cell.margin_bottom = Emu(0)
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    if fill:
        cell.fill.solid()
        cell.fill.fore_color.rgb = RGBColor.from_string(fill)
    else:
        cell.fill.background()
    para = cell.text_frame.paragraphs[0]
    para.alignment = align
    run = para.add_run()
    run.text = value
    run.font.name, run.font.size, run.font.bold = 'Calibri', Pt(size), bold
    run.font.color.rgb = RGBColor.from_string(color)
    if spacing:
        run.font._rPr.set('spc', str(spacing))
    # Hairline row divider, as on the reference cards.
    tcPr = cell._tc.get_or_add_tcPr()
    for edge in ('a:lnL', 'a:lnR', 'a:lnT', 'a:lnB'):
        line = tcPr.find(qn(edge))
        if line is not None:
            tcPr.remove(line)
    for edge, visible in (('a:lnL', False), ('a:lnR', False), ('a:lnT', False), ('a:lnB', True)):
        line = etree.SubElement(tcPr, qn(edge), w='6350' if visible else '0')
        if visible:
            etree.SubElement(etree.SubElement(line, qn('a:solidFill')), qn('a:srgbClr'), val=BORDER)
        else:
            etree.SubElement(line, qn('a:noFill'))
    # Borders must precede the cell fill in tcPr.
    for edge in ('a:lnB', 'a:lnT', 'a:lnR', 'a:lnL'):
        tcPr.insert(0, tcPr.find(qn(edge)))


def _equipment_table(slide, rows, top):
    height = ROW_H * (len(rows) + 1)
    frame = slide.shapes.add_table(len(rows) + 1, len(COLUMNS), Emu(LEFT + CARD_PAD), Emu(top),
                                   Emu(WIDTH - 2 * CARD_PAD), Emu(height))
    table = frame.table
    style = frame._element.graphic.graphicData.tbl.tblPr.find(qn('a:tableStyleId'))
    if style is not None:
        style.getparent().remove(style)
    table.first_row = table.horz_banding = False
    for index, (title, width) in enumerate(COLUMNS):
        table.columns[index].width = Emu(width)
        _cell(table.cell(0, index), title, 8.5, MUTED, bold=True, spacing=200,
              align=PP_ALIGN.RIGHT if title == 'QTY' else PP_ALIGN.LEFT)
    for r, values in enumerate(rows, start=1):
        for c, value in enumerate(values):
            _cell(table.cell(r, c), value, 10.5, SLATE, bold=(c == 0), fill=BAND if r % 2 == 0 else None,
                  align=PP_ALIGN.RIGHT if c == len(values) - 1 else PP_ALIGN.LEFT)
    for row in table.rows:
        row.height = Emu(ROW_H)


def inventory_slides(prs, p):
    """Append the Your Environment slide(s), then move them to just after Current State."""
    path_slide, rates_slide = prs.slides[CURRENT_STATE_SLIDE], prs.slides[RATES_SLIDE]
    before = len(prs.slides)
    _build_inventory_slides(prs, p, path_slide, rates_slide)
    id_list = prs.slides._sldIdLst
    for offset, entry in enumerate(list(id_list)[before:]):
        id_list.remove(entry)
        id_list.insert(ENVIRONMENT_SLIDE + offset, entry)


def _build_inventory_slides(prs, p, path_slide, rates_slide):
    rows = [(a.kind, a.description, a.location or '—', str(a.quantity)) for a in p.assets] or \
           [('—', 'No equipment listed', '—', '0')]
    first_capacity = (CARD_BOTTOM - (TILE_TOP + TILE_H + 137160) - CARD_HEADER - 2 * 91440) // ROW_H - 1
    later_capacity = (CARD_BOTTOM - TILE_TOP - CARD_HEADER - 2 * 91440) // ROW_H - 1
    chunks, start = [], 0
    while start < len(rows) or not chunks:
        size = first_capacity if not chunks else later_capacity
        chunks.append(rows[start:start + size])
        start += size
    for number, chunk in enumerate(chunks):
        slide = prs.slides.add_slide(path_slide.slide_layout)
        for shape_id in (2, 3, 4, 26):  # Logo, eyebrow, title, footer.
            _clone(path_slide, shape_id, slide)
        eyebrow, title = slide.shapes[1], slide.shapes[2]
        _set_text(eyebrow, 'IN SCOPE')
        _set_text(title, 'Your Environment' + (' (continued)' if number else ''))
        card_top = TILE_TOP
        if number == 0:
            tiles = [('USERS', p.users, 'Supported users'), ('WORKSTATIONS', p.workstations, 'Desktops & laptops'),
                     ('SERVERS', p.servers, 'Physical & cloud'), ('NETWORKS', p.networks, 'Managed networks'),
                     ('MOBILE', p.mobile_devices, 'Phones & tablets')]
            width = (WIDTH - TILE_GAP * (len(tiles) - 1)) / len(tiles)
            for index, (label, value, caption) in enumerate(tiles):
                x = LEFT + index * (width + TILE_GAP)
                ids = (5, 6, 7, 9) if index % 2 == 0 else (10, 11, 12, 14)  # Green and navy tiles.
                box, top_label, figure, note = (_clone(rates_slide, i, slide) for i in ids)
                _place(box, x, TILE_TOP, width, TILE_H)
                _set_text(_place(top_label, x + 164592, TILE_TOP + 118872, width - 329184, 228600), label)
                for run in top_label._element.iter(qn('a:rPr')):
                    run.set('spc', '150')  # Five tiles are narrower than the two on slide 13.
                _set_text(_place(figure, x + 164592, TILE_TOP + 338328, width - 329184, 457200), str(value))
                _set_text(_place(note, x + 164592, TILE_TOP + 777240, width - 329184, 182880), caption)
            card_top = TILE_TOP + TILE_H + 137160
        card, bar, heading = (_clone(path_slide, i, slide) for i in (5, 6, 7))
        _place(card, LEFT, card_top, WIDTH, CARD_BOTTOM - card_top)
        _place(bar, LEFT, card_top, WIDTH, CARD_HEADER)
        _set_text(_place(heading, LEFT, card_top, WIDTH, CARD_HEADER), 'EQUIPMENT IN SCOPE')
        _equipment_table(slide, chunk, card_top + CARD_HEADER + 91440)


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
    state = current_state(p)
    multiline = {'{{current_state}}': state, '{{core_detail}}': detail(core, '  ') or [''],
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
                if index == CURRENT_STATE_SLIDE and shape.shape_id == 8:
                    fit_bullets(shape, len(state))
                if index == len(prs.slides) - 1 and shape.text_frame.text == p.client:
                    fit_client(shape, p.client)
                # Long company names wrap inside the original cover text box.
                if index == 0 and p.client in shape.text_frame.text and len(p.client) > 30:
                    shape.text_frame.word_wrap = True
                    for para in shape.text_frame.paragraphs:
                        for run in para.runs:
                            if p.client in run.text:
                                run.font.size = Pt(20)
    inventory_slides(prs, p)
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
