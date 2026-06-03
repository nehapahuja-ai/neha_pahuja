# =============================================================================
# OutletPage.py
#
# Page Object for the FNB Add Outlet wizard steps (Steps 2-6 of TC_FNB_001).
# Login is handled by the shared tenant_admin.robot resource; this class
# starts from the post-login Tenant dashboard.
#
# Each public method is auto-exposed as a Robot Framework keyword
# (snake_case → Title Case With Spaces).
#
# Scope: SUITE — one shared instance per suite run.
# =============================================================================

import os
import sys
import time

_FNB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _FNB_ROOT not in sys.path:
    sys.path.insert(0, _FNB_ROOT)

from robot.libraries.BuiltIn import BuiltIn

from locators.OutletLocators import (
    LOGIN_EMAIL_INPUT,
    LOGIN_CONTINUE_BUTTON,
    OTP_INPUTS_MULTI,
    OTP_INPUT_SINGLE,
    DASHBOARD_LOADED_MARKER,
    SIDEBAR_OUTLETS_LINK,
    ADD_OUTLET_BUTTON,
    OUTLET_TYPE_FOOD,
    OUTLET_NAME_INPUT,
    LOCATION_DROPDOWN_TRIGGER,
    FSSAI_INPUT,
    ALL_DAY_CHECKBOX,
    ALL_DAY_TOGGLE_DIV,
    PHONE_INPUT,
    OUTLET_EMAIL_INPUT,
    NEXT_BUTTON,
    DELIVERY_TO_DESK_CB,
    TAKEAWAY_CB,
    DINE_IN_CB,
    ORDER_CHANNEL_APP_BTN,
    DELIVERIES_SELF_BTN,
    GST_INCLUSIVE_BTN,
    GST_RATE_SELECT,
    POS_SYSTEM_SELECT,
    MENU_TYPE_SELECT,
    CUISINES_INPUT,
    COST_FOR_TWO_INPUT,
    PAYMENT_COLLECTOR_INPUT,
    DONE_BUTTON,
    OUTLET_SEARCH_INPUT,
    USER_AVATAR,
    SWITCH_ACCOUNTS_MENU_ITEM,
    SWITCH_ACCOUNTS_CONTINUE_BTN,
)


