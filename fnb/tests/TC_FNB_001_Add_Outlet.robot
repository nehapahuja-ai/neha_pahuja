# =============================================================================
# TC_FNB_001_Add_Outlet.robot
#
# Purpose : End-to-end regression — create a new FNB Food Outlet on the
#           Aeria property management staging dashboard.
# Flow    : OTP login (reuses shared tenant_admin flow) →
#           Outlets sidebar → Add Outlet (Food) →
#           Overview wizard step → Configuration wizard step →
#           Verify Tenant view (Drafted) → Switch to Site Admin → Verify
# Data    : ../testdata/outlet_data.yaml
# Run     : robot -d results fnb/tests/TC_FNB_001_Add_Outlet.robot
# =============================================================================

*** Settings ***
Documentation       End-to-end Add FNB Food Outlet test on Aeria staging.
...                 Login via the shared Tenant Admin OTP flow, then fill the
...                 2-step Add Outlet wizard and verify in Tenant and Site Admin views.

Variables           ../testdata/outlet_data.yaml
Resource            ../keywords/OutletKeywords.resource


*** Test Cases ***

TC_FNB_001 Add FNB Food Outlet End To End
    [Documentation]    Full E2E: OTP login, Add Outlet wizard (Overview + Configuration),
    ...                verify outlet in Tenant view as Drafted, switch to Site Admin and
    ...                confirm the outlet appears in the Site Admin outlets list.
    [Tags]             regression    outlet    fnb    food    e2e
    [Teardown]         Close All Browsers

    # ── Step 1: Login via shared Tenant Admin OTP flow ───────────────────────
    Login FNB Tenant Dashboard

    # ── Step 2: Navigate to Outlets → trigger Add Outlet ────────────────────
    Click Outlets In Sidebar
    Click Add Outlet Button
    Select Outlet Type              Food

    # ── Step 3: Overview (Wizard Step 1) ────────────────────────────────────
    ${outlet_name}=    Generate Dynamic Outlet Name    ${OUTLET_NAME_PREFIX}
    Set Suite Variable              ${CREATED_OUTLET_NAME}    ${outlet_name}

    Fill Outlet Overview
    ...    outlet_name=${outlet_name}
    ...    location_tower=${OUTLET_LOCATION_TOWER}
    ...    location_floor=${OUTLET_LOCATION_FLOOR}
    ...    fssai=${OUTLET_FSSAI}
    ...    phone=${OUTLET_PHONE}
    ...    email=${OUTLET_EMAIL}

    Click Next

    # ── Step 4: Configuration (Wizard Step 2) ───────────────────────────────
    Fill Outlet Configuration
    ...    cuisines=${OUTLET_CUISINES}
    ...    cost_for_two=${OUTLET_COST_FOR_TWO}
    ...    payment_collector=${OUTLET_PAYMENT_COLLECTOR}

    Click Done

    # ── Step 5: Verify outlet in Tenant view, open it, send for approval ───────
    Search Outlet                   ${CREATED_OUTLET_NAME}
    Verify Outlet In Tenant List    ${CREATED_OUTLET_NAME}    Drafted
    Open Outlet                     ${CREATED_OUTLET_NAME}
    Click Send Approval

    # ── Step 6: Switch to Site Admin, search, open, and approve outlet ─────────
    Switch To Site Admin            ${SITE_ADMIN_NAME}
    Click Outlets In Sidebar
    Search Outlet                   ${CREATED_OUTLET_NAME}
    Verify Outlet In Site Admin     ${CREATED_OUTLET_NAME}
    Open Outlet                     ${CREATED_OUTLET_NAME}
    Approve Outlet

    # ── Step 7: Switch back to Gravity By Prestige, find outlet, activate it ───────────
    Switch To Site Admin            ${TENANT_NAME}
    Click Outlets In Sidebar
    Search Outlet                   ${CREATED_OUTLET_NAME}
    Open Outlet                     ${CREATED_OUTLET_NAME}
    Activate Outlet
