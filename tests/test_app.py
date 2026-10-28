import hashlib
import io
import json
import os
import tempfile
import zipfile
from decimal import Decimal
os.environ['DATA_DIR']=tempfile.mkdtemp(prefix='tlit-test-')
from fastapi.testclient import TestClient
from pypdf import PdfReader
from pptx import Presentation
from app.main import app,connect
from app.models import Proposal,quote
from app.generate import TEMPLATES,pdf_bytes,pptx_bytes

def example():return Proposal(**json.loads((TEMPLATES/'example.json').read_text()))

def test_example_totals():
    q=quote(example())
    assert q['monthly']==Decimal('410.00')
    assert q['one_time']==Decimal('500.00')
    assert q['first_month']==Decimal('910.00')
    assert q['term_total']==Decimal('15260.00')

def test_billing_modes_and_tax_allocation():
    p=example();p.user_rate=Decimal('100');p.billing_mode='users';p.extras=[];p.user_taxable=True
    p.tax_percent=Decimal('8');p.discount=Decimal('20')
    assert quote(p)['monthly']==Decimal('194.40')
    p.billing_mode='combined';p.workstation_taxable=False;p.server_taxable=False
    q=quote(p)
    assert q['subtotal']==Decimal('520.00')
    assert q['tax']==Decimal('15.38')

def test_invalid_discount_and_fractional_counts():
    import pytest
    p=example();p.discount=Decimal('999')
    with pytest.raises(ValueError):quote(p)
    with pytest.raises(ValueError):Proposal(**{**example().model_dump(),'users':1.2})
    with pytest.raises(ValueError):Proposal(**{**example().model_dump(),'user_rate':'NaN'})

def test_auth_save_reload_and_download():
    salt=b'0123456789abcdef';password='test-only-password'
    with connect() as db:
        db.execute('INSERT OR REPLACE INTO users VALUES(?,?,?)',('tester',salt.hex(),hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1).hex()))
    with TestClient(app) as c:
        assert c.get('/api/proposals').status_code==401
        assert c.post('/api/login',json={'username':'tester','password':password}).status_code==403
        c.headers['X-TLIT-Request']='1'
        assert c.post('/api/login',json={'username':'tester','password':password}).status_code==200
        data=example().model_dump(mode='json')
        result=c.post('/api/proposals',json=data);assert result.status_code==200
        assert c.get('/api/proposals/'+result.json()['id']).json()==data
        data['client']='Different Client & Co'
        assert c.put('/api/proposals/'+result.json()['id'],json=data,headers={'If-Match':'1'}).status_code==200
        response=c.post('/api/generate',json=data);assert response.status_code==200
        z=zipfile.ZipFile(io.BytesIO(response.content))
        pdf=PdfReader(io.BytesIO(z.read('Managed-IT-Services.pdf')))
        text='\n'.join(p.extract_text() for p in pdf.pages)
        assert 'Different Client & Co' in text and '$410.00' in text
        assert 'ProjectCenter' not in text
        assert 'Bank routing number' in text
        assert 'ninety (90) days' in ' '.join(text.split())
        deck=Presentation(io.BytesIO(z.read('Proposal.pptx')))
        all_text=' '.join(s.text for slide in deck.slides for s in slide.shapes if s.has_text_frame)
        assert 'ProjectCenter' not in all_text
        assert '{{' not in all_text
        assert '$410.00' in all_text
        assert c.post('/api/logout').status_code==200
        assert c.get('/api/proposals').status_code==401

def test_long_content_and_pagination():
    p=example();p.client='A long client company name that should wrap cleanly in the proposal';p.needs='Long discovery note. '*90
    from app.models import Line
    p.extras=[Line(description='Additional support service '+str(i),quantity=2,rate='10') for i in range(30)]
    q=quote(p)
    assert len(Presentation(io.BytesIO(pptx_bytes(p,q))).slides)>20
    assert len(PdfReader(io.BytesIO(pdf_bytes(p,q))).pages)>5
