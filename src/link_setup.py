"""
link_setup.py
=============
One-time Plaid Link setup utility for obtaining access tokens.

This is NOT part of the regular sync pipeline. It's a standalone Flask server
that runs locally once per institution to obtain Plaid access tokens via the
Plaid Link UI.

Usage:
    1. Install dependencies: pip install -r requirements.txt
    2. Set up your .env file with PLAID_CLIENT_ID, PLAID_SECRET, PLAID_ENV
    3. Run this script: python link_setup.py
    4. Open http://localhost:5000 in your browser
    5. For each institution you want to connect, complete the Plaid Link flow
    6. Copy each printed access_token to your .env file as:
       PLAID_{ENV}_TOKEN_INSTITUTIONNAME=access-sandbox-...
    7. Stop the server when done (Ctrl+C)

After setup, the regular sync pipeline (main.py) uses these tokens to fetch
transactions without user interaction.
"""

import json
import logging
import os
from datetime import datetime

from flask import Flask, render_template_string, request, jsonify

from .core.config import PLAID_ENV
from .api import plaid_integration

# Configure logging for the setup process
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(name)-20s  %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)


# ─── Flask App ─────────────────────────────────────────────────────────────

app = Flask(__name__)


def _get_requested_profile():
    """Return the Plaid profile requested by query/body, or the default profile."""
    requested_name = None
    if request.method == 'GET':
        requested_name = request.args.get('profile')
    else:
        payload = request.get_json(silent=True) or {}
        requested_name = payload.get('profile')

    profiles = plaid_integration.get_plaid_profiles()
    if not profiles:
        return plaid_integration.get_default_plaid_profile()

    if not requested_name:
        return profiles[0]

    requested_name = requested_name.strip().upper()
    for profile in profiles:
        if profile.name.upper() == requested_name or profile.prefix.upper() == requested_name:
            return profile

    raise ValueError(f"Unknown Plaid profile: {requested_name!r}. "
                     f"Available: {[p.name for p in profiles]}")


def _find_profile_for_institution(institution_name: str):
    """
    Scan all configured Plaid profiles to find which one owns the given institution.

    Searches every profile's token prefix in the environment so the caller
    never needs to know which client ID / secret to use — it's derived
    automatically from where the access token lives.

    Args:
        institution_name: Raw institution string from the UI (e.g. 'fidelity', 'CHASE').

    Returns:
        Tuple of (PlaidProfile, env_key, access_token) for the matching profile,
        or (None, None, None) if no profile has a token for this institution.
    """
    profiles = plaid_integration.get_plaid_profiles()
    institution_upper = institution_name.strip().upper()

    for profile in profiles:
        env_key = f"{profile.token_prefix}{institution_upper}"
        token = os.environ.get(env_key)
        if token:
            logger.info(
                f"Auto-detected profile '{profile.name}' for institution "
                f"'{institution_upper}' via env key '{env_key}'."
            )
            return profile, env_key, token

    logger.warning(
        f"No access token found for institution '{institution_upper}' "
        f"in any configured profile. Checked prefixes: "
        f"{[p.token_prefix for p in profiles]}"
    )
    return None, None, None


