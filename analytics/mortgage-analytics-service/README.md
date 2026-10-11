# Mortgage Analytics Service

Python 3.11 service providing portfolio analytics, data normalization, S3 document storage integration, and REST endpoints.

## Portfolio Analytics & Formulas

The analytics engine (`src/analytics/portfolio.py`) processes normalized DataFrames to compute the following core metrics[cite: 4]:

* **Total Mortgages**: Count of all loan records (`len(df_mortgages)`)[cite: 4].
* **Active / Delinquent Loans**: Segmented counts based on the `status` attribute (`ACTIVE` or `DELINQUENT`)[cite: 4].
* **Outstanding Balance Total**: Sum of the `outstanding_balance` field across all valid mortgage records[cite: 4].
* **Delinquency Rate**: The proportion of delinquent mortgages relative to the total portfolio count (`delinquent_mortgages / total_mortgages`)[cite: 4].
* **Borrower Risk Summary**: Aggregated metrics grouped by `borrower_external_id`, computing total active mortgages, sum of outstanding balances, and total delinquent loans[cite: 4].
* **Payment Trends**: Monthly payment aggregations using `pd.Grouper` on `paid_date`, summing the total posted amount and computing the on-time ratio (`paid_date <= due_date`)[cite: 4].


## Local Setup
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn src.api.main:app --reload --port 8000