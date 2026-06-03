# =============================================================================
# OutletLocators.py  —  Single source of truth for all Selenium locators.
# Zero logic, zero imports.  All business logic lives in OutletPage.py.
#
# Strategy (highest → lowest preference):
#   1. Stable attribute: data-testid, id, name, type, placeholder
#   2. ARIA: role, aria-label
#   3. Visible text via XPath normalize-space()
#   4. Structural XPath (last resort)
#
# Where the real value is unknown, multiple candidate patterns are joined with
# XPath | so the first match wins.  Update the winning pattern once confirmed.
# =============================================================================


# ── Step 1: Login page ────────────────────────────────────────────────────────

# Email field on the "enter-email" step
LOGIN_EMAIL_INPUT = (
    "//input[@type='email' or @name='email' or contains(@placeholder,'email') "
    "or contains(@placeholder,'Email')][1]"
)

# "Continue" button that triggers OTP dispatch
LOGIN_CONTINUE_BUTTON = (
    "//button[normalize-space(.)='Continue' or normalize-space(.)='Send OTP' "
    "or normalize-space(.)='Get OTP']"
)

# Six individual OTP digit boxes (maxlength=1 pattern)
OTP_INPUTS_MULTI = "//input[@maxlength='1']"

# Single consolidated OTP field (fallback)
OTP_INPUT_SINGLE = (
    "//input[@maxlength='6' or @name='otp' or @id='otp' "
    "or contains(@placeholder,'OTP') or contains(@placeholder,'otp')]"
)

# Element present only after a successful OTP login lands on VMS / dashboard
DASHBOARD_LOADED_MARKER = (
    "//nav[contains(@class,'sidebar') or contains(@class,'nav')] "
    "| //*[@data-testid='sidebar'] "
    "| //a[contains(@href,'outlets') or contains(@href,'vms')]"
)


# ── Step 2: Sidebar navigation ────────────────────────────────────────────────

# "Outlets" item in the left navigation sidebar
SIDEBAR_OUTLETS_LINK = (
    "//a[contains(@href,'outlets') and not(contains(@href,'add-outlet'))]"
    "[normalize-space(.)='Outlets' or .//*[normalize-space(.)='Outlets']] "
    "| //span[normalize-space(.)='Outlets']/ancestor::a[1] "
    "| //li[normalize-space(.)='Outlets']"
)

# Heading visible after the Outlets list page finishes loading
OUTLET_LIST_PAGE_HEADING = (
    "//*[self::h1 or self::h2 or self::h3][contains(normalize-space(.),'Outlet')]"
)


# ── Step 2b: Add Outlet entry point ───────────────────────────────────────────

# "+ Add Outlet" button on the listing page (top-right)
ADD_OUTLET_BUTTON = (
    "//button[contains(normalize-space(.),'Add Outlet') "
    "or contains(normalize-space(.),'+') and contains(normalize-space(.),'Outlet')]"
)

# Food type card / button on the outlet-type picker modal
OUTLET_TYPE_FOOD = (
    "//div[@role='button' or @role='option'][normalize-space(.)='Food'] "
    "| //button[normalize-space(.)='Food'] "
    "| //span[normalize-space(.)='Food']/ancestor::*[@role='button' or @role='option'][1]"
)


# ── Step 3: Overview tab ──────────────────────────────────────────────────────

OUTLET_NAME_INPUT = (
    "//input[@name='name' or @id='name' or @placeholder='Outlet Name' "
    "or contains(@placeholder,'name') or contains(@placeholder,'Name')][1]"
)

# Location field — opens a searchable tree picker (Tower > Floor)
LOCATION_DROPDOWN_TRIGGER = (
    "//input[contains(@placeholder,'ocation') or @name='location' or @id='location'] "
    "| //*[@data-testid='location-select'] "
    "| //label[contains(.,'Location')]/following-sibling::*//*[contains(@class,'select') "
    "  or contains(@class,'picker')]"
)

FSSAI_INPUT = (
    "//input[contains(@placeholder,'FSSAI') or contains(@placeholder,'fssai') "
    "or @name='fssaiLicenseNumber' or @name='fssai' "
    "or contains(@placeholder,'License') or contains(@placeholder,'license')]"
)

# "All Day" checkbox/toggle on the Operational Time section
ALL_DAY_CHECKBOX = (
    "//input[@id='allDay' or @name='allDay' or @value='allDay']["
    "  @type='checkbox' or @type='radio'] "
    "| //label[contains(normalize-space(.),'All Day')]//input"
)

ALL_DAY_TOGGLE_DIV = (
    "//label[contains(normalize-space(.),'All Day')] "
    "| //div[contains(@class,'toggle') and "
    "  ancestor::*[contains(normalize-space(.),'All Day')]] "
    "| //button[@role='switch' and "
    "  ancestor::*[contains(normalize-space(.),'All Day')]]"
)

PHONE_INPUT = (
    "//input[@type='tel' or @name='phone' or @name='phoneNumber' "
    "or contains(@placeholder,'Phone') or contains(@placeholder,'phone')]"
)

# Email input inside the Overview form (distinct from the login email field)
OUTLET_EMAIL_INPUT = (
    "//input[@name='email' or @name='outletEmail' "
    "or contains(@placeholder,'Email') or contains(@placeholder,'email')]"
    "[not(@type='hidden')][last()]"
)

