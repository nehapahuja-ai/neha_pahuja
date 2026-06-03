# FNB Outlet Automation — TC_FNB_001

End-to-end Robot Framework test that creates a Food outlet on the
Aeria property management staging dashboard.

---

## Prerequisites

- Python 3.9+
- Google Chrome + matching ChromeDriver (managed automatically by webdriver-manager)

## Install dependencies

```bash
pip install -r requirements.txt
```

Install ChromeDriver automatically:

```bash
python -m webdriver_manager.chrome
```

Or let the test manage it at runtime via SeleniumLibrary's built-in support.

---

## Run the test

From the repo root:

```bash
robot -d fnb/results fnb/tests/TC_FNB_001_Add_Outlet.robot
```

Results are written to `fnb/results/` (log.html, report.html, output.xml).

To run headless (CI):

```bash
robot -d fnb/results \
  --variable BROWSER:headless-chrome \
  fnb/tests/TC_FNB_001_Add_Outlet.robot
```

---

## Configuration

All test data lives in `fnb/testdata/outlet_data.yaml`.

| Key | Default | Notes |
|---|---|---|
| `LOGIN_URL` | Aeria staging OTP URL | Full URL including callbackUrl |
| `LOGIN_EMAIL` | `ak@aeria.world.patil@aeria.world` | Account that triggers the OTP |
| `SMTP4DEV_URL` | `http://13.202.22.2` | Change if smtp4dev moves |
| `SMTP4DEV_EMAIL` | `ak@aeria.world.patil+mainsite@…` | The To: address OTP is delivered to |
| `OUTLET_NAME_PREFIX` | `Test Auto Outlet` | A timestamp is appended at runtime |
| `OUTLET_LOCATION_TOWER` | `Tower 1` | First level of location tree |
| `OUTLET_LOCATION_FLOOR` | `Floor 1` | Second level of location tree |
| `SITE_ADMIN_NAME` | `ak@aeria.world Patil- Main Site` | Exact label in Switch Accounts |

Override any value at runtime without editing the YAML:

```bash
robot -d fnb/results \
  --variable LOGIN_EMAIL:other@aeria.world \
  fnb/tests/TC_FNB_001_Add_Outlet.robot
```

---

## If the smtp4dev URL changes

1. Update `SMTP4DEV_URL` in `fnb/testdata/outlet_data.yaml`.
2. If the API changes (e.g. smtp4dev v2 → v3), update `fetch_otp_from_smtp4dev`
   in `fnb/pages/OutletPage.py`.  The relevant section:

   ```python
   resp = requests.get(f"{base}/api/messages", timeout=10)
   ```

   smtp4dev v3 returns `{ "results": [...], "totalCount": N }`.
   smtp4dev v2 returns a plain list `[...]`.
   Both are handled already.

---

## Project layout

```
fnb/
├── tests/
│   └── TC_FNB_001_Add_Outlet.robot   # Test cases
├── keywords/
│   └── OutletKeywords.resource        # Browser setup + retry wrappers
├── pages/
│   └── OutletPage.py                  # All Selenium interactions (Page Object)
├── locators/
│   └── OutletLocators.py              # XPath/CSS constants — update when UI changes
├── testdata/
│   └── outlet_data.yaml               # All test data (no hardcoded values elsewhere)
├── results/                           # robot -d target
├── requirements.txt
└── README.md
```
