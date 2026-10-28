# Arizona / Scottsdale tax research

Research date: October 27, 2026. Implementation guidance, not a final classification of TeamLogic IT's contracts. Confirm the precise contracts, sourcing and reporting with the firm's tax adviser or ADOR before using tax amounts in client agreements.

## Findings

Arizona's transaction privilege tax is imposed on business activities rather than being a universal tax on all services. [ADOR overview](https://azdor.gov/business/transaction-privilege-tax).

[A.R.S. 42-5061](https://www.azleg.gov/ars/42/05061.htm) distinguishes retail tangible personal property from professional/personal service businesses and specified services. Pure separately stated IT consulting/support labor should not simply inherit the treatment of licensed software. The exact classification and bundling matter.

Scottsdale publishes an **8.00% combined rate for most taxable activities**: 5.6% state + 0.7% county + 1.7% city. This is not an across-the-board tax on managed IT services. [City tax resources](https://www.scottsdaleaz.gov/taxes/resources).

ADOR's [software letter ruling 17-001](https://azdor.gov/sites/default/files/2023-03/RULINGS_TPT_2018_17-001.pdf) discusses prewritten software as tangible personal property and rental/licensing treatment, including the treatment of related charges under the rental classification. Letter rulings are fact-specific; this is evidence that software subscriptions cannot safely be assumed tax-free, not a binding ruling for this business.

The [Model City Tax Code index](https://azdor.gov/business/transaction-privilege-tax/model-city-tax-code/index-articles-and-regulations) includes computer software and rental/licensing provisions. [Scottsdale's ADOR profile](https://azdor.gov/model-city-tax-code/city-profile/scottsdale) identifies its local code and rates.

## Practical classification worksheet

| Offering | Working treatment to review | What must be established |
| --- | --- | --- |
| Separately stated managed support / consulting labor | Candidate for nontaxable service treatment | Actual deliverables, no bundled license right, separate records |
| Workstation/server monitoring | Review required | Human service versus licensed monitoring/security software bundle |
| $500 onboarding | Review required | Standalone labor versus charge connected to a taxable rental/license |
| Sophos Endpoint / email filtering | Review as possible taxable software license | Reseller/license structure and sourcing |
| Sophos MDR | Review service/software allocation | Managed response service versus license bundle |
| Datto Endpoint / AppRiver cloud-to-cloud backup | Review required | Software rights, storage/service components, contract structure |
| Hardware | Generally retail tangible personal property | Applicable exemptions/resale and transaction sourcing |

These are review categories, not automatic tax rules. No blanket vendor tax decision has been established.

## Sourcing and application behavior

The provider is in Scottsdale and Example Company is in Phoenix. Do not choose the tax rate solely from either mailing address; applicable business classification and sourcing rules must be established. The app starts with a provisional 0% rate and a prominent unreviewed-tax warning. Zero is a placeholder, not a determination of exemption.

Each charge has a Taxable checkbox. The app applies the entered rate to taxable amounts only. Monthly discounts reduce taxable and nontaxable recurring subtotals proportionally. Taxable base and tax are rounded half-up to cents. One-time tax is calculated separately. Both outputs use those exact totals. A single proposal currently supports a single reviewed rate; split-jurisdiction transactions need a later extension.

Before client use, document the jurisdiction/classification rationale in Tax notes and mark the review complete. The app deliberately permits draft exports while review questions remain, and includes warnings in the generation manifest.
