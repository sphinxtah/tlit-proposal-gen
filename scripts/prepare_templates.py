"""One-time extraction from the supplied examples. Originals remain unchanged."""
import json
import argparse
from pathlib import Path
from docx import Document
from pptx import Presentation

root = Path(__file__).resolve().parents[1]
out = root/'templates'
out.mkdir(exist_ok=True)
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--document',required=True)
parser.add_argument('--presentation',required=True)
parser.add_argument('--client-name',required=True)
parser.add_argument('--proposal-month',required=True)
args=parser.parse_args()
doc = Document(args.document)
paragraphs = [p.text for p in doc.paragraphs]
start = paragraphs.index('Definitions - Any capitalized terms used but not defined in this SOW will have the meaning set forth in the General Terms or elsewhere in the Agreement.  This SOW consists of the SOW Cover Page, these Additional Terms, and the SOW Schedules set forth on the SOW Cover Page.')
end = paragraphs.index('TeamLogic IT Managed Services')
terms = [s for s in paragraphs[start:end] if s.strip()]
(out/'terms.json').write_text(json.dumps(terms, indent=2), encoding='utf-8')
services = []
for table in doc.tables[2:4]:
    for row in table.rows:
        cells = [c.text.strip() for c in row.cells]
        if cells[-1] in ('YES','NO','NA'):
            services.append(dict(description=cells[0], frequency=cells[1], status={'YES':'Included','NO':'Excluded','NA':'Not applicable'}[cells[-1]]))
(out/'services.json').write_text(json.dumps(services, indent=2), encoding='utf-8')
payment_start=paragraphs.index('Recurring Payment Authorization Form')
(out/'payment.json').write_text(json.dumps([s for s in paragraphs[payment_start:] if s.strip()],indent=2),encoding='utf-8')
# Keep the supplied marketing slides and branding. Replace client-specific slides
# with simple editable content layouts, avoiding stale pricing or inventory.
p = Presentation(args.presentation)
for idx in [12,11,10]:
    sid = p.slides._sldIdLst[idx]
    p.part.drop_rel(sid.rId)
    p.slides._sldIdLst.remove(sid)
for slide in p.slides:
    if slide.has_notes_slide:
        slide.notes_slide.notes_text_frame.text = ''
    for shape in slide.shapes:
        if not shape.has_text_frame: continue
        for para in shape.text_frame.paragraphs:
            for run in para.runs:
                run.text = run.text.replace(args.client_name,'{{client}}').replace(args.proposal_month,'{{proposal_month}}')
        if ' / 14' in shape.text or ' / 15' in shape.text:
            shape.text = ''
p.core_properties.title = 'TeamLogic IT proposal template'
p.core_properties.author = 'TeamLogic IT Scottsdale'
p.save(out/'proposal.pptx')

# Demo data is maintained separately in example.json. Never commit real client data.