# ─── HTML Template for Plaid Link UI ───────────────────────────────────────

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Finance Sync — Plaid Link Setup</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", "Oxygen", "Ubuntu", "Cantarell", "Fira Sans", "Droid Sans", "Helvetica Neue", sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
            color: #333;
        }
        .container {
            max-width: 600px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            padding: 40px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            color: #2c3e50;
            margin-top: 0;
        }
        .instructions {
            background: #ecf0f1;
            border-left: 4px solid #3498db;
            padding: 15px;
            margin: 20px 0;
            border-radius: 4px;
            font-size: 14px;
            line-height: 1.6;
        }
        .button {
            background: #3498db;
            color: white;
            border: none;
            padding: 12px 24px;
            font-size: 16px;
            border-radius: 4px;
            cursor: pointer;
            margin-top: 20px;
        }
        .button:hover {
            background: #2980b9;
        }
        .button:disabled {
            background: #95a5a6;
            cursor: not-allowed;
        }
        #status {
            margin-top: 20px;
            padding: 15px;
            border-radius: 4px;
            display: none;
            white-space: pre-line;
        }
        #status.loading {
            background: #e8f4f8;
            color: #2c3e50;
            display: block;
        }
        #status.success {
            background: #d4edda;
            color: #155724;
            display: block;
        }
        #status.error {
            background: #f8d7da;
            color: #721c24;
            display: block;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>💰 Finance Sync — Plaid Link Setup</h1>
        
        <div class="instructions">
            <strong>How this works:</strong><br>
            Select a mode below:<br>
            • <strong>New Connection:</strong> Link a new bank to generate an access token<br>
            • <strong>Update Existing:</strong> Update an existing connection (e.g., Fidelity, Robinhood) to extend history to 2 years and add investment support<br>
            • <strong>Update All:</strong> Update all existing connections at once
        </div>

        <div style="margin: 20px 0;">
            <label style="margin-right: 15px;">
                <input type="radio" name="mode" value="new" checked> New Connection
            </label>
            <label style="margin-right: 15px;">
                <input type="radio" name="mode" value="update"> Update Existing
            </label>
            <label>
                <input type="radio" name="mode" value="update_all"> Update All
            </label>
        </div>

        <!-- Profile selector — shown for new connections only -->
        <div id="profileSelect" style="margin: 15px 0;">
            <label for="profile" style="display: block; margin-bottom: 5px; font-weight: 600;">
                Plaid Profile (which credentials to use):
            </label>
            <select id="profile" style="padding: 8px; width: 220px; border: 1px solid #ddd; border-radius: 4px;">
                <option value="">Loading profiles…</option>
            </select>
            <div id="profileHint" style="font-size: 12px; color: #666; margin-top: 4px;"></div>
        </div>

        <!-- Institution name — shown for single-institution update only -->
        <div id="institutionSelect" style="margin: 15px 0; display: none;">
            <label for="institution" style="display: block; margin-bottom: 5px; font-weight: 600;">
                Institution name (from .env):
            </label>
            <input type="text" id="institution" placeholder="e.g., FIDELITY, ROBINHOOD, CHASE"
                   style="padding: 8px; width: 220px; border: 1px solid #ddd; border-radius: 4px; text-transform: uppercase;">
            <div style="font-size: 12px; color: #666; margin-top: 4px;">
                Profile is auto-detected from your environment variables.
            </div>
        </div>

        <button id="openLink" class="button">Open Plaid Link</button>
        
        <div id="status"></div>
    </div>

    <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
    <script>
        document.addEventListener('DOMContentLoaded', async function() {

            // ── Load profiles into dropdown ─────────────────────────────────────
            async function loadProfiles() {
                try {
                    const res = await fetch('/profiles');
                    const data = await res.json();
                    const select = document.getElementById('profile');
                    select.innerHTML = '';
                    if (!data.profiles || data.profiles.length === 0) {
                        select.innerHTML = '<option value="">No profiles configured</option>';
                        return;
                    }
                    data.profiles.forEach((p, i) => {
                        const opt = document.createElement('option');
                        opt.value = p.name;
                        opt.textContent = `${p.name}  (${p.prefix}_*)`;
                        if (i === 0) opt.selected = true;
                        select.appendChild(opt);
                    });
                    updateProfileHint();
                } catch (e) {
                    document.getElementById('profile').innerHTML =
                        '<option value="">Error loading profiles</option>';
                }
            }

            function updateProfileHint() {
                const select = document.getElementById('profile');
                const hint = document.getElementById('profileHint');
                const selected = select.options[select.selectedIndex];
                if (selected) {
                    hint.textContent =
                        `New tokens will be stored as ${selected.textContent.split('(')[1]?.replace(')','').trim() || '…'}INSTITUTIONNAME`;
                }
            }

            document.getElementById('profile').addEventListener('change', updateProfileHint);
            await loadProfiles();

            // ── Show/hide fields based on mode ──────────────────────────────────
            function updateFieldVisibility(mode) {
                document.getElementById('profileSelect').style.display =
                    mode === 'new' ? 'block' : 'none';
                document.getElementById('institutionSelect').style.display =
                    mode === 'update' ? 'block' : 'none';
            }

            document.querySelectorAll('input[name="mode"]').forEach(radio => {
                radio.addEventListener('change', (e) => updateFieldVisibility(e.target.value));
            });
            updateFieldVisibility('new');   // Initial state

            // ── Helper: wrap a Plaid handler in a Promise ───────────────────────
            function openPlaidPromise(token) {
                return new Promise((resolve) => {
                    const handler = Plaid.create({
                        token: token,
                        onSuccess: (public_token, metadata) => {
                            console.log('Plaid Link success:', metadata);
                            resolve({ status: 'success', metadata, public_token });
                        },
                        onExit: (err, metadata) => {
                            if (err) {
                                console.error('Plaid Link error:', err);
                                resolve({ status: 'error', error: err });
                            } else {
                                resolve({ status: 'exited' });
                            }
                        }
                    });
                    handler.open();
                });
            }

            // ── Main button handler ─────────────────────────────────────────────
            document.getElementById('openLink').addEventListener('click', async () => {
                try {
                    const mode = document.querySelector('input[name="mode"]:checked').value;

                    // ── Update All ──────────────────────────────────────────────
                    if (mode === 'update_all') {
                        showStatus('loading', 'Generating update tokens for all institutions across all profiles…');

                        const res = await fetch('/update_all_link_tokens', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                        });
                        const data = await res.json();

                        if (!data.success) {
                            showStatus('error', data.message || 'Failed to generate update tokens');
                            return;
                        }

                        showStatus('loading', `Generated ${data.successful}/${data.total} tokens. Starting updates…`);

                        let report = '';
                        for (const [label, token] of Object.entries(data.update_tokens)) {
                            if (String(token).startsWith('ERROR')) {
                                report += `❌ ${label}: token generation failed\n`;
                                continue;
                            }
                            showStatus('loading', `Opening Plaid for: ${label}…`);
                            const result = await openPlaidPromise(token);
                            if (result.status === 'success') {
                                report += `✅ ${label}: updated\n`;
                            } else if (result.status === 'exited') {
                                report += `⚠️ ${label}: skipped / closed\n`;
                            } else {
                                report += `❌ ${label}: Plaid error\n`;
                            }
                        }

                        showStatus('success', `All done!\n\n${report}`);
                        return;
                    }

                    // ── Update Single ───────────────────────────────────────────
                    if (mode === 'update') {
                        const institution = document.getElementById('institution').value.trim();
                        if (!institution) {
                            showStatus('error', 'Enter the institution name (e.g. FIDELITY)');
                            return;
                        }

                        showStatus('loading', `Looking up ${institution.toUpperCase()} across all profiles…`);
                        const res = await fetch('/update_link_token', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ institution }),
                        });
                        const data = await res.json();

                        if (!data.success || !data.link_token) {
                            showStatus('error', data.message || 'Failed to get update token');
                            return;
                        }

                        showStatus('loading',
                            `Opening Plaid for ${institution.toUpperCase()} (profile: ${data.profile})…`);
                        const result = await openPlaidPromise(data.link_token);

                        if (result.status === 'success') {
                            showStatus('success',
                                `✅ ${institution.toUpperCase()} updated successfully! ` +
                                `Your existing access token has been extended.`);
                        } else if (result.status === 'exited') {
                            showStatus('', '');
                        } else {
                            showStatus('error', 'Plaid Link encountered an error. Please try again.');
                        }
                        return;
                    }

                    // ── New Connection ──────────────────────────────────────────
                    const selectedProfile = document.getElementById('profile').value;
                    if (!selectedProfile) {
                        showStatus('error', 'No profile selected — check your environment configuration.');
                        return;
                    }

                    showStatus('loading', `Fetching link token for profile "${selectedProfile}"…`);
                    const res = await fetch(`/link_token?profile=${encodeURIComponent(selectedProfile)}`);
                    const data = await res.json();

                    if (!data.link_token) {
                        showStatus('error', data.error || 'No link token received from server');
                        return;
                    }

                    const result = await openPlaidPromise(data.link_token);

                    if (result.status === 'success') {
                        showStatus('loading', 'Exchanging public token…');
                        const exchRes = await fetch('/exchange', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                public_token: result.public_token,
                                profile: selectedProfile,
                            }),
                        });
                        const exchData = await exchRes.json();
                        if (exchData.success) {
                            showStatus('success', exchData.message);
                        } else {
                            showStatus('error', exchData.message || 'Token exchange failed');
                        }
                    } else if (result.status === 'exited') {
                        showStatus('', '');
                    } else {
                        showStatus('error', 'Plaid Link encountered an error. Please try again.');
                    }

                } catch (err) {
                    showStatus('error', 'Unexpected error: ' + err.message);
                }
            });

            function showStatus(type, message) {
                const el = document.getElementById('status');
                if (!type) { el.style.display = 'none'; return; }
                el.className = type;
                el.textContent = message;
            }
        });
    </script>
