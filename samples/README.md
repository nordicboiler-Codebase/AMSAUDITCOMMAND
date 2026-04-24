# Sample CSVs — column reference

Drop one of these into the **Datasets → Import dataset** form in the UI to see how the detectors behave. Each sample has **planted fraud signals** so packs immediately produce findings.

## Use your own data

Your ERP export is welcome — the detectors only care about **column names**. Rename columns to match the references below (or override the `field` parameter on each template). **Any extra columns are ignored.**

---

## Accounts Payable — `accounts_payable_sample.csv`

| Column | Type | Used by |
|---|---|---|
| `record_id` | string | universal record key |
| `vendor_id` | string | AP01, AP06, AP22, AP23, AP24 |
| `vendor_name` | string | AP06 fuzzy dup, AP17 vendor-employee match |
| `vendor_iban` | string | AP18 bank account match |
| `vendor_address` | string | AP19 address match, AP21 PO Box |
| `vendor_phone` | string | AP20 phone match |
| `invoice_no` | string | AP01, AP02, AP04, AP07 |
| `amount` | number | AP03, AP11–AP16 (rounding, thresholds) |
| `payment_date` | date | AP08, AP09 (weekend / holiday) |
| `payment_datetime` | datetime | AP10 after-hours |
| `description` | string | AP25 keyword scan |
| `gl_account` | string | AP23 rare vendor-GL pair |

**Planted signals**: duplicate payment on R0004, amount 9,500 near 10k threshold on R0002, 23:45 posting on R0005 with "test reversal" keyword.

---

## General Ledger — `general_ledger_sample.csv`

| Column | Type | Used by |
|---|---|---|
| `record_id` | string | universal record key |
| `journal_id` | string | GL01 duplicate JE |
| `posting_date` | date | GL02, GL05, GL06 |
| `posting_datetime` | datetime | GL04 after-hours |
| `entry_date` | date | GL07 backdated |
| `entry_type` | string | GL02, GL16 filter (`manual`/`auto`) |
| `entered_by` | string | GL08 override, GL16 user summary |
| `debit_account`, `credit_account` | string | GL09 rare account pair |
| `debit_amount`, `credit_amount` | number | GL10, GL11, GL12 |
| `amount` | number | GL13, GL17, GL18 |
| `description` | string | GL14 null, GL15 keyword |
| `period_close_date` | date | GL06 after-close |
| `reverses_journal_id` | string | GL19 orphan reversal |

**Planted signals**: late-night JE (R0003), backdated posting (R0004), "test plug" keyword (R0003), unbalanced debit/credit (R0006).

---

## Accounts Receivable — `accounts_receivable_sample.csv`

| Column | Type | Used by |
|---|---|---|
| `record_id` | string | universal record key |
| `customer_id` | string | AR01, AR09, AR12, AR14 |
| `customer_name` | string | AR11 fuzzy dup |
| `invoice_no` | string | AR01, AR02 |
| `invoice_amount` | number | AR07, AR08 |
| `invoice_date` | date | AR15 date anomaly |
| `due_date` | date | AR03, AR04 aging |
| `payment_date` | date | AR15 date anomaly |
| `balance` | number | AR05 credit limit, AR06 negative |
| `credit_limit` | number | AR05 comparison |
| `writeoff_amount` | number | AR13 large write-offs |
| `type` | string | AR14 filter (`refund`/`writeoff`/`sale`) |
| `ref_invoice_no` | string | AR02 orphan credit note |
| `shipment_id` | string | AR10 unbilled revenue |

**Planted signals**: credit limit breached (R0004), negative balance refund (R0005), aged invoice (R0006), large write-off (R0007), invoice_date after payment_date (R0003).

---

## Payroll — `payroll_sample.csv`

| Column | Type | Used by |
|---|---|---|
| `record_id` | string | universal record key |
| `employee_id` | string | PR01, PR02, PR03 |
| `full_name` | string | PR06 fuzzy duplicate names |
| `pay_period` | date | PR01 period-duplicate |
| `gross_pay` | number | PR15 Benford |
| `bonus_amount`, `bonus_ratio`, `base_salary`, `grade` | | PR08, PR10 |
| `bank_account` | string | PR04 shared bank |
| `emirates_id` | string | PR12 duplicate TRN |
| `address` | string | PR05 shared address |
| `hire_date` | date | PR13 mass hires |
| `posting_date` | date | PR09 weekend |
| `overtime_hours` | number | PR07 |
| `pay_rate_change_pct` | number | PR11 |
| `status_change` | string | PR14 reactivation |

**Planted signals**: shared bank account (E01/E05 both on BA-0001), 50% pay increase (E04), reactivated employee (E04), 40h overtime (E04), bonus ratio 0.83 (E03).

---

## Other subledgers

For **Inventory, Bank, Procurement, T&E, Sales, Fixed Assets**: the detector params tell you the field names. From the UI, open **Templates → filter by subledger → click a code** to see its `default_params` — those keys are your column names. Rename your export headers to match, or override params when running.