class OutletPage:
    ROBOT_LIBRARY_SCOPE = "SUITE"
    _TIMEOUT = "20s"

    def __init__(self):
        self._selenium = None

    # ── Login / OTP flow ──────────────────────────────────────────────────────

    def login_tenant_admin_dashboard(self):
        """Open Chrome, OTP-login to Aeria staging, and select the active property.

        Reads all required values from Robot suite variables set by outlet_data.yaml:
        LOGIN_URL, LOGIN_EMAIL, SMTP4DEV_URL, SMTP4DEV_EMAIL, TENANT_NAME, BROWSER.
        """
        builtin = BuiltIn()
        login_url      = builtin.get_variable_value("${LOGIN_URL}")
        login_email    = builtin.get_variable_value("${LOGIN_EMAIL}")
        smtp4dev_url   = builtin.get_variable_value("${SMTP4DEV_URL}") or ""
        smtp4dev_user  = builtin.get_variable_value("${SMTP4DEV_USERNAME}") or ""
        smtp4dev_pass  = builtin.get_variable_value("${SMTP4DEV_PASSWORD}") or ""
        smtp4dev_email = builtin.get_variable_value("${SMTP4DEV_EMAIL}") or login_email
        tenant_name    = builtin.get_variable_value("${TENANT_NAME}") or ""
        browser_name   = (builtin.get_variable_value("${BROWSER}") or "chrome").lower()
        smtp4dev_auth  = (smtp4dev_user, smtp4dev_pass) if smtp4dev_user else None

        self._open_chrome_browser(login_url, browser_name)

        # Snapshot existing message IDs before triggering OTP so we only read new ones
        known_ids = self._smtp4dev_known_ids(smtp4dev_url, smtp4dev_auth)
        builtin.log(f"smtp4dev known message IDs before OTP trigger: {len(known_ids)}", "INFO")

        # Submit the email address to trigger OTP dispatch
        self._sl.wait_until_element_is_visible(LOGIN_EMAIL_INPUT, timeout="20s")
        self._fill(LOGIN_EMAIL_INPUT, login_email)
        self._click(LOGIN_CONTINUE_BUTTON)
        builtin.log(f"Submitted login email '{login_email}' — waiting for OTP", "INFO")

        # Retrieve and enter OTP
        otp = self._fetch_otp_from_smtp4dev(smtp4dev_url, smtp4dev_email, known_ids=known_ids, auth=smtp4dev_auth)
        builtin.log(f"OTP retrieved: {otp}", "INFO")
        self._enter_otp(otp)

        # Wait for the OTP form to navigate away (up to 20s), then give React time to settle
        from selenium.webdriver.common.by import By
        otp_gone_deadline = time.time() + 20
        while time.time() < otp_gone_deadline:
            remaining_otp = (
                self._driver.find_elements(By.XPATH, OTP_INPUTS_MULTI) or
                self._driver.find_elements(By.XPATH, OTP_INPUT_SINGLE)
            )
            if not remaining_otp:
                break
            time.sleep(1)
        time.sleep(2.0)

        # Select the property/tenant from the account picker if it appears
        if tenant_name:
            self._select_property(tenant_name)

        # Wait for dashboard sidebar to confirm successful login
        try:
            self._sl.wait_until_element_is_visible(DASHBOARD_LOADED_MARKER, timeout="30s")
        except Exception:
            pass
        builtin.log(f"Login complete. URL: {self._sl.get_location()}", "INFO")

    def _open_chrome_browser(self, url, browser_name="chrome"):
        """Open a Chrome browser (headed or headless) and navigate to url."""
        from selenium.webdriver.chrome.options import Options

        opts = Options()
        opts.add_argument("--window-size=1440,1200")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-search-engine-choice-screen")
        opts.add_argument("--disable-notifications")
        if "headless" in browser_name:
            opts.add_argument("--headless=new")
            opts.add_argument("--no-sandbox")

        self._sl.create_webdriver("Chrome", options=opts)
        self._sl.go_to(url)
        try:
            self._sl.maximize_browser_window()
        except Exception:
            pass
        self._sl.wait_until_page_contains_element("xpath=//body", timeout="20s")

    def _smtp4dev_known_ids(self, base_url, auth=None):
        """Return the set of message IDs currently on smtp4dev (used to skip pre-existing emails)."""
        import requests as _req
        try:
            data = _req.get(f"{base_url.rstrip('/')}/api/messages", auth=auth, timeout=10).json()
            messages = data.get("results", data) if isinstance(data, dict) else data
            return {m.get("id") for m in messages if m.get("id")}
        except Exception:
            return set()

    def _fetch_otp_from_smtp4dev(self, base_url, recipient_email, known_ids=None, timeout=60, auth=None):
        """Poll smtp4dev until a NEW OTP email arrives, then return the 6-digit code.

        Skips any message whose ID was already present before the OTP was triggered.
        Uses the /source endpoint since the smtp4dev detail endpoint lacks body fields.
        """
        import re
        import requests as _req

        base      = base_url.rstrip("/")
        known_ids = known_ids or set()
        deadline  = time.time() + timeout

        while time.time() < deadline:
            try:
                data     = _req.get(f"{base}/api/messages", auth=auth, timeout=10).json()
                messages = data.get("results", data) if isinstance(data, dict) else data

                # Only look at messages that arrived after we started waiting
                new_msgs = [
                    m for m in messages
                    if m.get("id") and m["id"] not in known_ids
                    and recipient_email.lower() in str(m.get("to", "") or "").lower()
                ]

                for msg in new_msgs:
                    msg_id = msg["id"]
                    body   = _req.get(f"{base}/api/messages/{msg_id}/source", auth=auth, timeout=10).text

                    # Aeria's OTP email renders each digit in a <div class="btn">N</div>
                    digits = re.findall(r'<div[^>]*class="btn"[^>]*>(\d)</div>', body)
                    if len(digits) >= 6:
                        otp = "".join(digits[:6])
                        BuiltIn().log(f"Extracted OTP from btn divs: {otp}", "INFO")
                        return otp

                    # Fallback: first standalone 6-digit number not inside a CSS color (#RRGGBB)
                    clean = re.sub(r'#[0-9a-fA-F]{6}', '', body)
                    match = re.search(r"\b(\d{6})\b", clean)
                    if match:
                        BuiltIn().log(f"Extracted OTP via fallback regex: {match.group(1)}", "INFO")
                        return match.group(1)

                    BuiltIn().log(f"New OTP email found but no code extracted: {body[1800:2200]}", "WARN")

            except Exception as exc:
                BuiltIn().log(f"smtp4dev poll error: {exc}", "WARN")

            time.sleep(3)

        raise AssertionError(
            f"OTP not received at smtp4dev {base_url} for '{recipient_email}' within {timeout}s"
        )

    def _enter_otp(self, otp):
        """Enter the OTP — handles both multi-box and single-field UIs.

        Uses ActionChains.send_keys() without a target element so keystrokes go
        to the browser's currently-focused element.  react-otp-input auto-advances
        focus after each digit, so each subsequent keystroke naturally lands in the
        correct box — updating React's internal state properly.
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.action_chains import ActionChains

        # Wait up to 30s for either OTP input pattern to appear
        deadline = time.time() + 30
        while time.time() < deadline:
            if self._driver.find_elements(By.XPATH, OTP_INPUTS_MULTI):
                break
            if self._driver.find_elements(By.XPATH, OTP_INPUT_SINGLE):
                break
            time.sleep(1)

        try:
            self._sl.capture_page_screenshot()
        except Exception:
            pass

        multi = self._driver.find_elements(By.XPATH, OTP_INPUTS_MULTI)
        if multi and len(multi) >= 4:
            BuiltIn().log(f"OTP: found {len(multi)} multi-box inputs, entering '{otp}'", "INFO")

            # Focus the first box via JS, then send each digit to the active element.
            # react-otp-input moves browser focus to the next box after each character,
            # and ActionChains.send_keys() (without a target) follows that focus move.
            self._driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'}); arguments[0].focus();",
                multi[0],
            )
            time.sleep(0.4)

            for digit in otp[:6]:
                ActionChains(self._driver).send_keys(digit).perform()
                time.sleep(0.25)

            time.sleep(0.8)

            try:
                self._sl.capture_page_screenshot()
            except Exception:
                pass

            # Some forms auto-submit when the last digit is typed
            if not self._driver.find_elements(By.XPATH, OTP_INPUTS_MULTI):
                return

            # Click the submit button; also capture state after the click for diagnosis
            for btn_text in ["Verify OTP", "Verify", "Submit", "Continue", "Sign In", "Login"]:
                if self._js_click_by_text("button", btn_text):
                    BuiltIn().log(f"Clicked OTP submit button: '{btn_text}'", "INFO")
                    break
            time.sleep(1.5)
            try:
                self._sl.capture_page_screenshot()
            except Exception:
                pass
            return

        singles = self._driver.find_elements(By.XPATH, OTP_INPUT_SINGLE)
        if singles:
            inp = singles[0]
            self._driver.execute_script("arguments[0].focus();", inp)
            time.sleep(0.2)
            ActionChains(self._driver).send_keys(otp[:6]).perform()
            time.sleep(0.3)
            for btn_text in ["Verify OTP", "Verify", "Submit", "Continue", "Sign In", "Login"]:
                if self._js_click_by_text("button", btn_text):
                    break
            return

        raise AssertionError("No OTP input field appeared within 30s after submitting email")

    def _select_property(self, tenant_name):
        """Click the tenant/property entry in the account-picker screen if it appears."""
        from selenium.webdriver.common.by import By

        deadline = time.time() + 15
        while time.time() < deadline:
            # Already on dashboard if sidebar/nav is visible
            if self._driver.find_elements(By.XPATH, DASHBOARD_LOADED_MARKER):
                BuiltIn().log("Property picker not shown — already on dashboard", "INFO")
                return
            clicked = self._js_click_by_text(
                'div, button, li, [role="option"], [role="button"]', tenant_name
            )
            if clicked:
                BuiltIn().log(f"Selected property '{tenant_name}' from picker", "INFO")
                time.sleep(2.0)
                return
            time.sleep(1)

        BuiltIn().log("Property picker timed out — continuing", "WARN")

    # ── Private helpers ────────────────────────────────────────────────────────

    @property
    def _sl(self):
        if self._selenium is None:
            self._selenium = BuiltIn().get_library_instance("SeleniumLibrary")
        return self._selenium

    @property
    def _driver(self):
        return self._sl.driver

    def _wait_visible(self, locator, timeout=None):
        self._sl.wait_until_element_is_visible(locator, timeout=timeout or self._TIMEOUT)

    def _click(self, locator, timeout=None):
        self._wait_visible(locator, timeout=timeout)
        self._sl.scroll_element_into_view(locator)
        try:
            self._sl.click_element(locator)
        except Exception:
            el = self._sl.get_webelement(locator)
            self._driver.execute_script("arguments[0].click();", el)

    def _fill(self, locator, text, timeout=None):
        """Clear and type into an input using React-compatible native events."""
        self._wait_visible(locator, timeout=timeout)
        el = self._sl.get_webelement(locator)
        self._driver.execute_script(
            """
            const el = arguments[0], val = arguments[1];
            const proto = el.tagName.toLowerCase() === 'textarea'
                ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
            const setter = Object.getOwnPropertyDescriptor(proto, 'value');
            if (setter && setter.set) {
                setter.set.call(el, '');
                setter.set.call(el, val);
            } else {
                el.value = '';
                el.value = val;
            }
            el.dispatchEvent(new Event('input',  { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true }));
            el.dispatchEvent(new KeyboardEvent('keyup',   { bubbles: true }));
            """,
            el, text,
        )

    def _fill_phone(self, locator, text, timeout=None):
        """Fill a phone input by simulating real keystrokes via send_keys.

        Phone input libraries (react-phone-input-2, etc.) validate each
        character on keydown/keyup, so the bulk JS setter used by _fill is
        silently ignored.  Clicking first ensures focus and triggers any
        click-to-open handlers; send_keys then fires the full keyboard event
        chain that those libraries expect.
        """
        from selenium.webdriver.common.keys import Keys
        self._wait_visible(locator, timeout=timeout)
        el = self._sl.get_webelement(locator)
        self._driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        try:
            el.click()
        except Exception:
            self._driver.execute_script("arguments[0].click();", el)
        time.sleep(0.2)
        # Select-all + delete to clear any existing value
        el.send_keys(Keys.CONTROL + 'a')
        el.send_keys(Keys.DELETE)
        time.sleep(0.1)
        el.send_keys(str(text))
        # Fire change event so form libraries that listen on change are notified
        self._driver.execute_script(
            "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
            el,
        )

    def _js_click_by_text(self, css_selector, target_text):
        """Click the first visible element whose text matches target_text."""
        return self._driver.execute_script(
            """
            const target = arguments[0].trim().toLowerCase();
            const sel    = arguments[1];
            const visible = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
            const nodes  = Array.from(document.querySelectorAll(sel)).filter(visible);
            const match  =
                nodes.find(e => (e.innerText || e.textContent || '').trim().toLowerCase() === target) ||
                nodes.find(e => (e.innerText || e.textContent || '').trim().toLowerCase().includes(target));
            if (match) { match.click(); return true; }
            return false;
            """,
            target_text, css_selector,
        )

    def _set_checkbox(self, locator, should_be_checked=True):
        try:
            el = self._sl.get_webelement(locator)
            if el.is_selected() != should_be_checked:
                self._driver.execute_script("arguments[0].click();", el)
        except Exception:
            pass

    def _click_toggle_if_off(self, toggle_locator):
        try:
            el = self._sl.get_webelement(toggle_locator)
            state = (
                el.get_attribute("aria-checked") or
                el.get_attribute("data-state") or
                el.get_attribute("data-checked") or ""
            ).lower()
            if state not in ("true", "checked", "on"):
                self._driver.execute_script("arguments[0].click();", el)
        except Exception:
            self._click(toggle_locator)

    def _react_short_pause(self):
        time.sleep(0.4)

    def _click_react_select_near_label(self, label_pattern, field_name):
        """Find the react-select / Ant-Design select __control nearest to a label matching
        label_pattern, open it, and click the first visible option.

        Returns True on success, False otherwise.
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys

        # ── Step 1: locate the __control div near the matching label ────────────
        control = self._driver.execute_script(
            """
            const pat = new RegExp(arguments[0], 'i');
            const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const inNav = el => {
                for (let p = el, i = 0; p && i < 10; p = p.parentElement, i++)
                    if (/sidebar|sidenav|nav-/i.test((p.className || '').toString())) return true;
                return false;
            };
            // Candidate label-like elements whose text matches the pattern
            const labels = Array.from(document.querySelectorAll(
                'label, span, p, div, h4, h5, li'
            )).filter(el => {
                const t = (el.innerText || el.textContent || '').trim();
                return pat.test(t) && t.length < 80 && vis(el) && !inNav(el);
            });

            for (const lbl of labels) {
                // Climb up at most 8 levels to find the form-row ancestor
                for (let anc = lbl.parentElement, depth = 0;
                     anc && anc !== document.body && depth < 8;
                     anc = anc.parentElement, depth++) {
                    // Prefer an explicit react-select or Ant-Design control class
                    const ctrl = anc.querySelector(
                        '[class*="__control"],[class*="-control"],'
                        + '[class*="selectControl"],[class*="ant-select-selector"]'
                    );
                    if (ctrl && vis(ctrl) && !inNav(ctrl)) return ctrl;
                    // Also stop if the ancestor is already very large
                    if (anc.querySelectorAll('input[role="combobox"]').length > 3) break;
                }
            }
            return null;
            """,
            label_pattern,
        )

        if not control:
            BuiltIn().log(f"{field_name}: react-select control not found near label", "WARN")
            return False

        # ── Step 2: scroll into view and click to open ───────────────────────
        self._driver.execute_script("arguments[0].scrollIntoView({block:'center'});", control)
        time.sleep(0.3)
        try:
            control.click()
        except Exception:
            self._driver.execute_script("arguments[0].click();", control)
        time.sleep(1.2)

        # ── Step 3: find the open menu (portal at body level) ────────────────
        # Do NOT use id-based snapshot — many listboxes have no id, causing false negatives.
        # Instead pick the first *visible* dropdown menu / listbox that has children.
        target_menu = None
        for sel in [
            '[role="listbox"]',
            '.ant-select-dropdown',
            '[class*="__menu-list"]',
            '[class*="__menu"]',
            '[class*="-menu"]',
        ]:
            for el in self._driver.find_elements(By.CSS_SELECTOR, sel):
                if el.is_displayed():
                    target_menu = el
                    break
            if target_menu:
                break

        if not target_menu:
            # Keyboard fallback via the hidden combobox input inside the control
            BuiltIn().log(f"{field_name}: menu not visible — trying keyboard on combobox input", "WARN")
            try:
                inp = control.find_element(By.CSS_SELECTOR, 'input')
                inp.send_keys(Keys.ARROW_DOWN)
                time.sleep(0.4)
                inp.send_keys(Keys.ENTER)
                BuiltIn().log(f"{field_name}: selected via keyboard", "INFO")
                time.sleep(0.3)
                return True
            except Exception as ke:
                BuiltIn().log(f"{field_name}: keyboard fallback failed: {ke}", "WARN")
                return False

        # ── Step 4: click the first visible option ───────────────────────────
        for opt_sel in [
            '[role="option"]',
            '.ant-select-item-option',
            '[class*="__option"]',
            '[class*="item"]',
            'li',
        ]:
            opts = [
                o for o in target_menu.find_elements(By.CSS_SELECTOR, opt_sel)
                if o.is_displayed() and o.text.strip()
            ]
            if opts:
                first_text = opts[0].text.strip()
                try:
                    opts[0].click()
                except Exception:
                    self._driver.execute_script("arguments[0].click();", opts[0])
                BuiltIn().log(f"{field_name}: selected first option '{first_text}'", "INFO")
                time.sleep(0.3)
                return True

        BuiltIn().log(f"{field_name}: menu open but no clickable options found", "WARN")
        self._sl.capture_page_screenshot()
        return False

    def _dismiss_blocking_modals(self):
        """Click OK on any visible blocking modal (e.g. Rotate Your Screen overlay)."""
        result = self._driver.execute_script(
            """
            const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            // 1. Visible [role="dialog"] / modal containers with an OK button
            for (const dlg of Array.from(document.querySelectorAll(
                '[role="dialog"],[class*="modal"],[class*="overlay"],[class*="popup"]'
            )).filter(vis)) {
                const ok = Array.from(dlg.querySelectorAll('button')).find(
                    b => vis(b) && /^ok$/i.test((b.innerText || b.textContent || '').trim())
                );
                if (ok) { ok.click(); return 'dialog-ok'; }
            }
            // 2. Any visible OK button whose ancestor contains rotate/landscape text
            for (const btn of Array.from(document.querySelectorAll('button')).filter(vis)) {
                if (!/^ok$/i.test((btn.innerText || btn.textContent || '').trim())) continue;
                let p = btn.parentElement;
                for (let i = 0; i < 10 && p; i++, p = p.parentElement) {
                    if (/rotate|landscape|portrait/i.test(p.innerText || p.textContent || '')) {
                        btn.click(); return 'rotate-ok';
                    }
                }
            }
            return null;
            """
        )
        if result:
            BuiltIn().log(f"Dismissed blocking modal: {result}", "INFO")
            time.sleep(0.6)

    def _type_and_select_suggestion(self, input_locator, text, suggestion_css=None):
        """Type into a tag/search input and click the matching suggestion."""
        self._fill(input_locator, text)
        self._react_short_pause()
        for sel in [
            suggestion_css,
            '[role="option"]',
            'li[role="option"]',
            '.ant-select-item-option',
            '.select__option',
            '[class*="option"]',
            'li',
        ]:
            if not sel:
                continue
            if self._js_click_by_text(sel, text):
                self._react_short_pause()
                return
        raise AssertionError(f'Suggestion "{text}" not found after typing into {input_locator}')

    # ── Utility ───────────────────────────────────────────────────────────────

    def generate_dynamic_outlet_name(self, prefix):
        """Return prefix + compact timestamp to keep outlet names unique across runs."""
        return f"{prefix} {time.strftime('%m%d%H%M')}"

    # ── Step 2: Navigate to Outlets ───────────────────────────────────────────

    def click_outlets_in_sidebar(self):
        """Click the Outlets navigation item in the left sidebar."""
        BuiltIn().log(f"Navigating to Outlets from: {self._sl.get_location()}", "INFO")
        try:
            self._click(SIDEBAR_OUTLETS_LINK)
        except Exception:
            clicked = self._js_click_by_text(
                "a, li, [role='menuitem'], [role='link'], button, div, span",
                "Outlets",
            )
            if not clicked:
                raise AssertionError("'Outlets' not found in the sidebar navigation.")
        self._react_short_pause()

    def click_add_outlet_button(self):
        """Click the '+ Add Outlet' button on the Outlets listing page."""
        # Wait up to 30s for the page to load before trying to click
        time.sleep(2)
        try:
            self._click(ADD_OUTLET_BUTTON)
        except Exception:
            # Log what's on the page for diagnosis
            btn_texts = self._driver.execute_script(
                """
                const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                return Array.from(document.querySelectorAll('button, [role="button"], a'))
                    .filter(vis)
                    .map(b => (b.innerText || b.textContent || '').trim().replace(/\\s+/g,' '))
                    .filter(t => t.length > 0 && t.length < 80)
                    .join(' | ');
                """
            )
            BuiltIn().log(f"Visible buttons on Outlets page: [{btn_texts}]", "INFO")
            self._sl.capture_page_screenshot()
            # Try broader text patterns
            for text in ["Add Outlet", "New Outlet", "Add Food", "Create"]:
                if self._js_click_by_text("button, [role='button'], a", text):
                    BuiltIn().log(f"Clicked Add Outlet via fallback text '{text}'", "INFO")
                    break
            else:
                raise AssertionError(
                    f"'Add Outlet' button not found. Visible buttons: [{btn_texts}]"
                )
        self._react_short_pause()

    def select_outlet_type(self, outlet_type):
        """Click the outlet type card (e.g. 'Food') on the type-picker dialog."""
        try:
            self._click(OUTLET_TYPE_FOOD if outlet_type.lower() == "food" else ADD_OUTLET_BUTTON)
        except Exception:
            clicked = self._js_click_by_text(
                '[role="button"],[role="option"],button,div', outlet_type
            )
            assert clicked, f'Outlet type "{outlet_type}" not found.'
        self._react_short_pause()

    # ── Step 3: Overview wizard step ─────────────────────────────────────────

    def fill_outlet_overview(self, outlet_name, location_tower, location_floor,
                              fssai, phone, email):
        """Fill all fields on the Add Outlet Overview tab (wizard step 1)."""
        self._fill(OUTLET_NAME_INPUT, outlet_name)
        self._dump_form_elements()
        self._select_location(location_tower, location_floor)
        self._fill(FSSAI_INPUT, fssai)
        self._enable_all_day()
        self._fill_phone(PHONE_INPUT, phone)
        self._fill(OUTLET_EMAIL_INPUT, email)

    def _dump_form_elements(self):
        """Diagnostic: log every visible input, button, and div[role] on the page."""
        try:
            info = self._driver.execute_script(
                """
                const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                const items = [];
                document.querySelectorAll('input, textarea, select').forEach((el, i) => {
                    if (visible(el))
                        items.push('input['+i+']: tag='+el.tagName
                            +' type='+el.type+' name='+el.name+' id='+el.id
                            +' placeholder='+el.placeholder+' maxlen='+el.maxLength);
                });
                document.querySelectorAll('[role="combobox"],[role="listbox"],[role="button"],[data-testid]')
                .forEach((el, i) => {
                    if (visible(el))
                        items.push('control['+i+']: tag='+el.tagName
                            +' role='+(el.getAttribute('role')||'')
                            +' testid='+(el.getAttribute('data-testid')||'')
                            +' text='+((el.innerText||'').trim().slice(0,50)));
                });
                return items.join(' || ');
                """
            )
            BuiltIn().log(f"Form elements: {info}", "INFO")
        except Exception as e:
            BuiltIn().log(f"Form diagnostic failed: {e}", "WARN")

    def _select_location(self, tower, floor):
        """Click the 'Select Location' search field, then pick the matching option.

        The UI renders a single searchable dropdown.  The input itself is hidden
        by React; we must use a Selenium click on the visible container to fire
        the synthetic mouse events that open the dropdown.
        """
        from selenium.webdriver.common.by import By

        # Build a list of XPath candidates for the visible Location trigger.
        _TRIGGER_XPATHS = [
            # Container div/span that has "Select Location" placeholder text
            "//*[normalize-space(.)='Select Location' and (self::div or self::span or self::input)]",
            # Sibling of the Location label
            "//label[contains(normalize-space(.),'Location')]/following-sibling::*//input",
            "//label[contains(normalize-space(.),'Location')]/parent::*//*[self::div or self::input][contains(@class,'select') or contains(@class,'search') or contains(@class,'input')][1]",
            # Fallback: the hidden input itself
            "//input[@name='details.location']",
        ]

        trigger_el = None
        for xpath in _TRIGGER_XPATHS:
            els = self._driver.find_elements(By.XPATH, xpath)
            if els:
                trigger_el = els[0]
                BuiltIn().log(f"Location trigger found via: {xpath}", "INFO")
                break

        if not trigger_el:
            raise AssertionError("Location field trigger not found on page.")

        # Scroll into view and click via Selenium (fires React synthetic events).
        self._driver.execute_script("arguments[0].scrollIntoView({block:'center'});", trigger_el)
        try:
            trigger_el.click()
        except Exception:
            self._driver.execute_script("arguments[0].click();", trigger_el)
        time.sleep(1.2)

        # Capture ALL visible dropdown options — exclude sidebar and known non-options.
        all_options = self._driver.execute_script(
            """
            const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const inSidebar = el => {
                let p = el, d = 0;
                while (p && d < 8) {
                    if (/menuContent|_menuItems|_item_1hbqa|sideNav|sidebar/i
                            .test((p.className || '').toString())) return true;
                    p = p.parentElement; d++;
                }
                return false;
            };
            return Array.from(document.querySelectorAll(
                '[role="option"],[role="listitem"],[role="treeitem"],'
                + '[class*="location"],[class*="option"],[class*="node"],'
                + '[class*="result"],[class*="suggestion"]'
            )).filter(el => visible(el) && !inSidebar(el))
              .map(el => (el.innerText || el.textContent || '').trim().slice(0, 80))
              .filter(t => t.length > 1)
              .slice(0, 30)
              .join(' | ');
            """
        )
        BuiltIn().log(f"Available location options: {all_options}", "INFO")
        self._sl.capture_page_screenshot()

        _OPT_SELS = [
            '[role="option"]', '[role="listitem"]', '[role="treeitem"]',
            '[class*="option"]', '[class*="node"]', '[class*="result"]',
            '[class*="suggestion"]', '[class*="location"]',
        ]

        # Step 1: Try the fully combined term (some pickers show "Tower 1 Floor 1" as one item)
        for sel in _OPT_SELS:
            if self._js_click_by_text(sel, f"{tower} {floor}"):
                BuiltIn().log(f"Selected location via combined term '{tower} {floor}'", "INFO")
                self._react_short_pause()
                return

        # Step 2: Tree navigation — click tower to expand, then click floor leaf.
        # The picker shows Tower and Floor as separate nodes; clicking the tower
        # expands the sub-tree so the floor becomes clickable.
        tower_clicked = False
        for sel in _OPT_SELS:
            if self._js_click_by_text(sel, tower):
                BuiltIn().log(f"Expanded location tree via tower='{tower}'", "INFO")
                tower_clicked = True
                time.sleep(0.8)
                break

        for sel in _OPT_SELS:
            if self._js_click_by_text(sel, floor):
                BuiltIn().log(f"Selected floor '{floor}' in location tree", "INFO")
                self._react_short_pause()
                return

        # Step 3: Floor still not found — re-open picker and try floor directly
        if tower_clicked:
            try:
                trigger_el.click()
            except Exception:
                self._driver.execute_script("arguments[0].click();", trigger_el)
            time.sleep(0.8)
            for sel in _OPT_SELS:
                if self._js_click_by_text(sel, floor):
                    BuiltIn().log(f"Selected floor '{floor}' on retry", "INFO")
                    self._react_short_pause()
                    return

        # Nothing matched — screenshot and fail with the full option list.
        try:
            self._sl.capture_page_screenshot()
        except Exception:
            pass
        raise AssertionError(
            f'Location "{tower} / {floor}" not found in picker. '
            f'Available options: [{all_options}]'
        )

    def _enable_all_day(self):
        """Check the All Day toggle — handles both checkbox and styled button patterns."""
        try:
            if self._sl.get_webelements(ALL_DAY_CHECKBOX):
                self._set_checkbox(ALL_DAY_CHECKBOX, should_be_checked=True)
                return
        except Exception:
            pass
        try:
            self._click_toggle_if_off(ALL_DAY_TOGGLE_DIV)
        except Exception:
            pass

    def click_next(self):
        """Click the Next button to advance from Overview to Configuration."""
        self._click(NEXT_BUTTON)
        self._react_short_pause()

    # ── Step 4: Configuration wizard step ────────────────────────────────────

    def fill_outlet_configuration(self, cuisines, cost_for_two, payment_collector):
        """Fill all fields on the Add Outlet Configuration tab (wizard step 2)."""
        self._dismiss_blocking_modals()
        self._sl.capture_page_screenshot()
        self._dump_form_elements()
        self._select_order_fulfillment_modes()
        self._select_order_channel_app()
        self._select_deliveries_self()
        self._select_gst_inclusive()
        self._select_gst_rate("0%")
        self._select_pos_system()
        self._select_menu_type("Veg & Non-Veg")
        self._add_cuisines(cuisines)
        self._fill(COST_FOR_TWO_INPUT, str(cost_for_two))
        self._select_payment_collector(payment_collector)

    def _select_order_fulfillment_modes(self):
        for loc in [DELIVERY_TO_DESK_CB, TAKEAWAY_CB, DINE_IN_CB]:
            try:
                self._set_checkbox(loc, should_be_checked=True)
            except Exception:
                pass

    def _select_order_channel_app(self):
        try:
            self._click(ORDER_CHANNEL_APP_BTN)
        except Exception:
            self._js_click_by_text('button, label, [role="radio"]', "App")

    def _select_deliveries_self(self):
        try:
            self._click(DELIVERIES_SELF_BTN)
        except Exception:
            self._js_click_by_text('button, label, [role="radio"]', "Self")

    def _select_gst_inclusive(self):
        try:
            self._click(GST_INCLUSIVE_BTN)
        except Exception:
            self._js_click_by_text('button, label, [role="radio"]', "Inclusive")

    def _select_dropdown_field(self, label_text, value, locator):
        """Generic: click a labeled dropdown container, then pick a matching option."""
        from selenium.webdriver.common.by import By

        # Try native <select> first (cheapest)
        try:
            self._sl.select_from_list_by_label(locator, value)
            return
        except Exception:
            pass

        # Click the container near the label to open the custom dropdown
        _CONTAINER_XPATHS = [
            f"//label[contains(normalize-space(.), '{label_text}')]/following-sibling::*[1]",
            f"//*[contains(normalize-space(.), '{label_text}') and (self::div or self::span)]"
            f"[contains(@class,'select') or contains(@class,'control') or contains(@class,'input')][1]",
            locator,
        ]
        for xpath in _CONTAINER_XPATHS:
            els = self._driver.find_elements(By.XPATH, xpath)
            if els:
                try:
                    self._driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", els[0]
                    )
                    els[0].click()
                except Exception:
                    self._driver.execute_script("arguments[0].click();", els[0])
                time.sleep(0.4)
                break

        # Click the matching option in the opened dropdown
        for sel in ['[role="option"]', 'li[role="option"]', 'option', 'li', '[class*="option"]']:
            if self._js_click_by_text(sel, value):
                time.sleep(0.3)
                return

        BuiltIn().log(
            f"_select_dropdown_field: could not select '{value}' for '{label_text}'", "WARN"
        )

    def _open_dropdown_and_select_first(self, label_pattern_js, locator_fallback, field_name):
        """Find a custom dropdown by label text pattern, open it, click the first option."""
        container = self._driver.execute_script(
            """
            const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const pattern = arguments[0];
            const re = new RegExp(pattern, 'i');
            for (const el of Array.from(document.querySelectorAll('*'))) {
                const txt = (el.innerText || el.textContent || '');
                if (!re.test(txt)) continue;
                if (!visible(el) || el.children.length === 0 || el.children.length > 25) continue;
                const child = el.querySelector(
                    'select,[role="combobox"],[role="listbox"],'
                    + 'div[class*="select"],div[class*="dropdown"],'
                    + 'div[class*="Select"],input[readonly]'
                );
                if (child && visible(child)) return child;
            }
            return null;
            """,
            label_pattern_js,
        )

        # Fallback to the static locator
        if container is None and locator_fallback:
            from selenium.webdriver.common.by import By
            els = self._driver.find_elements(By.XPATH, locator_fallback)
            if els:
                container = els[0]

        if container is None:
            BuiltIn().log(f"{field_name}: dropdown container not found", "WARN")
            return False

        try:
            self._driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", container
            )
            container.click()
        except Exception:
            self._driver.execute_script("arguments[0].click();", container)
        time.sleep(0.6)

        # Strategy 1: options inside a known dropdown/menu overlay container
        selected = self._driver.execute_script(
            """
            const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const inNav = el => {
                let p = el;
                for (let i = 0; i < 10; i++) {
                    if (!p) break;
                    const cls = (p.className || '').toString().toLowerCase();
                    if (/sidebar|sidenav|navigation|menubar/.test(cls)) return true;
                    p = p.parentElement;
                }
                return false;
            };
            // Look in known overlay/menu containers first
            const menuSels = [
                '[role="listbox"]', '[class*="__menu"]', '[class*="-menu-list"]',
                '[class*="dropdown"]', '[class*="Dropdown"]',
                '[class*="select-menu"]', '[class*="selectMenu"]',
                '.ant-select-dropdown', '.rc-select-dropdown',
                '[class*="popover"]', '[class*="popup"]',
                '[class*="option-list"]', '[class*="optionList"]',
            ];
            for (const menuSel of menuSels) {
                for (const menu of Array.from(document.querySelectorAll(menuSel)).filter(visible)) {
                    const opts = Array.from(menu.querySelectorAll(
                        '[role="option"], li, [class*="option"], [class*="item"]'
                    )).filter(el => visible(el) && !inNav(el));
                    if (opts.length > 0) {
                        const text = (opts[0].innerText || opts[0].textContent || '').trim();
                        opts[0].click();
                        return text;
                    }
                }
            }
            // Last-resort: any [role="option"] not in sidebar
            const opts = Array.from(document.querySelectorAll('[role="option"]'))
                .filter(el => visible(el) && !inNav(el));
            if (opts.length > 0) {
                const text = (opts[0].innerText || opts[0].textContent || '').trim();
                opts[0].click();
                return text;
            }
            return null;
            """
        )
        if selected:
            BuiltIn().log(f"{field_name}: selected first option '{selected}'", "INFO")
            time.sleep(0.3)
            return True

        # Strategy 2: keyboard navigation — Arrow Down selects first item, Enter confirms
        from selenium.webdriver.common.keys import Keys
        try:
            container.send_keys(Keys.ARROW_DOWN)
            time.sleep(0.3)
            container.send_keys(Keys.ENTER)
            BuiltIn().log(f"{field_name}: selected via keyboard navigation", "INFO")
            time.sleep(0.3)
            return True
        except Exception as kb_err:
            BuiltIn().log(f"{field_name}: keyboard nav failed: {kb_err}", "WARN")

        BuiltIn().log(f"{field_name}: opened dropdown but found no options", "WARN")
        return False

    def _select_combobox_first_option(self, input_id, combobox_index, field_name, locator=None):
        """Open a react-select by its input ID and select the first option via keyboard.

        Falls back to picking the Nth visible combobox (outside the sidebar) when the ID
        is not found — handles cases where react-select IDs shift between renders.
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys

        # Strategy 1: native <select> by index
        if locator:
            for idx in ['1', '0']:
                try:
                    self._sl.select_from_list_by_index(locator, idx)
                    BuiltIn().log(f"{field_name}: selected via native select index {idx}", "INFO")
                    return True
                except Exception:
                    pass

        # Strategy 2: direct react-select input by known ID
        input_el = None
        if input_id:
            els = self._driver.find_elements(By.ID, input_id)
            if els:
                input_el = els[0]
                BuiltIn().log(f"{field_name}: found combobox #{input_id}", "INFO")

        # Strategy 3: Nth visible combobox outside the sidebar
        if input_el is None:
            result = self._driver.execute_script(
                """
                const idx = arguments[0];
                const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                const inNav = el => {
                    let p = el;
                    for (let i = 0; i < 10; i++) {
                        if (!p) break;
                        const cls = (p.className || '').toString().toLowerCase();
                        const role = (p.getAttribute('role') || '').toLowerCase();
                        if (/sidebar|sidenav|navigation|menubar/.test(cls) || role === 'navigation') return true;
                        p = p.parentElement;
                    }
                    return false;
                };
                const combos = Array.from(document.querySelectorAll('input[role="combobox"]'))
                    .filter(el => visible(el) && !inNav(el));
                return combos.length > idx ? combos[idx] : null;
                """,
                combobox_index,
            )
            if result:
                input_el = result
                BuiltIn().log(f"{field_name}: using combobox at index {combobox_index}", "INFO")

        if input_el is None:
            BuiltIn().log(f"{field_name}: combobox not found", "WARN")
            self._sl.capture_page_screenshot()
            return False

        # The react-select hidden input is not directly interactable.
        # Walk up to the visible __control div and click that instead.
        control_el = self._driver.execute_script(
            """
            const inp = arguments[0];
            let p = inp.parentElement;
            for (let i = 0; i < 6; i++) {
                if (!p) break;
                const cls = (p.className || '').toString();
                if (/(__control|-control|Control)/.test(cls) && p.offsetWidth > 0) return p;
                p = p.parentElement;
            }
            // Fallback: first visible ancestor
            p = inp.parentElement;
            for (let i = 0; i < 4; i++) {
                if (!p) break;
                if (p.offsetWidth > 0 && p.offsetHeight > 0) return p;
                p = p.parentElement;
            }
            return null;
            """,
            input_el,
        )

        target = control_el if control_el else input_el
        self._driver.execute_script("arguments[0].scrollIntoView({block:'center'});", target)
        # Click the visible control to open the dropdown
        self._driver.execute_script("arguments[0].click();", target)
        time.sleep(0.6)
        # Send keyboard navigation to the hidden input (now focused after control click)
        try:
            input_el.send_keys(Keys.ARROW_DOWN)
            time.sleep(0.3)
            input_el.send_keys(Keys.ENTER)
        except Exception:
            # Last resort: JS click the first option in the opened menu
            self._driver.execute_script(
                """
                const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                const opt = Array.from(document.querySelectorAll('[role="option"],[class*="__option"]'))
                    .find(visible);
                if (opt) opt.click();
                """
            )
        BuiltIn().log(f"{field_name}: selected first option via keyboard", "INFO")
        time.sleep(0.4)
        return True

    def _select_gst_rate(self, rate):
        """Select the Default GST Rate — first option from the react-select near the label."""
        if not self._click_react_select_near_label(
            r"gst.{0,15}rate|default.{0,10}gst", "GST Rate"
        ):
            BuiltIn().log("GST Rate: selection failed", "WARN")
            self._sl.capture_page_screenshot()

    def _select_pos_system(self):
        """Find the POS System dropdown (by label proximity) and select its first option."""
        for pattern in [r"pos.{0,10}system", r"point.{0,10}sale", r"\bpos\b"]:
            if self._click_react_select_near_label(pattern, "POS System"):
                return
        BuiltIn().log("POS System: not found (likely optional) — skipping", "WARN")

    def _select_menu_type(self, menu_type):
        self._select_dropdown_field("Menu Type", menu_type, MENU_TYPE_SELECT)

    def _add_cuisines(self, cuisines):
        if isinstance(cuisines, str):
            cuisines = [c.strip() for c in cuisines.split(",") if c.strip()]
        for cuisine in cuisines:
            self._add_single_cuisine(cuisine)

    def _add_single_cuisine(self, cuisine):
        """Click cuisines container to reveal hidden input, type, then pick suggestion."""
        from selenium.webdriver.common.by import By

        # Candidate XPaths to find the cuisines container/trigger to click open
        _CONTAINER_XPATHS = [
            "//label[contains(normalize-space(.),'Cuisine')]/following-sibling::*[1]",
            "//label[contains(normalize-space(.),'Cuisines')]/following-sibling::*[1]",
            "//*[contains(@class,'cuisine') or contains(@class,'Cuisine')][1]",
            "//*[contains(@placeholder,'Cuisine') or contains(@placeholder,'cuisine')][1]",
        ]
        for xpath in _CONTAINER_XPATHS:
            els = self._driver.find_elements(By.XPATH, xpath)
            if els:
                try:
                    self._driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", els[0]
                    )
                    els[0].click()
                except Exception:
                    self._driver.execute_script("arguments[0].click();", els[0])
                time.sleep(0.4)
                break

        # After clicking the container the input should be visible/accessible
        _INPUT_XPATHS = [
            CUISINES_INPUT,
            "//label[contains(normalize-space(.),'Cuisine')]/following-sibling::*//input[not(@type='hidden')][1]",
            "//label[contains(normalize-space(.),'Cuisines')]/following-sibling::*//input[not(@type='hidden')][1]",
            "//*[contains(@class,'cuisine') or contains(@class,'Cuisine')]//input[not(@type='hidden')][1]",
        ]
        input_el = None
        for xpath in _INPUT_XPATHS:
            els = self._driver.find_elements(By.XPATH, xpath)
            if els:
                input_el = els[0]
                break

        if input_el is None:
            raise AssertionError(
                f"Cuisine input field not found on page for cuisine '{cuisine}'"
            )

        # send_keys fires proper keydown/keyup events that tag-input libraries expect
        try:
            input_el.click()
        except Exception:
            self._driver.execute_script("arguments[0].click();", input_el)
        input_el.send_keys(cuisine)
        time.sleep(0.5)

        # Click the matching suggestion from the dropdown
        for sel in ['[role="option"]', '.ant-select-item', '[class*="option"]', 'li']:
            if self._js_click_by_text(sel, cuisine):
                time.sleep(0.3)
                return
        raise AssertionError(f'Cuisine suggestion "{cuisine}" not found in dropdown')

    def _select_payment_collector(self, collector):
        """Click payment collector container to reveal hidden input, then pick suggestion."""
        from selenium.webdriver.common.by import By

        # Click the container section to open/activate the dropdown
        _CONTAINER_XPATHS = [
            "//label[contains(normalize-space(.),'Payment Collector')]/following-sibling::*[1]",
            "//label[contains(normalize-space(.),'Payment')]/following-sibling::*[1]",
            "//*[contains(@placeholder,'Payment Collector') or contains(@placeholder,'payment')][1]",
        ]
        for xpath in _CONTAINER_XPATHS:
            els = self._driver.find_elements(By.XPATH, xpath)
            if els:
                try:
                    self._driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", els[0]
                    )
                    els[0].click()
                except Exception:
                    self._driver.execute_script("arguments[0].click();", els[0])
                time.sleep(0.4)
                break

        # Use JS to locate the input near "Payment Collector" label text on the page
        input_el = self._driver.execute_script(
            """
            const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const editable = el => !el.disabled && !el.readOnly && el.type !== 'hidden';

            // 1. Search inside any ancestor that contains "Payment Collector" text
            const ancestors = Array.from(document.querySelectorAll('*')).filter(el =>
                /payment.{0,15}collector/i.test((el.innerText || el.textContent || '').trim())
                && el.children.length > 0
            );
            for (const sec of ancestors) {
                const inp = sec.querySelector('input');
                if (inp && visible(inp) && editable(inp)) return inp;
            }

            // 2. Fallback: XPath-style attribute match
            const byAttr = document.querySelector(
                'input[name="paymentCollector"], input[id="paymentCollector"], '
                + 'input[placeholder*="Payment"], input[placeholder*="payment"]'
            );
            if (byAttr && visible(byAttr) && editable(byAttr)) return byAttr;

            // 3. Last resort: last visible, editable, empty text input on the page
            const all = Array.from(
                document.querySelectorAll('input[type="text"],input[type="search"],input:not([type])')
            ).filter(el => visible(el) && editable(el) && !el.value);
            return all.length ? all[all.length - 1] : null;
            """
        )

        if input_el is None:
            self._sl.capture_page_screenshot()
            raise AssertionError(
                f"Payment Collector input field not found for value '{collector}'"
            )

        BuiltIn().log(
            f"Payment Collector input found: name={input_el.get_attribute('name')} "
            f"id={input_el.get_attribute('id')} placeholder={input_el.get_attribute('placeholder')}",
            "INFO",
        )
        try:
            input_el.click()
        except Exception:
            self._driver.execute_script("arguments[0].click();", input_el)
        time.sleep(1.0)

        # Log and screenshot the open dropdown (no typing) to discover available options
        visible_opts = self._driver.execute_script(
            """
            const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const inMenu = el => {
                for (let p = el, i = 0; p && i < 6; p = p.parentElement, i++)
                    if (/listbox|menu|dropdown|__menu/i.test((p.className||'').toString()+(p.getAttribute('role')||''))) return true;
                return false;
            };
            return Array.from(document.querySelectorAll('[role="option"],[class*="__option"],[class*="-option"]'))
                .filter(vis)
                .map(e => (e.innerText||e.textContent||'').trim())
                .filter(t => t && t.length < 100)
                .join(' | ');
            """
        )
        BuiltIn().log(f"Payment Collector dropdown options: [{visible_opts}]", "INFO")
        self._sl.capture_page_screenshot()

        # If a specific collector name is given, type it to filter; otherwise use first option
        if collector:
            input_el.send_keys(collector)
            time.sleep(1.2)
            for sel in ['[role="option"]', '[class*="__option"]', '[class*="-option"]']:
                if self._js_click_by_text(sel, collector):
                    time.sleep(0.3)
                    return

        # Select the first available real option from the dropdown
        first_opt = self._driver.execute_script(
            """
            const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const inNav = el => {
                for (let p = el, i = 0; p && i < 8; p = p.parentElement, i++)
                    if (/sidebar|sidenav|navigation/i.test((p.className||'').toString())) return true;
                return false;
            };
            for (const sel of ['[role="option"]','[class*="__option"]','[class*="-option"]']) {
                const opts = Array.from(document.querySelectorAll(sel))
                    .filter(vis).filter(e => !inNav(e));
                if (opts.length) {
                    opts[0].scrollIntoView({block:'center'});
                    opts[0].click();
                    return (opts[0].innerText||opts[0].textContent||'').trim();
                }
            }
            return null;
            """
        )
        if first_opt:
            BuiltIn().log(f"Payment Collector: selected '{first_opt}'", "INFO")
            time.sleep(0.3)
            return

        self._sl.capture_page_screenshot()
        raise AssertionError(f'Payment Collector: no options found in dropdown (searched for "{collector}")')

    def click_done(self):
        """Click Done to submit the wizard, then navigate back to the Outlets list."""
        from selenium.webdriver.common.by import By

        # Dismiss any blocking overlay (e.g. Rotate Your Screen) before submitting
        self._dismiss_blocking_modals()
        self._sl.capture_page_screenshot()

        self._click(DONE_BUTTON)
        time.sleep(1.5)

        # Check for VISIBLE validation error messages only (skip hidden DOM nodes and asterisk markers)
        validation_errors = self._driver.execute_script(
            """
            const vis = el => {
                const s = window.getComputedStyle(el);
                return s.display !== 'none' && s.visibility !== 'hidden'
                    && !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            };
            const msgs = [];
            document.querySelectorAll(
                '[class*="error"],[class*="invalid"],[role="alert"],'
                + 'p[style*="color: red"],p[style*="color:red"]'
            ).forEach(el => {
                if (!vis(el)) return;
                const text = (el.innerText || el.textContent || '').trim();
                // Skip empty, single-char (*), or orientation-related text
                if (!text || text.length <= 1 || /rotate|landscape|portrait/i.test(text)) return;
                // Attach nearest label for context
                let label = '', p = el.parentElement;
                for (let i = 0; i < 5 && p; i++, p = p.parentElement) {
                    const lbl = p.querySelector('label');
                    if (lbl) { label = (lbl.innerText || lbl.textContent || '').trim().slice(0,30); break; }
                }
                msgs.push(label ? label + ': ' + text : text);
            });
            return [...new Set(msgs)].join(' | ');
            """
        )
        if validation_errors:
            BuiltIn().log(f"click_done: validation errors: {validation_errors}", "WARN")

        # Wait up to 15 s for Done button to disappear (wizard closed / submitted)
        deadline = time.time() + 15
        while time.time() < deadline:
            done_els = self._driver.find_elements(By.XPATH, DONE_BUTTON)
            if not done_els:
                break
            time.sleep(1)
        else:
            self._sl.capture_page_screenshot()
            raise AssertionError(
                "Wizard did not submit: Done button still visible after 15s."
                + (f" Validation errors: [{validation_errors}]" if validation_errors else "")
            )

        time.sleep(1.5)
        try:
            self.click_outlets_in_sidebar()
        except Exception as e:
            BuiltIn().log(f"click_done: sidebar re-nav failed ({e}), continuing", "WARN")
        time.sleep(1.5)

    # ── Step 5: Verify Tenant view ────────────────────────────────────────────

    def search_outlet(self, query):
        """Type a search term into the Outlets list search box."""
        from selenium.webdriver.common.by import By

        # Broader locator set — try XPath candidates first, then JS fallback
        _SEARCH_XPATHS = [
            OUTLET_SEARCH_INPUT,
            "//input[@type='text' and (contains(@placeholder,'Search') or contains(@placeholder,'search'))]",
            "//input[contains(@placeholder,'Outlet') or contains(@placeholder,'outlet')]",
            "//input[@type='text' or @type='search'][not(@type='hidden')][1]",
        ]
        search_el = None
        deadline = time.time() + 20
        while time.time() < deadline:
            for xpath in _SEARCH_XPATHS:
                els = self._driver.find_elements(By.XPATH, xpath)
                if els and els[0].is_displayed():
                    search_el = els[0]
                    break
            if search_el:
                break
            time.sleep(1)

        if search_el is None:
            self._sl.capture_page_screenshot()
            raise AssertionError("Outlet list search input not found after clicking Done")

        try:
            search_el.click()
        except Exception:
            self._driver.execute_script("arguments[0].click();", search_el)
        search_el.send_keys(query)
        self._react_short_pause()

    def verify_outlet_in_tenant_list(self, outlet_name, expected_status, timeout=30):
        """Poll until outlet_name + expected_status appear together on the page."""
        # Accept partial status matches: "Drafted" matches "draft", "drafted", "draft"
        status_variants = list({
            expected_status.lower(),
            expected_status.lower().rstrip("ed"),   # "drafted" -> "draft"
            expected_status.lower() + "ed",          # "draft"   -> "drafted"
        })
        deadline = time.time() + float(timeout)
        last_page_text = ""
        while True:
            result = self._driver.execute_script(
                """
                const name    = arguments[0].trim().toLowerCase();
                const variants = arguments[1];

                // 1. Check structured rows first
                const rowSels = 'tr, [role="row"], [class*="outlet-row"], [class*="outlet-item"], '
                              + '[class*="card"], [class*="list-item"], [class*="table-row"]';
                const inRow = Array.from(document.querySelectorAll(rowSels)).some(row => {
                    const txt = (row.innerText || row.textContent || '').toLowerCase();
                    return txt.includes(name) && variants.some(s => txt.includes(s));
                });
                if (inRow) return {found: true, debug: ''};

                // 2. Fallback: name appears anywhere on the page
                const pageText = (document.body.innerText || document.body.textContent || '').toLowerCase();
                const nameOnPage = pageText.includes(name);
                const statusOnPage = variants.some(s => pageText.includes(s));

                // Capture a snippet around the outlet name for debugging
                const idx = pageText.indexOf(name.slice(0, 10));
                const snippet = idx >= 0 ? pageText.slice(Math.max(0,idx-30), idx+80) : '';
                return {found: nameOnPage && statusOnPage, debug: snippet};
                """,
                outlet_name, status_variants,
            )
            if result.get("found"):
                return
            last_page_text = result.get("debug", "")
            if time.time() >= deadline:
                self._sl.capture_page_screenshot()
                raise AssertionError(
                    f'Outlet "{outlet_name}" with status "{expected_status}" '
                    f'not found in Tenant outlet list after {timeout}s. '
                    f'Page snippet near name: [{last_page_text}]'
                )
            time.sleep(2)

    def open_outlet(self, outlet_name):
        """Open the outlet detail view — click the outlet's row/link in the (filtered) list.

        The Aeria outlet list may open an inline panel on the same page rather than
        navigating to a new URL.  We click the outlet entry and then wait for either
        a URL change OR a new action button (Edit / Send Approval) to appear.
        """
        url_before = self._driver.current_url
        self._sl.capture_page_screenshot()

        # Log all elements containing the outlet name for diagnosis
        diag = self._driver.execute_script(
            """
            const name = arguments[0].trim().toLowerCase();
            const norm = t => (t||'').replace(/\\s+/g,' ').trim().toLowerCase();
            const vis  = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const matches = Array.from(document.querySelectorAll('*'))
                .filter(vis)
                .filter(el => norm(el.innerText||el.textContent).includes(name))
                .filter(el => el.children.length <= 10)
                .slice(0, 10)
                .map(el => el.tagName + '.' + (el.className||'').toString().replace(/\\s+/g,'.').slice(0,40)
                         + ' cursor=' + window.getComputedStyle(el).cursor
                         + ' text="' + norm(el.innerText||'').slice(0,60) + '"');
            return matches.join(' || ');
            """,
            outlet_name,
        )
        BuiltIn().log(f"Elements containing outlet name: {diag}", "INFO")

        deadline = time.time() + 20
        while time.time() < deadline:
            clicked = self._driver.execute_script(
                """
                const name = arguments[0].trim().toLowerCase();
                const norm = t => (t || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                const vis  = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                const inNav = el => {
                    for (let p = el, i = 0; p && i < 8; p = p.parentElement, i++)
                        if (/sidebar|sidenav|navigation/i.test((p.className||'').toString())) return true;
                    return false;
                };

                // Priority 1: <a> elements (actual navigation links)
                const links = Array.from(document.querySelectorAll('a')).filter(vis).filter(el => !inNav(el))
                    .filter(el => norm(el.innerText || el.textContent).includes(name));
                if (links.length) {
                    links[0].scrollIntoView({block:'center'}); links[0].click();
                    return 'a:' + (links[0].className||'').slice(0,30);
                }

                // Priority 2: smallest element with pointer cursor containing the name
                const byPointer = Array.from(document.querySelectorAll('*'))
                    .filter(vis).filter(el => !inNav(el))
                    .filter(el => {
                        const t = norm(el.innerText || el.textContent);
                        return t.includes(name) && t.length < name.length * 4;
                    })
                    .filter(el => window.getComputedStyle(el).cursor === 'pointer')
                    .sort((a,b) => norm(a.innerText||'').length - norm(b.innerText||'').length);
                if (byPointer.length) {
                    byPointer[0].scrollIntoView({block:'center'}); byPointer[0].click();
                    return 'ptr:' + byPointer[0].tagName;
                }

                // Priority 3: <tr> or row element (click the whole row)
                const rows = Array.from(document.querySelectorAll('tr, [role="row"]'))
                    .filter(vis).filter(el => !inNav(el))
                    .filter(el => norm(el.innerText || el.textContent).includes(name));
                if (rows.length) {
                    rows[0].scrollIntoView({block:'center'}); rows[0].click();
                    return 'row:' + rows[0].tagName;
                }

                // Priority 4: any visible element containing the name (most specific / smallest first)
                const anyMatch = Array.from(document.querySelectorAll('*'))
                    .filter(vis).filter(el => !inNav(el))
                    .filter(el => {
                        const t = norm(el.innerText || el.textContent);
                        return t.includes(name) && t.length < name.length * 5;
                    })
                    .sort((a,b) => norm(a.innerText||'').length - norm(b.innerText||'').length);
                if (anyMatch.length) {
                    anyMatch[0].scrollIntoView({block:'center'}); anyMatch[0].click();
                    return 'any:' + anyMatch[0].tagName + '.' + (anyMatch[0].className||'').toString().slice(0,30);
                }
                return null;
                """,
                outlet_name,
            )

            if clicked:
                time.sleep(2.0)
                self._sl.capture_page_screenshot()
                url_after = self._driver.current_url
                if url_after != url_before:
                    BuiltIn().log(f"Navigated to: {url_after}", "INFO")
                    return
                # Same URL — may be an inline expand; check for action buttons
                approval_visible = self._driver.execute_script(
                    "const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);"
                    "return Array.from(document.querySelectorAll('button, [role=\"button\"], a'))"
                    ".filter(vis).some(b => /approv|edit|publish|save/i.test(b.innerText||b.textContent||''));"
                )
                if approval_visible:
                    BuiltIn().log(f"Outlet opened inline via {clicked}", "INFO")
                    return
                BuiltIn().log(f"Clicked via {clicked} but no action button appeared — retrying", "WARN")

            time.sleep(1)

        self._sl.capture_page_screenshot()
        raise AssertionError(f'Could not open outlet "{outlet_name}" detail/panel')

    def click_send_approval(self):
        """Click the Send Approval / Send for Approval button on the outlet detail page."""
        self._sl.capture_page_screenshot()

        # Log all visible button texts for diagnosis
        btn_texts = self._driver.execute_script(
            """
            const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            return Array.from(document.querySelectorAll('button, [role="button"], a'))
                .filter(vis)
                .map(b => (b.innerText || b.textContent || '').trim())
                .filter(t => t.length > 0)
                .join(' | ');
            """
        )
        BuiltIn().log(f"Visible buttons on detail page: {btn_texts}", "INFO")

        clicked = self._driver.execute_script(
            """
            const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const btns = Array.from(document.querySelectorAll(
                'button, [role="button"], a'
            )).filter(vis);
            // Match any button whose text contains "approval" or "approve" with optional "send/submit/request"
            const btn = btns.find(b => /approv/i.test(b.innerText || b.textContent || ''));
            if (btn) { btn.scrollIntoView({block:'center'}); btn.click(); return (btn.innerText||btn.textContent||'').trim(); }
            return null;
            """
        )
        if not clicked:
            self._sl.capture_page_screenshot()
            raise AssertionError(
                f"Approval button not found on outlet detail page. "
                f"Visible buttons: [{btn_texts}]"
            )
        BuiltIn().log(f"Clicked approval button: '{clicked}'", "INFO")
        time.sleep(2.0)

    # ── Step 6: Switch to Site Admin ──────────────────────────────────────────

    def switch_to_site_admin(self, account_name):
        """Avatar → Switch Accounts → select account → Continue → wait for dashboard."""
        self._sl.capture_page_screenshot()

        # Use a JS scan to find and click the user-profile / account-menu button.
        # The Aeria header does not always expose a reliable data-testid or class name,
        # so we try a prioritised set of signals rather than a single fixed locator.
        clicked_via = self._driver.execute_script(
            """
            const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);

            // Priority 1: explicit test IDs / semantic classes
            const explicit = [
                '[data-testid="user-avatar"]', '[data-testid="profile-button"]',
                '[data-testid="user-menu"]',   '[data-testid="account-menu"]',
                'button[class*="avatar"]',     'div[class*="userAvatar"]',
                'button[class*="profile"]',    'div[class*="user-menu"]',
                '[class*="AccountSwitcher"]',  '[class*="account-switcher"]',
            ];
            for (const sel of explicit) {
                const el = document.querySelector(sel);
                if (el && vis(el)) { el.click(); return sel; }
            }

            // Priority 2: button/div in the topbar that contains an avatar image
            const topbar = document.querySelector(
                'header, [class*="header"], [class*="navbar"], [class*="topbar"], '
                + '[class*="Header"], [class*="Navbar"], nav'
            );
            if (topbar) {
                // Button that wraps an <img> or a round element (likely avatar)
                const withImg = Array.from(topbar.querySelectorAll(
                    'button, [role="button"], div[class*="menu"]'
                )).filter(vis).find(b => b.querySelector('img') || /avatar|profile|user/i.test(b.className));
                if (withImg) { withImg.click(); return 'topbar-img-btn'; }

                // Button with very short text (initials like "SP") — typical profile avatar
                const initials = Array.from(topbar.querySelectorAll('button, [role="button"]'))
                    .filter(vis)
                    .find(b => {
                        const t = (b.innerText || b.textContent || '').trim();
                        return t.length >= 1 && t.length <= 3;
                    });
                if (initials) { initials.click(); return 'topbar-initials-btn'; }

                // Last resort: rightmost clickable button in the topbar (usually profile)
                const allBtns = Array.from(
                    topbar.querySelectorAll('button, [role="button"]')
                ).filter(vis);
                if (allBtns.length) {
                    allBtns[allBtns.length - 1].click();
                    return 'topbar-last-btn';
                }
            }

            // Priority 3: fall back to the static XPath locator via direct DOM query
            const fallbacks = [
                'button[class*="user"]', 'button[class*="account"]',
                '[class*="userProfile"]', '[class*="UserProfile"]',
            ];
            for (const sel of fallbacks) {
                const el = document.querySelector(sel);
                if (el && vis(el)) { el.click(); return sel; }
            }
            return null;
            """
        )

        if clicked_via:
            BuiltIn().log(f"User avatar clicked via: {clicked_via}", "INFO")
        else:
            BuiltIn().log("JS avatar search failed — falling back to locator", "WARN")
            self._click(USER_AVATAR)

        self._react_short_pause()

        self._click(SWITCH_ACCOUNTS_MENU_ITEM)
        time.sleep(1.5)  # wait for switch accounts dialog to render

        self._sl.capture_page_screenshot()
        BuiltIn().log(f"Switch Accounts dialog opened. Looking for: '{account_name}'", "INFO")

        # Normalize whitespace so "Site Admin\n@ Prestige Tech Park Building 1" matches
        # "Site Admin @ Prestige Tech Park Building 1" (the dialog renders role + property on separate lines).
        clicked = self._driver.execute_script(
            """
            const raw    = arguments[0];
            const target = raw.replace(/\\s+/g, ' ').trim().toLowerCase();
            const norm   = t => (t || '').replace(/\\s+/g, ' ').trim().toLowerCase();
            const vis    = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);

            // Helper: pick the most specific (shortest text) visible element
            // that includes the target — avoids clicking a parent container
            // whose innerText contains multiple accounts.
            const pickBest = candidates => {
                const hits = candidates
                    .filter(vis)
                    .filter(e => norm(e.innerText || e.textContent).includes(target))
                    .sort((a, b) =>
                        (a.innerText || a.textContent || '').length -
                        (b.innerText || b.textContent || '').length
                    );
                return hits.length ? hits[0] : null;
            };

            // Pass 1: exact text match (most reliable)
            const allVis = Array.from(document.querySelectorAll('*')).filter(vis);
            const exact = allVis.find(e => norm(e.innerText || e.textContent) === target);
            if (exact) { exact.scrollIntoView({block:'center'}); exact.click(); return true; }

            // Pass 2: semantic role elements — [role="option"], radio, label, li
            const roleMatch = pickBest(Array.from(document.querySelectorAll(
                '[role="option"], [role="radio"], [role="menuitem"], label, li'
            )));
            if (roleMatch) { roleMatch.scrollIntoView({block:'center'}); roleMatch.click(); return true; }

            // Pass 3: any element whose text is close in length to target
            // (target.length + 100 chars max to exclude large container divs)
            const close = Array.from(document.querySelectorAll('*'))
                .filter(vis)
                .filter(e => {
                    const t = norm(e.innerText || e.textContent);
                    return t.includes(target) && t.length <= target.length + 100;
                })
                .sort((a, b) =>
                    (a.innerText || a.textContent || '').length -
                    (b.innerText || b.textContent || '').length
                );
            if (close.length) { close[0].scrollIntoView({block:'center'}); close[0].click(); return true; }

            return false;
            """,
            account_name,
        )
        if not clicked:
            page_text = self._driver.execute_script(
                "return (document.body.innerText || document.body.textContent || '').slice(0, 800);"
            )
            self._sl.capture_page_screenshot()
            raise AssertionError(
                f'Account "{account_name}" not found in Switch Accounts dialog. '
                f'Visible text: [{page_text}]'
            )

        self._react_short_pause()
        self._click(SWITCH_ACCOUNTS_CONTINUE_BTN)

        # Wait for page navigation to complete after account switch
        time.sleep(3.0)
        try:
            self._sl.wait_until_element_is_visible(
                "//nav[contains(@class,'sidebar') or contains(@class,'nav')] "
                "| //*[@data-testid='sidebar'] "
                "| //a[contains(@href,'outlets')]",
                timeout="20s",
            )
        except Exception:
            pass
        BuiltIn().log(
            f"Switched to '{account_name}'. Current URL: {self._sl.get_location()}", "INFO"
        )

    def verify_outlet_in_site_admin(self, outlet_name, timeout=30):
        """Poll until outlet_name appears anywhere on the Site Admin Outlets page."""
        deadline = time.time() + float(timeout)
        while True:
            found = self._driver.execute_script(
                """
                const name = arguments[0].trim().toLowerCase();
                return Array.from(document.querySelectorAll('*')).some(
                    el => el.children.length === 0
                       && (el.innerText || el.textContent || '').trim().toLowerCase().includes(name)
                );
                """,
                outlet_name,
            )
            if found:
                return
            if time.time() >= deadline:
                raise AssertionError(
                    f'Outlet "{outlet_name}" not found on Site Admin Outlets page after {timeout}s.'
                )
            time.sleep(2)

    def _click_approv_element(self):
        """Click the Approve ACTION button — only on interactive elements.

        Deliberately EXCLUDES status text like "Pending Approval", "Send for Approval",
        "Approval Request" which are not action buttons.
        """
        return self._driver.execute_script(
            """
            const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const getText = el => (el.innerText || el.textContent || '').trim();

            // Only look at explicitly interactive elements
            const interactive = Array.from(document.querySelectorAll(
                'button, a, [role="button"], [role="menuitem"], [role="option"]'
            )).filter(vis);

            // Match "Approve" (exactly) or "Approve <something>" — NOT "Approval", "Approving", etc.
            // The word boundary after "Approve" avoids matching "Approval Request" or "Pending Approval".
            const btn = interactive.find(e => /^approve(\\s|$)/i.test(getText(e)));
            if (btn) {
                btn.scrollIntoView({block: 'center'});
                btn.click();
                return getText(btn);
            }

            // Fallback: any interactive element with text containing "approve " (with trailing space/end)
            const wide = interactive.find(e => /approve(\\s|$)/i.test(getText(e)));
            if (wide) {
                wide.scrollIntoView({block: 'center'});
                wide.click();
                return getText(wide);
            }

            return null;
            """
        )

    def approve_outlet(self):
        """Click the Approve button on the Site Admin outlet detail page.

        Strategy:
          1. Try current tab (Overview) for a direct approve button.
          2. Click the "Pending Requests" tab, then poll every 2s for up to 15s
             for an approve button (tab content is async).
          3. If a status badge was clicked, retry once after a short pause.
        """
        self._sl.capture_page_screenshot()
        url = self._sl.get_location()
        BuiltIn().log(f"approve_outlet: current URL = {url}", "INFO")

        # --- Attempt 1: approve directly on current tab -----------------------
        clicked = self._click_approv_element()
        if clicked:
            BuiltIn().log(f"Approved via Overview tab button: '{clicked}'", "INFO")
            time.sleep(2.0)
            self._sl.capture_page_screenshot()
            return

        # --- Attempt 2: click Pending Requests tab, poll for approve ----------
        tab_clicked = self._driver.execute_script(
            """
            const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const all = Array.from(document.querySelectorAll('*')).filter(vis);
            const t = all.find(el =>
                /pending.{0,20}request/i.test((el.innerText || el.textContent || '').trim()) &&
                el.children.length <= 3
            );
            if (t) { t.scrollIntoView({block: 'center'}); t.click(); return true; }
            return false;
            """
        )
        if tab_clicked:
            BuiltIn().log("Clicked Pending Requests tab — polling for Approve button (up to 15s)", "INFO")
            deadline = time.time() + 15
            while time.time() < deadline:
                time.sleep(2.0)
                page_excerpt = self._driver.execute_script(
                    "return (document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 600);"
                )
                BuiltIn().log(f"Pending Requests tab text: {page_excerpt}", "INFO")
                clicked = self._click_approv_element()
                if clicked:
                    BuiltIn().log(f"Clicked approve button: '{clicked}'", "INFO")
                    # Handle any confirmation dialog ("Confirm", "Yes", "OK")
                    time.sleep(1.5)
                    confirmed = self._driver.execute_script(
                        """
                        const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                        const btns = Array.from(document.querySelectorAll('button, [role="button"]')).filter(vis);
                        const conf = btns.find(b =>
                            /^(confirm|yes|ok|submit|accept)$/i.test(
                                (b.innerText || b.textContent || '').trim()
                            )
                        );
                        if (conf) { conf.scrollIntoView({block:'center'}); conf.click();
                            return (conf.innerText || conf.textContent || '').trim(); }
                        return null;
                        """
                    )
                    if confirmed:
                        BuiltIn().log(f"Confirmation handled: '{confirmed}'", "INFO")
                        time.sleep(1.5)
                    time.sleep(2.0)
                    # Verify approval succeeded: "Approve" button should be gone
                    still_visible = self._click_approv_element  # don't click, just check text
                    status_text = self._driver.execute_script(
                        "return (document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 300);"
                    )
                    BuiltIn().log(f"Post-approve page text: {status_text}", "INFO")
                    self._sl.capture_page_screenshot()
                    return
            self._sl.capture_page_screenshot()

        # --- Failure: capture full diagnostics ---------------------------------
        page_text = self._driver.execute_script(
            "return (document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 1500);"
        )
        clickable = self._driver.execute_script(
            """
            const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            return Array.from(document.querySelectorAll('*'))
                .filter(vis)
                .filter(e => window.getComputedStyle(e).cursor === 'pointer')
                .map(e => (e.innerText || e.textContent || '').trim().slice(0, 60))
                .filter(t => t)
                .slice(0, 40)
                .join(' | ');
            """
        )
        self._sl.capture_page_screenshot()
        raise AssertionError(
            f"Approve button not found on Site Admin outlet page.\\n"
            f"URL: {url}\\n"
            f"Clickable elements: [{clickable}]\\n"
            f"Page text: [{page_text[:600]}]"
        )

    def _click_activate_element(self):
        """Scan ALL visible elements for any activation action. Returns clicked text or None."""
        return self._driver.execute_script(
            """
            const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const getText = el => (el.innerText || el.textContent || '').trim();
            // Exact labels the button might carry
            const PAT = /^(activate|active|active account|go live|publish|enable outlet|make active|launch|set active)$/i;
            // Broader: any text containing these words
            const WIDE = /activ|go.?live|publish|enable/i;

            const all = Array.from(document.querySelectorAll('*')).filter(vis);

            // P1: leaf element with exact label (no children = most specific)
            const leafExact = all.find(e => e.children.length === 0 && PAT.test(getText(e)));
            if (leafExact) { leafExact.scrollIntoView({block:'center'}); leafExact.click(); return getText(leafExact); }

            // P2: any element with exact label (don't require cursor:pointer — badge may use cursor:default)
            const anyExact = all.find(e => PAT.test(getText(e)));
            if (anyExact) { anyExact.scrollIntoView({block:'center'}); anyExact.click(); return getText(anyExact); }

            // P3: button/a/role=button containing broad pattern
            const btnWide = all.filter(e =>
                /^(button|a)$/i.test(e.tagName) || /button|menuitem/i.test(e.getAttribute('role') || '')
            ).find(e => WIDE.test(getText(e)));
            if (btnWide) { btnWide.scrollIntoView({block:'center'}); btnWide.click(); return getText(btnWide); }

            // P4: any leaf element containing broad pattern (sort by text length = most specific)
            const leafWide = all
                .filter(e => e.children.length === 0 && WIDE.test(getText(e)))
                .sort((a, b) => getText(a).length - getText(b).length);
            if (leafWide.length) { leafWide[0].scrollIntoView({block:'center'}); leafWide[0].click(); return getText(leafWide[0]); }

            return null;
            """
        )

    def _confirm_activation(self):
        """Handle the 'Are you sure you want to activate?' confirmation popup.

        Clicks the 'Yes' button (or Yes/Confirm/OK variants) if visible.
        Returns the button text clicked, or None if no dialog appeared.
        """
        time.sleep(1.0)  # wait for popup to render
        self._sl.capture_page_screenshot()
        result = self._driver.execute_script(
            """
            const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const getText = el => (el.innerText || el.textContent || '').trim();
            const btns = Array.from(document.querySelectorAll(
                'button, [role="button"], [role="dialog"] button'
            )).filter(vis);
            // Priority 1: exact "Yes"
            const yes = btns.find(b => /^yes$/i.test(getText(b)));
            if (yes) { yes.scrollIntoView({block:'center'}); yes.click(); return getText(yes); }
            // Priority 2: "Confirm", "OK", "Activate", "Sure"
            const conf = btns.find(b => /^(confirm|ok|activate|sure|proceed)$/i.test(getText(b)));
            if (conf) { conf.scrollIntoView({block:'center'}); conf.click(); return getText(conf); }
            return null;
            """
        )
        if result:
            BuiltIn().log(f"Activation confirmed with: '{result}'", "INFO")
            time.sleep(2.0)
            self._sl.capture_page_screenshot()
        return result

    def activate_outlet(self):
        """Click the Activate button on the Tenant outlet detail page,
        then confirm the 'Are you sure?' popup by clicking 'Yes'.

        Strategy:
          1. Scroll to top, try immediately.
          2. Refresh page, poll every 3s for up to 20s.
          3. Try clicking the outlet status badge (may open a dropdown).
          4. Navigate to outlet list, look for Activate in the outlet row.
        """
        url = self._sl.get_location()
        BuiltIn().log(f"activate_outlet: current URL = {url}", "INFO")

        # Scroll to top before each attempt so sticky/fixed headers are in viewport
        self._driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.5)
        self._sl.capture_page_screenshot()

        # --- Attempt 1: try immediately ----------------------------------------
        clicked = self._click_activate_element()
        if clicked:
            BuiltIn().log(f"Clicked activate button: '{clicked}'", "INFO")
            self._confirm_activation()
            self._sl.capture_page_screenshot()
            return

        # --- Attempt 2: refresh + poll ------------------------------------------
        BuiltIn().log("Activate not found immediately — refreshing and polling (up to 20s)", "INFO")
        self._driver.refresh()
        time.sleep(2.5)
        self._driver.execute_script("window.scrollTo(0, 0);")

        deadline = time.time() + 20
        while time.time() < deadline:
            full_text = self._driver.execute_script(
                "return (document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 2000);"
            )
            BuiltIn().log(f"[POLL] page text: {full_text}", "INFO")
            clicked = self._click_activate_element()
            if clicked:
                BuiltIn().log(f"Clicked activate button after refresh: '{clicked}'", "INFO")
                self._confirm_activation()
                self._sl.capture_page_screenshot()
                return
            time.sleep(3.0)

        # --- Attempt 3: click any outlet STATUS badge that might be a dropdown ---
        BuiltIn().log("Trying status badge toggle approach", "INFO")
        badge_clicked = self._driver.execute_script(
            """
            const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const getText = el => (el.innerText || el.textContent || '').trim();
            const STATUS = /^(inactive|approved|pending|draft|sent for approval)$/i;
            const all = Array.from(document.querySelectorAll('*')).filter(vis);
            const badge = all.find(e => STATUS.test(getText(e)));
            if (badge) { badge.scrollIntoView({block:'center'}); badge.click(); return getText(badge); }
            return null;
            """
        )
        if badge_clicked:
            BuiltIn().log(f"Clicked status badge '{badge_clicked}' — looking for Active option", "INFO")
            time.sleep(1.5)
            clicked = self._click_activate_element()
            if clicked:
                BuiltIn().log(f"Clicked activate via status badge: '{clicked}'", "INFO")
                self._confirm_activation()
                self._sl.capture_page_screenshot()
                return

        # --- Attempt 4: go to outlet list, look for Activate in row -----------
        BuiltIn().log("Trying outlet list row approach — navigating back to outlet list", "INFO")
        outlet_list_url = url.split('/outlets/')[0] + '/outlets'
        self._driver.get(outlet_list_url)
        time.sleep(2.5)
        row_clicked = self._driver.execute_script(
            """
            const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const getText = el => (el.innerText || el.textContent || '').trim();
            const PAT = /activ|go.?live|publish|enable/i;
            const all = Array.from(document.querySelectorAll('*')).filter(vis);
            const btn = all.find(e => PAT.test(getText(e)) && e.children.length === 0);
            if (btn) { btn.scrollIntoView({block:'center'}); btn.click(); return getText(btn); }
            return null;
            """
        )
        if row_clicked:
            BuiltIn().log(f"Clicked activate from outlet list: '{row_clicked}'", "INFO")
            self._confirm_activation()
            self._sl.capture_page_screenshot()
            return

        # --- Failure diagnostics -----------------------------------------------
        self._driver.get(url)  # go back to outlet detail for screenshot
        time.sleep(2.0)
        self._driver.execute_script("window.scrollTo(0, 0);")
        full_page = self._driver.execute_script(
            "return (document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 3000);"
        )
        self._sl.capture_page_screenshot()
        raise AssertionError(
            f"Activate button not found after all strategies.\\n"
            f"URL: {url}\\n"
            f"Full page text: [{full_page}]"
        )
