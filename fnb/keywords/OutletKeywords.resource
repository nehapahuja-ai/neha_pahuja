# =============================================================================
# OutletKeywords.resource
#
# Outlet-specific Robot Framework keywords for TC_FNB_001.
# Browser lifecycle and OTP login are handled by the shared tenant_admin.robot
# resource (imported in the test suite).  This file only imports the
# OutletPage.py page object library.
# =============================================================================

*** Settings ***
Library    SeleniumLibrary
Library    ../pages/OutletPage.py

*** Keywords ***
Login FNB Tenant Dashboard
    Set Suite Variable    ${tenant_admin_username}    ${LOGIN_EMAIL}
    Set Suite Variable    ${property_name}           ${TENANT_NAME}
    Login Tenant Admin Dashboard
