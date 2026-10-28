"""Render both outputs from the same validated proposal and Decimal quote."""
import io
import json
import textwrap
import math
from pathlib import Path
from xml.sax.saxutils import escape
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

TEMPLATES = Path(__file__).resolve().parents[1]/'templates'
VERSION = '2026.10-v2'

def money(x): return f'${x:,.2f}'

def shapes(items):
    for shape in items:
        yield shape
        if shape.shape_type == 6:
            yield from shapes(shape.shapes)

def pptx_bytes(p, q):
    prs = Presentation(TEMPLATES/'proposal.pptx')
    for slide in prs.slides:
        for sh in shapes(slide.shapes):
            if sh.has_text_frame:
                for para in sh.text_frame.paragraphs:
                    for run in para.runs:
                        run.text=run.text.replace('{{client}}',p.client).replace('{{proposal_month}}',p.proposal_date.strftime('%B %Y'))
                # Long company names wrap inside the original cover text box.
                if p.client in sh.text and len(p.client)>30:
                    sh.text_frame.word_wrap=True
                    for para in sh.text_frame.paragraphs:
                        for run in para.runs: run.font.size=Pt(20)
    # New client-specific slides are inserted before the original closing slide.
    def textbox(slide, text, x,y,w,h, size=17, color='182338', bold=False):
        box=slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        box.text_frame.word_wrap=True
        box.text_frame.margin_left=box.text_frame.margin_right=0
        box.text_frame.text=text
        for para in box.text_frame.paragraphs:
            para.font.name='Arial';para.font.size=Pt(size);para.font.bold=bold;para.font.color.rgb=RGBColor.from_string(color)
        return box
    def slide(title):
        s=prs.slides.add_slide(prs.slide_layouts[0])
        for sh in list(s.shapes):
            s.shapes._spTree.remove(sh._element)
        s.background.fill.solid();s.background.fill.fore_color.rgb=RGBColor.from_string('F7F9FB')
        bar=s.shapes.add_shape(MSO_SHAPE.RECTANGLE,0,0,prs.slide_width,Inches(.7))
        bar.fill.solid();bar.fill.fore_color.rgb=RGBColor.from_string('FFFFFF');bar.line.fill.background()
        s.shapes.add_picture(str(TEMPLATES/'header-logo.png'),Inches(.5),Inches(.12),height=Inches(.46))
        header=textbox(s,'SCOTTSDALE',7,.2,2.5,.3,10,'0C5845',True)
        header.text_frame.paragraphs[0].alignment=PP_ALIGN.RIGHT
        title_box=textbox(s,title,.5,.85,9,.65,26,bold=True)
        title_box.text_frame.paragraphs[0].alignment=PP_ALIGN.CENTER
        textbox(s,p.client,.5,5.12,8,.25,10,'59667A')
        # Move before closing.
        ids=prs.slides._sldIdLst; item=ids[-1];ids.remove(item);ids.insert(len(ids)-1,item)
        return s
    def paragraphs(title, entries):
        lines=[]
        for label,value in entries:
            if value:
                lines.extend(textwrap.wrap(f'{label}: {value}',width=82,replace_whitespace=True))
                lines.append('')
        for offset in range(0,max(1,len(lines)),14):
            s=slide(title if offset==0 else title+' (continued)')
            box=textbox(s,'\n'.join(lines[offset:offset+14]),.5,1.55,9,3.4,15)
            for para in box.text_frame.paragraphs:
                para.line_spacing=Pt(17)
                para.alignment=PP_ALIGN.CENTER
    paragraphs('Your environment', [('Users',str(p.users)),('Workstations',str(p.workstations)),('Servers',str(p.servers)),('Cloud',p.cloud),('Identity / domain',p.domain),('Backups',p.backups),('Security',p.security),('Applications',p.applications)])
    paragraphs('Priorities and proposed approach',[('Business needs',p.needs),('Recommendations',p.recommendations),('Excluded',p.exclusions)])
    rows = [[x['description'],str(x['quantity']),money(x['rate']),money(x['total'])+('/mo' if x['cadence']=='monthly' else ' once')] for x in q['lines']]
    batches=[];batch=[];height=.36
    for row in rows:
        row_height=max(.36,.19*max(1,len(textwrap.wrap(row[0],width=52)))+.14)
        if batch and height+row_height>2.2:
            batches.append(batch);batch=[];height=.36
        batch.append((row,row_height));height+=row_height
    if batch or not batches:batches.append(batch)
    for batch_index,batch in enumerate(batches):
        s=slide('Your investment' if batch_index==0 else 'Your investment (continued)')
        textbox(s,f"{money(q['monthly'])} / month",.5,1.45,9,.5,25,'008D69',True)
        subset=[row for row,h in batch]
        heights=[.36]+[h for row,h in batch]
        table=s.shapes.add_table(len(subset)+1,4, Inches(.5), Inches(2.1), Inches(9), Inches(sum(heights))).table
        for tr,h in zip(table.rows,heights):tr.height=Inches(h)
        widths=[4.7,.6,1.5,2.2]
        for c,w in zip(table.columns,widths):c.width=Inches(w)
        for ri,row in enumerate([['Service','Qty','Unit rate','Amount']]+subset):
            for ci,value in enumerate(row):
                cell=table.cell(ri,ci);cell.text=value
                cell.fill.solid();cell.fill.fore_color.rgb=RGBColor.from_string('0C5845' if ri==0 else ('E9F2EF' if ri%2 else 'FFFFFF'))
                for para in cell.text_frame.paragraphs:
                    para.font.name='Arial';para.font.size=Pt(11);para.font.color.rgb=RGBColor.from_string('FFFFFF' if ri==0 else '182338')
        textbox(s,f"Monthly discount: {money(q['discount'])}  |  Monthly tax: {money(q['tax'])}\nOne-time total: {money(q['one_time'])}  |  First month + setup: {money(q['first_month'])}",.5,4.48,9,.55,12)
    paragraphs('Service rates and terms', [('Business hours','Mon-Fri, 8:00 AM-5:00 PM MST, excluding holidays'),('Onsite / special projects',money(p.hourly_rate)+' per hour'),('After hours / weekends',money(p.after_hours_rate)+' per hour'),('Initial term',f'{p.term_months} months'),('Renewal term',f'{p.renewal_months} months'),('Nonrenewal notice',f'{p.notice_days} days'),('Tax',f'{p.tax_percent}% on taxable items; discount allocated proportionally')])
    prs.core_properties.title=f'Managed IT services proposal - {p.client}'
    stream=io.BytesIO();prs.save(stream);return stream.getvalue()

