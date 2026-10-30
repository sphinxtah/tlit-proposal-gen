from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field

Money = Annotated[Decimal, Field(ge=0, le=1000000, max_digits=12, decimal_places=2)]
Count = Annotated[int, Field(ge=0, le=100000)]
Text = Annotated[str, Field(max_length=2000)]
Short = Annotated[str, Field(max_length=40)]

class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class Asset(Model):
    kind: Literal['Workstation', 'Physical server', 'Cloud server', 'Firewall', 'Switch', 'Access point', 'Other']
    description: Annotated[str, Field(min_length=1, max_length=200)]
    quantity: Count = 1
    location: Annotated[str, Field(max_length=200)] = ''

class Line(Model):
    description: Annotated[str, Field(min_length=1, max_length=150)]
    quantity: Count = 1
    rate: Money = Decimal('0')
    cadence: Literal['monthly', 'one-time'] = 'monthly'
    taxable: bool = False
    # Which card on the pricing slide shows this charge, and how its quantity is labelled ("2 users × $25.00").
    category: Literal['security', 'backup', 'other'] = 'other'
    unit: Short = 'users'

class Service(Model):
    description: Annotated[str, Field(min_length=1, max_length=350)]
    frequency: Annotated[str, Field(max_length=80)] = 'Ongoing'
    status: Literal['Included', 'Excluded', 'Not applicable'] = 'Included'

class Proposal(Model):
    client: Annotated[str, Field(min_length=1, max_length=100)]
    contact: Annotated[str, Field(max_length=120)] = ''
    email: Annotated[str, Field(max_length=160)] = ''
    phone: Annotated[str, Field(max_length=80)] = ''
    address: Annotated[str, Field(max_length=500)] = ''
    proposal_date: date
    effective_date: date | None = None
    msa_date: date | None = None
    prepared_by: Annotated[str, Field(max_length=120)] = ''
    users: Count = 0
    workstations: Count = 0
    servers: Count = 0
    networks: Count = 1
    mobile_devices: Count = 0
    user_rate: Money = Decimal('0')
    workstation_rate: Money = Decimal('0')
    server_rate: Money = Decimal('0')
    billing_mode: Literal['combined','users','devices'] = 'combined'
    onboarding: Money = Decimal('500')
    user_taxable: bool = False
    workstation_taxable: bool = False
    server_taxable: bool = False
    onboarding_taxable: bool = False
    tax_reviewed: bool = False
    tax_notes: Text = ''
    discount: Money = Decimal('0')
    tax_percent: Annotated[Decimal, Field(ge=0, le=100, decimal_places=3)] = Decimal('0')
    hourly_rate: Money = Decimal('135')
    after_hours_rate: Money = Decimal('202')
    term_months: Annotated[int, Field(ge=1, le=120)] = 36
    renewal_months: Annotated[int, Field(ge=1, le=120)] = 12
    notice_days: Literal[90] = 90
    current_state: Text = ''
    backup_label: Short = 'Cloud'
    cloud: Text = ''
    domain: Text = ''
    backups: Text = ''
    security: Text = ''
    applications: Text = ''
    needs: Text = ''
    recommendations: Text = ''
    exclusions: Text = 'Printer management is provided by another MSP and is excluded.'
    assets: Annotated[list[Asset], Field(max_length=100)] = []
    extras: Annotated[list[Line], Field(max_length=50)] = []
    services: Annotated[list[Service], Field(max_length=100)] = []
    unresolved: Text = ''

def cents(value):
    return value.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)

def quote(p: Proposal):
    lines = []
    for name, qty, rate, taxable, enabled, unit in [('Managed IT services / user', p.users, p.user_rate,p.user_taxable,p.billing_mode!='devices','Users'),
                             ('Workstation monitoring & support', p.workstations, p.workstation_rate,p.workstation_taxable,p.billing_mode!='users','Devices'),
                             ('Server monitoring & support', p.servers, p.server_rate,p.server_taxable,p.billing_mode!='users','Devices')]:
        if qty and enabled:
            lines.append(dict(description=name, quantity=qty, rate=rate, taxable=taxable, cadence='monthly', category='core', unit=unit, total=cents(qty*rate)))
    for x in p.extras:
        lines.append(dict(**x.model_dump(), total=cents(x.quantity*x.rate)))
    if p.onboarding:
        lines.append(dict(description='Onboarding / setup', quantity=1, rate=p.onboarding, taxable=p.onboarding_taxable, cadence='one-time', category='onboarding', unit='', total=p.onboarding))
    subtotal = sum((x['total'] for x in lines if x['cadence']=='monthly'), Decimal('0'))
    if p.discount > subtotal:
        raise ValueError('Monthly discount cannot exceed the recurring subtotal.')
    net = subtotal-p.discount
    taxable_subtotal=sum((x['total'] for x in lines if x['cadence']=='monthly' and x['taxable']),Decimal('0'))
    taxable_net=cents(taxable_subtotal*(net/subtotal)) if subtotal else Decimal('0')
    tax = cents(taxable_net*p.tax_percent/100)
    setup = sum((x['total'] for x in lines if x['cadence']=='one-time'), Decimal('0'))
    taxable_setup=sum((x['total'] for x in lines if x['cadence']=='one-time' and x['taxable']),Decimal('0'))
    setup_tax = cents(taxable_setup*p.tax_percent/100)
    warnings = []
    if not p.tax_reviewed:warnings.append('Tax classification and sourcing have not been reviewed. Tax settings are provisional.')
    if p.unresolved: warnings.append(p.unresolved)
    if not p.effective_date: warnings.append('SOW effective date has not been entered.')
    if not p.msa_date: warnings.append('MSA date has not been entered.')
    if not p.services: warnings.append('Service scope has not been selected.')
    for qty, rate, label in [(p.users,p.user_rate,'Users'),(p.workstations,p.workstation_rate,'Workstations'),(p.servers,p.server_rate,'Servers')]:
        enabled=(label=='Users' and p.billing_mode!='devices') or (label!='Users' and p.billing_mode!='users')
        if enabled and qty and not rate: warnings.append(f'{label} have a $0 unit rate; confirm this is intentional.')
    for kinds, count, label in [(['Workstation'],p.workstations,'Workstation'),(['Physical server','Cloud server'],p.servers,'Server')]:
        actual = sum(a.quantity for a in p.assets if a.kind in kinds)
        if actual != count: warnings.append(f'{label} inventory ({actual}) differs from billed quantity ({count}).')
    # The proposal deck reproduces the reference pricing slide, which only has cards for managed services,
    # cybersecurity, backup and onboarding. Flag anything the client would not see itemised there.
    hidden=[x['description'] for x in lines if x['category'] not in ('core','onboarding') and (x['category']=='other' or x['cadence']!='monthly')]
    if hidden: warnings.append('Not itemised on the pricing slide (included in its totals only): '+', '.join(hidden)+'. Assign monthly charges to the Cybersecurity or Backup card where they belong.')
    if p.discount: warnings.append('The pricing slide cards show undiscounted amounts; the headline monthly figure and SOW Monthly Fee include the discount.')
    if tax or setup_tax: warnings.append('The pricing slide and SOW show fees before tax. Applicable tax is invoiced separately.')
    return dict(lines=lines, subtotal=cents(subtotal), discount=p.discount, net=cents(net), tax=tax,
                monthly=cents(net+tax), one_time=cents(setup+setup_tax), one_time_tax=setup_tax,
                first_month=cents(net+tax+setup+setup_tax), term_total=cents((net+tax)*p.term_months+setup+setup_tax), warnings=warnings)
