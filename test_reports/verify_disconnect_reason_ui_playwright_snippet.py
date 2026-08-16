# Playwright snippet executed with mcp_browser_automation for the disconnect reason UI bug.
# It uses real preview backend data created by verify_disconnect_reason_backend.py, except
# the final connected-session edge uses a MOCKED status response because no real connected
# WhatsApp account is available in the preview environment.

import json

await page.set_viewport_size({"width": 1920, "height": 1080})
try:
    with open('/app/test_reports/disconnect_reason_backend_results.json', 'r', encoding='utf-8') as f:
        ids = json.load(f)['created_session_ids']

    print('Step 1: log in as admin')
    await page.goto('https://chat-platform-380.preview.emergentagent.com/login', wait_until='domcontentloaded')
    await page.get_by_test_id('login-email-input').fill('admin@wa.9x.design')
    await page.get_by_test_id('login-password-input').fill('admin123')
    await page.get_by_test_id('login-submit-button').click()
    await page.wait_for_url('**/app', timeout=15000)
    print('PASS: logged in')

    print('Step 2: legacy qr/no-reason session shows fallback disconnect banner')
    await page.goto(f"https://chat-platform-380.preview.emergentagent.com/app/sessions/{ids['legacy_qr_no_reason']}", wait_until='domcontentloaded')
    banner = page.get_by_test_id('disconnect-reason')
    await banner.wait_for(state='visible', timeout=20000)
    text = await banner.inner_text()
    required_fallback = [
        'why did this drop?',
        'Reason not recorded for this drop.',
        'Someone else linked this number',
        'You logged out from your phone',
        'WhatsApp blocked the number',
    ]
    missing = [s for s in required_fallback if s.lower() not in text.lower()]
    if missing:
        raise AssertionError(f'Fallback banner missing text: {missing}; text={text}')
    print('PASS: fallback banner text and 3 common causes are visible')

    print('Step 3: session with recorded node 440 label shows specific reason, not fallback')
    await page.goto(f"https://chat-platform-380.preview.emergentagent.com/app/sessions/{ids['qr_with_node_440_label']}", wait_until='domcontentloaded')
    banner = page.get_by_test_id('disconnect-reason')
    await banner.wait_for(state='visible', timeout=20000)
    text = await banner.inner_text()
    if 'Replaced by another device (someone else linked to this number)' not in text or 'Reason not recorded for this drop.' in text:
        raise AssertionError(f'Specific reason banner wrong: {text}')
    print('PASS: specific 440 reason is visible and fallback is not shown')

    print('Step 4: disconnect history empty state loads')
    await page.goto(f"https://chat-platform-380.preview.emergentagent.com/app/sessions/{ids['empty_history']}", wait_until='domcontentloaded')
    await page.get_by_test_id('toggle-disconnect-history').click()
    history = page.get_by_test_id('disconnect-history')
    await history.wait_for(state='visible', timeout=10000)
    await page.wait_for_timeout(1000)
    htext = await history.inner_text()
    if 'No disconnects recorded.' not in htext:
        raise AssertionError(f'Empty history text missing: {htext}')
    print('PASS: empty disconnect history message is visible')

    print('Step 5: recorded disconnect history loads in newest-first order')
    await page.goto(f"https://chat-platform-380.preview.emergentagent.com/app/sessions/{ids['history_order']}", wait_until='domcontentloaded')
    await page.get_by_test_id('toggle-disconnect-history').click()
    history = page.get_by_test_id('disconnect-history')
    await history.wait_for(state='visible', timeout=10000)
    await page.wait_for_timeout(1000)
    htext = await history.inner_text()
    idx_440 = htext.find('code 440')
    idx_401 = htext.find('code 401')
    if idx_440 < 0 or idx_401 < 0 or idx_440 > idx_401:
        raise AssertionError(f'History order wrong: {htext}')
    print('PASS: history UI shows code 440 before code 401')

    print('Step 6: MOCKED connected session status does not show disconnect banner')
    mock_id = 'mock-connected-ui-check'
    await page.route(f"**/api/sessions/{mock_id}/status", lambda route: route.fulfill(
        status=200,
        content_type='application/json',
        body=json.dumps({
            'id': mock_id,
            'user_id': 'qa',
            'name': 'QA Mock Connected',
            'phone': '916370505556',
            'status': 'connected',
            'api_key': 'qa',
            'created_at': '2026-07-01T00:00:00.000Z',
            'error': None,
            'error_code': None,
            'error_label': None,
            'last_disconnect_at': None,
            'last_disconnect_code': None,
            'last_disconnect_label': None,
            'last_disconnect_terminal': None,
        })
    ))
    await page.route(f"**/api/sessions/{mock_id}/disconnect-history?limit=20", lambda route: route.fulfill(
        status=200,
        content_type='application/json',
        body=json.dumps({'items': []})
    ))
    await page.goto(f"https://chat-platform-380.preview.emergentagent.com/app/sessions/{mock_id}", wait_until='domcontentloaded')
    await page.get_by_text('Connection is active', exact=True).wait_for(state='visible', timeout=10000)
    if await page.get_by_test_id('disconnect-reason').count() != 0:
        raise AssertionError('disconnect-reason banner rendered for connected status')
    print('PASS: MOCKED connected status hides disconnect banner')

    error_text = await page.evaluate("""() => {
    const errorElements = Array.from(document.querySelectorAll('.error, [class*="error"], [id*="error"]'));
    return errorElements.map(el => el.textContent).join(", ");
    }""")
    if error_text:
        print(f"Found error message: {error_text}")
    else:
        print("No error messages found on the page")
    print('UI_VERIFICATION_COMPLETE')
except Exception as e:
    print(f'UI_VERIFICATION_FAILED: {e}')
    raise