def pdf_bytes(p,q):
    stream=io.BytesIO()
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='BodyTL',fontName='Helvetica',fontSize=9.5,leading=14,spaceAfter=8,textColor=colors.HexColor('#243247')))
    styles.add(ParagraphStyle(name='HeadTL',fontName='Helvetica-Bold',fontSize=18,leading=23,spaceBefore=13,spaceAfter=14,textColor=colors.HexColor('#0C5845'),keepWithNext=True))
    styles.add(ParagraphStyle(name='CellTL',parent=styles['BodyTL'],fontSize=8.5,leading=12,spaceAfter=0))
    def para(text,style='BodyTL'):return Paragraph(escape(str(text)).replace('\n','<br/>'),styles[style])
    story=[]
    def heading(text):story.append(para(text,'HeadTL'))
    def table(rows,widths=None):
        t=Table([[para(v,'CellTL') for v in row] for row in rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#DCEEE7')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F4F7F8')]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
        story.extend([t,Spacer(1,12)])
    story.extend([para('TEAMLOGIC IT  /  SCOTTSDALE','HeadTL'),Spacer(1,20),para('Managed IT Services','Title'),Spacer(1,12),para(f'Statement of Work for {p.client}','HeadTL'),para(p.address),para(f'Prepared {p.proposal_date.isoformat()} by {p.prepared_by or "TeamLogic IT Scottsdale"}')])
    table([['Monthly investment','One-time charges','Initial term'],[money(q['monthly']),money(q['one_time']),f'{p.term_months} months']],[170,170,170])
    table([['Agreement detail','Value'],['Customer / authorized personnel',f'{p.client}\n{p.contact}\n{p.email}\n{p.phone}'],['MSP','SMTA Holdings Inc doing business as TeamLogic IT of Scottsdale\n8687 E Via De Ventura Suite 301 Scottsdale AZ 85258'],['MSP authorized personnel',p.prepared_by],['MSA date',p.msa_date or 'To be confirmed'],['SOW effective date',p.effective_date or 'To be confirmed'],['Term',f'Initial: {p.term_months} months; renewal: {p.renewal_months} months; nonrenewal notice: {p.notice_days} days'],['Governing state / venue','Arizona / Maricopa'],['Business hours','Mon-Fri 8:00 AM-5:00 PM MST, excluding holidays'],['Policies','NA']],[160,350])
    story.append(para('This SOW is entered into between the MSP and Customer. The Parties acknowledge and agree that they have read and understand Master Services Agreement (MSA) General Terms and Conditions. The Parties acknowledge and agree that they have read and understand this SOW and agree to be bound to its terms.'))
    story.append(PageBreak());heading('Schedule A  /  Additional terms')
    for text in json.loads((TEMPLATES/'terms.json').read_text(encoding='utf-8')):
        # The cover's explicit notice period drives the matching contractual reference.
        story.append(para(text,'HeadTL' if text.strip() in ['Recitals','Term and Termination.','Fees and Payment Schedule.','Scope; Services; Minimum Requirements.','Coverage.','Additional Maintenance Services.'] else 'BodyTL'))
    story.append(PageBreak());heading('Schedule B  /  Services')
    story.append(para('Only services marked Included below are included within this engagement.'))
    table([['Service','Frequency','Coverage']]+[[s.description,s.frequency,s.status] for s in p.services],[300,100,110])
    heading('Exclusions and scope notes');story.append(para(p.exclusions or 'No additional exclusions specified.'))
    heading('Environment and discovery')
    for label,value in [('Cloud',p.cloud),('Identity / domain',p.domain),('Backups',p.backups),('Security',p.security),('Applications',p.applications),('Needs',p.needs),('Recommendations',p.recommendations)]:
        if value:story.append(para(f'{label}: {value}'))
    if p.assets:
        heading('Equipment inventory')
        table([['Type','Description / location','Qty']]+[[a.kind,a.description+('\n'+a.location if a.location else ''),a.quantity] for a in p.assets],[110,350,50])
    story.append(PageBreak());heading('Schedule C  /  Service rates')
    table([['Service','Qty','Unit rate','Amount']]+[[x['description']+(' (monthly)' if x['cadence']=='monthly' else ' (one-time)'),x['quantity'],money(x['rate']),money(x['total'])] for x in q['lines']],[265,40,95,110])
    table([['Summary','Amount'],['Recurring subtotal',money(q['subtotal'])],['Monthly discount','-'+money(q['discount'])],[f'Monthly tax ({p.tax_percent}%)',money(q['tax'])],['Monthly total',money(q['monthly'])],['One-time total including tax',money(q['one_time'])],['First month plus one-time charges',money(q['first_month'])],[f'Initial {p.term_months}-month total including one-time charges',money(q['term_total'])]],[340,170])
    story.append(para(f'Tax is calculated at {p.tax_percent}% on items designated taxable. The monthly discount is allocated proportionally across recurring items. Term totals assume unchanged quantities and rates.'))
    table([['Additional service','Rate'],['Onsite labor / special projects',money(p.hourly_rate)+'/hour'],['After-hours / weekend / holiday support',money(p.after_hours_rate)+'/hour']],[340,170])
    story.append(para('We reserve the right to adjust the monthly ongoing fee for managed services when additional equipment is added, or new users/supported employees are brought on board. The adjusted fee will be reflected in the monthly invoice.'))
    heading('Covered users and equipment')
    story.append(para(f'{p.users} users; {p.workstations} workstations; {p.servers} servers. Network equipment is listed in the inventory and covered only as specified in Schedule B.'))
    story.append(PageBreak());heading('Acceptance')
    story.append(para('The parties agree to this SOW Cover Page and Schedules A, B and C, subject to the Master Services Agreement.'))
    table([['TeamLogic IT of Scottsdale',p.client],['Signature: _________________________\n\nName: ____________________________\n\nTitle: _____________________________\n\nDate: ____________________________','Signature: _________________________\n\nName: ____________________________\n\nTitle: _____________________________\n\nDate: ____________________________']],[255,255])
    story.append(PageBreak());heading('Recurring Payment Authorization Form')
    payment=json.loads((TEMPLATES/'payment.json').read_text(encoding='utf-8'))
    for text in payment[1:5]:story.append(para(text))
    story.append(para('Company name: ______________________________________________'))
    story.append(para('Authorizes TeamLogic IT to charge the account indicated below on the 7st day of each month for payment of the firm\'s Managed Services.'))
    story.append(para('Billing address: _________________________________________________\nCity, State, ZIP: _________________________________________________\nPhone: ___________________  Email: ______________________________'))
    table([['Checking / Savings Account','Credit Card (3% fee)'],['Account type: Checking ___ Savings ___\n\nName on account: __________________\n\nBank name: _______________________\n\nAccount number: __________________\n\nBank routing number: _______________\n\nBank city / state: ___________________','Visa ___ MasterCard ___ Amex ___ Discover ___\n\nCardholder name: __________________\n\nAccount number: __________________\n\nExpiration date: ___________________']],[255,255])
    story.append(para('Signature: __________________________________  Date: ______________'))
    for text in payment:
        if text.startswith('I understand'):story.append(para(text))
    def footer(canvas,doc):
        canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#627083'))
        canvas.drawString(51,28,'TeamLogic IT Scottsdale | Managed IT Services')
        canvas.drawRightString(561,28,str(doc.page))
    SimpleDocTemplate(stream,pagesize=(612,792),leftMargin=51,rightMargin=51,topMargin=45,bottomMargin=49,title=f'Managed IT Services - {p.client}',author='TeamLogic IT Scottsdale').build(story,onFirstPage=footer,onLaterPages=footer)
    return stream.getvalue()