# "Next →" button at the bottom of the Overview step
NEXT_BUTTON = (
    "//button[normalize-space(.)='Next' or starts-with(normalize-space(.),'Next')]"
)


# ── Step 4: Configuration tab ─────────────────────────────────────────────────

# Order Fulfillment Mode checkboxes
DELIVERY_TO_DESK_CB = (
    "//label[contains(normalize-space(.),'Delivery to Desk') "
    "or contains(normalize-space(.),'Delivery To Desk')]//input[@type='checkbox'] "
    "| //input[@name='deliveryToDesk' or @id='deliveryToDesk']"
)

TAKEAWAY_CB = (
    "//label[contains(normalize-space(.),'Takeaway') "
    "or contains(normalize-space(.),'Take Away')]//input[@type='checkbox'] "
    "| //input[@name='takeaway' or @id='takeaway']"
)

DINE_IN_CB = (
    "//label[contains(normalize-space(.),'Dine-In') "
    "or contains(normalize-space(.),'Dine In')]//input[@type='checkbox'] "
    "| //input[@name='dineIn' or @id='dineIn']"
)

# Order Channel toggle buttons (App / Website / Both)
ORDER_CHANNEL_APP_BTN = (
    "//button[normalize-space(.)='App'] "
    "| //label[normalize-space(.)='App']//input[@type='radio' or @type='checkbox']"
)

# "Self" option under "Deliveries handled by"
DELIVERIES_SELF_BTN = (
    "//button[normalize-space(.)='Self'] "
    "| //label[normalize-space(.)='Self']//input "
    "| //div[@role='radio' and normalize-space(.)='Self']"
)

# "Inclusive" / "Exclusive" GST toggle
GST_INCLUSIVE_BTN = (
    "//button[normalize-space(.)='Inclusive'] "
    "| //label[normalize-space(.)='Inclusive']//input "
    "| //div[@role='radio' and normalize-space(.)='Inclusive']"
)

# Default GST Rate dropdown/select
GST_RATE_SELECT = (
    "//select[@name='defaultGstRate' or @id='defaultGstRate'] "
    "| //input[contains(@placeholder,'GST') or @name='gstRate'] "
    "| //*[@data-testid='gst-rate-select']"
)

# POS System dropdown
POS_SYSTEM_SELECT = (
    "//select[contains(@name,'pos') or contains(@id,'pos') "
    "or contains(@name,'Pos') or contains(@id,'Pos')] "
    "| //input[contains(@placeholder,'POS') or contains(@name,'pos')] "
    "| //*[@data-testid='pos-select']"
)

# Menu Type dropdown (Veg Only / Non-Veg Only / Veg & Non-Veg)
MENU_TYPE_SELECT = (
    "//select[@name='menuType' or @id='menuType'] "
    "| //*[@data-testid='menu-type-select'] "
    "| //label[contains(.,'Menu Type')]/following-sibling::*//input[1]"
)

# Tag input for cuisines (type to search, click suggestion)
CUISINES_INPUT = (
    "//input[contains(@placeholder,'Cuisine') or contains(@placeholder,'cuisine') "
    "or @name='cuisines' or @id='cuisines']"
)

COST_FOR_TWO_INPUT = (
    "//input[@name='costForTwo' or @id='costForTwo' "
    "or contains(@placeholder,'Cost') or contains(@placeholder,'cost')]"
)

PAYMENT_COLLECTOR_INPUT = (
    "//input[contains(@placeholder,'Payment Collector') "
    "or contains(@placeholder,'payment') "
    "or @name='paymentCollector' or @id='paymentCollector']"
)

# "Done" button at the end of wizard step 2
DONE_BUTTON = (
    "//button[normalize-space(.)='Done' or normalize-space(.)='Submit' "
    "or normalize-space(.)='Save']"
)


# ── Step 5: Outlet list (Tenant view) ─────────────────────────────────────────

OUTLET_SEARCH_INPUT = (
    "//input[@type='search' or contains(@placeholder,'Search') "
    "or contains(@placeholder,'search')]"
)

# Any element inside an outlet row that shows the outlet name
OUTLET_ROW_BY_NAME = (
    "//*[contains(@class,'outlet') or @data-testid='outlet-item' "
    "or @data-testid='outlet-row']"
    "[.//*[contains(normalize-space(.),'{name}')]]"
)


# ── Step 6: Switch accounts ───────────────────────────────────────────────────

USER_AVATAR = (
    "//button[contains(@class,'avatar') or @data-testid='user-avatar'] "
    "| //img[contains(@class,'avatar') or @alt='avatar' or @data-testid='avatar'] "
    "| //div[contains(@class,'user-menu') or @data-testid='user-menu'] "
    "| //button[contains(@class,'profile') or contains(@class,'user')] "
    "| //*[@data-testid='user-avatar' or @data-testid='profile-button'] "
    "| //header//*[contains(@class,'avatar') or contains(@class,'profile') or contains(@class,'user')][1] "
    "| //nav//*[contains(@class,'avatar') or contains(@class,'profile')][1]"
)

SWITCH_ACCOUNTS_MENU_ITEM = (
    "//*[normalize-space(.)='Switch Accounts' or normalize-space(.)='Switch Account']"
    "[self::li or self::a or self::button or self::div]"
)

SWITCH_ACCOUNTS_CONTINUE_BTN = (
    "//button[normalize-space(.)='Continue' or normalize-space(.)='Switch']"
)