</body>
</html>
"""


# ─── Routes ───────────────────────────────────────────────────────────────

@app.route('/')
def home():
    """Serve the Plaid Link UI page."""
    return render_template_string(HTML_TEMPLATE)


@app.route('/link_token', methods=['GET'])
def get_link_token():
    """
    Generate and return a fresh Plaid Link token.

    Called by the frontend when the user clicks "Open Plaid Link".
    """
    try:
        profile = _get_requested_profile()
        link_token = plaid_integration.create_link_token(profile=profile)
        return jsonify({'link_token': link_token})
    except Exception as e:
        logger.exception("Failed to create link token")
        return jsonify({'error': str(e)}), 500


@app.route('/exchange', methods=['POST'])
def exchange_public_token():
    """
    Exchange a public token from Plaid Link for a long-lived access token.

    Called by the frontend after the user completes Link authentication.
    """
    try:
        data = request.get_json() or {}
        public_token = data.get('public_token')

        if not public_token:
            return jsonify({
                'success': False,
                'message': 'No public token provided'
            }), 400

        # Exchange public token for access token
        profile = _get_requested_profile()
        access_token = plaid_integration.item_public_token_exchange(public_token, profile)

        # Print the access token clearly to the terminal so the user can copy it
        print("\n" + "="*70)
        print("✓ SUCCESS — New access token obtained:")
        print("="*70)
        print(f"Access Token: {access_token}")
        print("-"*70)
        print("Copy this token and add it to your .env file as:")
        print(f"  {profile.token_prefix}<INSTITUTIONNAME>=<token>")
        print("where <INSTITUTIONNAME> is the name of the bank (e.g., CHASE, AMEX).")
        print("="*70 + "\n")

        return jsonify({
            'success': True,
            'message': f'Access token obtained for {profile.name}! Check the terminal for details.',
            'access_token': access_token,  # Also in JSON for reference
        })

    except Exception as e:
        logger.exception("Failed to exchange public token")
        return jsonify({
            'success': False,
            'message': f'Token exchange failed: {str(e)}'
        }), 500

@app.route('/profiles', methods=['GET'])
def get_profiles():
    """Return the list of configured Plaid profile names for the UI dropdown."""
    try:
        profiles = plaid_integration.get_plaid_profiles()
        return jsonify({
            'profiles': [{'name': p.name, 'prefix': p.prefix} for p in profiles]
        })
    except Exception as e:
        logger.exception("Failed to load profiles")
        return jsonify({'error': str(e)}), 500


@app.route('/update_all_link_tokens', methods=['POST'])
def generate_all_update_link_tokens():
    """
    Generate Plaid Link tokens in UPDATE mode for every institution across
    ALL configured profiles.

    Iterates every profile (PRIMARY, SECONDARY, …) and every access token
    within each profile so no institution is missed regardless of which
    client ID / secret it belongs to.
    """
    try:
        from plaid.model.link_token_create_request import LinkTokenCreateRequest
        from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
        from plaid.model.products import Products
        from plaid.model.country_code import CountryCode

        profiles = plaid_integration.get_plaid_profiles()
        if not profiles:
            return jsonify({
                'success': False,
                'message': 'No Plaid profiles configured.'
            }), 404

        update_tokens = {}   # institution_name → link_token (or ERROR string)
        total_found = 0

        for profile in profiles:
            # Collect all access tokens belonging to this profile
            profile_tokens = {
                key[len(profile.token_prefix):]: value
                for key, value in os.environ.items()
                if key.startswith(profile.token_prefix) and value
            }

            if not profile_tokens:
                logger.info(f"Profile '{profile.name}': no tokens found — skipping.")
                continue

            total_found += len(profile_tokens)
            client = plaid_integration.get_plaid_client(profile)
            logger.info(
                f"Profile '{profile.name}': generating update tokens for "
                f"{len(profile_tokens)} institution(s): {list(profile_tokens.keys())}"
            )

            for institution_name, existing_access_token in profile_tokens.items():
                label = f"{profile.name}/{institution_name}"
                try:
                    link_request = LinkTokenCreateRequest(
                        user=LinkTokenCreateRequestUser(client_user_id='finance_sync_user'),
                        client_name='Finance Sync',
                        language='en',
                        country_codes=[CountryCode('US')],
                        access_token=existing_access_token,
                        additional_consented_products=[Products('transactions')],
                        transactions={"days_requested": 730},
                        optional_products=[
                            Products('investments'),
                            Products('liabilities'),
                            Products('identity'),
                        ],
                    )
                    response = client.link_token_create(link_request)
                    token_val = (
                        response.get('link_token')
                        if isinstance(response, dict)
                        else response.link_token
                    )
                    update_tokens[label] = token_val
                    logger.info(f"Generated update token for {label}")

                except Exception as e:
                    logger.error(f"Failed to generate update token for {label}: {e}")
                    update_tokens[label] = f"ERROR: {str(e)}"

        if not update_tokens:
            return jsonify({
                'success': False,
                'message': 'No access tokens found across any configured profile.'
            }), 404

        successful_count = sum(
            1 for t in update_tokens.values() if not str(t).startswith('ERROR')
        )
        print(
            f"\n✓ Generated {successful_count}/{total_found} update link tokens "
            f"across {len(profiles)} profile(s)"
        )
        return jsonify({
            'success': True,
            'update_tokens': update_tokens,
            'total': total_found,
            'successful': successful_count,
        })

    except Exception as e:
        logger.exception("Failed to generate all update link tokens")
        return jsonify({
            'success': False,
            'message': f'Bulk update setup failed: {str(e)}'
        }), 500


@app.route('/update_link_token', methods=['POST'])
def generate_update_link_token():
    """
    Generate a Plaid Link token in UPDATE mode for a single existing institution.

    Auto-detects which Plaid profile (PRIMARY, SECONDARY, …) owns the institution
    by scanning every profile's token prefix in the environment. The caller only
    needs to supply the institution name — no manual profile selection required.
    """
    try:
        data = request.get_json() or {}
        institution_name = data.get('institution', '').strip()

        if not institution_name:
            return jsonify({
                'success': False,
                'message': 'Missing institution name.'
            }), 400

        # Auto-detect which profile owns this institution's access token.
        profile, env_key, existing_access_token = _find_profile_for_institution(institution_name)

        if not profile:
            all_profiles = plaid_integration.get_plaid_profiles()
            checked = [p.token_prefix + institution_name.upper() for p in all_profiles]
            return jsonify({
                'success': False,
                'message': (
                    f"No access token found for '{institution_name.upper()}' in any profile. "
                    f"Checked env keys: {checked}"
                )
            }), 404

        logger.info(
            f"Generating update token for {institution_name.upper()} "
            f"using profile '{profile.name}' (env key: {env_key})"
        )

        from plaid.model.link_token_create_request import LinkTokenCreateRequest
        from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
        from plaid.model.products import Products
        from plaid.model.country_code import CountryCode

        link_request = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(client_user_id='finance_sync_user'),
            client_name='Finance Sync',
            language='en',
            country_codes=[CountryCode('US')],
            access_token=existing_access_token,
            additional_consented_products=[Products('transactions')],
            transactions={"days_requested": 730},
            optional_products=[
                Products('investments'),
                Products('liabilities'),
                Products('identity'),
                Products('signal'),
                Products('statements'),
            ],
        )

        client = plaid_integration.get_plaid_client(profile)
        response = client.link_token_create(link_request)

        print(
            f"\n✓ Generated Update Link Token for {institution_name.upper()} "
            f"(profile: {profile.name})"
        )

        return jsonify({
            'success': True,
            'link_token': response.link_token,
            'is_update': True,
            'profile': profile.name,
        })

    except Exception as e:
        logger.exception("Failed to generate update link token")
        return jsonify({
            'success': False,
            'message': f'Update setup failed: {str(e)}'
        }), 500


# ─── Startup Instructions ─────────────────────────────────────────────────

def print_startup_message():
    """Print setup instructions to the terminal when the server starts."""
    print("\n" + "="*70)
    print("Finance Sync — Plaid Link Setup")
    print("="*70)
    print("\nStarting Flask server on http://localhost:5000")
    print("\n📝 Setup Instructions:")
    print("  1. Open http://localhost:5000 in your web browser")
    print("  2. Click 'Open Plaid Link'")
    print("  3. Search for and select your bank")
    print("  4. Log in to authorize access to your transactions")
    print("  5. After authentication succeeds, an access token will be displayed")
    print("  6. Copy the access token and add it to your .env file as:")
    print(f"     PLAID_{PLAID_ENV.upper()}_TOKEN_INSTITUTIONNAME=<token>")
    print("  7. Repeat steps 1-6 for each bank/institution you want to connect")
    print("  8. When finished, stop this server with Ctrl+C")
    print("\n⚠️  IMPORTANT:")
    print("  - NEVER commit access tokens to version control")
    print("  - Keep your .env file in .gitignore")
    print("  - Store tokens securely and treat them like passwords")
    print("="*70 + "\n")


# ─── Main Entry Point ──────────────────────────────────────────────────────

if __name__ == '__main__':
    print_startup_message()
    app.run(debug=True, port=5000)
