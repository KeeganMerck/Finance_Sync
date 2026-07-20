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

from config import PLAID_ENV
import plaid_integration

# Configure logging for the setup process
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(name)-20s  %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)


# ─── Flask App ─────────────────────────────────────────────────────────────

app = Flask(__name__)


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

        <div id="institutionSelect" style="margin: 15px 0; display: none;">
            <label for="institution" style="display: block; margin-bottom: 5px;">Institution name (from .env):</label>
            <input type="text" id="institution" placeholder="e.g., fidelity, robinhood, chase" 
                   style="padding: 8px; width: 200px; border: 1px solid #ddd; border-radius: 4px;">
        </div>

        <button id="openLink" class="button">Open Plaid Link</button>
        
        <div id="status"></div>
    </div>

    <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            // Handle mode selection to show/hide institution input
            document.querySelectorAll('input[name="mode"]').forEach(radio => {
                radio.addEventListener('change', (e) => {
                    const institutionDiv = document.getElementById('institutionSelect');
                    institutionDiv.style.display = e.target.value === 'update' ? 'block' : 'none';
                });
            });

            // Helper function that converts a single Plaid instance into a blocking Promise
            function openPlaidPromise(token) {
                return new Promise((resolve) => {
                    const handler = Plaid.create({
                        token: token,
                        onSuccess: (public_token, metadata) => {
                            console.log("Successfully updated item:", metadata);
                            resolve({ status: 'success', metadata });
                        },
                        onExit: (err, metadata) => {
                            if (err) {
                                console.error("Plaid Link error during update execution:", err);
                                resolve({ status: 'error', error: err });
                            } else {
                                console.log("User closed update modal manually.");
                                resolve({ status: 'exited' });
                            }
                        }
                    });
                    handler.open();
                });
            }

            document.getElementById('openLink').addEventListener('click', async () => {
                try {
                    const mode = document.querySelector('input[name="mode"]:checked').value;
                    
                    if (mode === 'update_all') {
                        showStatus('loading', 'Generating update tokens for all institutions...');
                        
                        const response = await fetch('/update_all_link_tokens', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' }
                        });
                        const data = await response.json();
                        
                        if (!data.success) {
                            showStatus('error', data.message || 'Failed to generate update tokens');
                            return;
                        }

                        showStatus('loading', 'Tokens generated. Starting interactive updates sequence...');

                        let summaryReport = "";
                        
                        // Loop sequentially through each token returned by your backend dict
                        for (const [institution, token] of Object.entries(data.update_tokens)) {
                            if (token.startsWith('ERROR')) {
                                summaryReport += `❌ ${institution.toUpperCase()}: Failed token generation\n`;
                                continue;
                            }

                            showStatus('loading', `Opening prompt window for: ${institution.toUpperCase()}...`);
                            
                            // Execution blocks here completely until the specific overlay window is closed
                            const result = await openPlaidPromise(token);
                            
                            if (result.status === 'success') {
                                summaryReport += `✅ ${institution.toUpperCase()}: Successfully Updated\n`;
                            } else {
                                summaryReport += `⚠️ ${institution.toUpperCase()}: Skipped/Closed without validation\n`;
                            }
                        }

                        showStatus('success', `Sequence complete! Status report:\n\n${summaryReport}`);
                        return;
                    }
                    
                    showStatus('loading', 'Fetching link token...');
                    let response, data;
                    
                    if (mode === 'update') {
                        const institution = document.getElementById('institution').value.trim();
                        if (!institution) {
                            showStatus('error', 'Please enter an institution name for update mode');
                            return;
                        }
                        
                        response = await fetch('/update_link_token', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ institution })
                        });
                        data = await response.json();
                    } else {
                        response = await fetch('/link_token');
                        data = await response.json();
                    }

                    if (!data.link_token) {
                        throw new Error('No link token received from server');
                    }

                    const isUpdateMode = data.is_update === true;

                    const handler = Plaid.create({
                        token: data.link_token,
                        onSuccess: async (public_token, metadata) => {
                            if (isUpdateMode) {
                                showStatus('success', 'Token updated successfully! Your existing access_token has been extended.');
                                return;
                            }

                            showStatus('loading', 'Exchanging public token with server...');
                            const exchangeResponse = await fetch('/exchange', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ public_token: public_token })
                            });

                            const exchangeData = await exchangeResponse.json();
                            if (exchangeData.success) {
                                showStatus('success', exchangeData.message);
                            } else {
                                showStatus('error', exchangeData.message || 'Exchange failed');
                            }
                        },
                        onExit: (err, metadata) => {
                            if (err) {
                                showStatus('error', 'Setup cancelled or failed. Please try again.');
                            } else {
                                showStatus('', '');
                            }
                        }
                    });
                            
                    handler.open();
                } catch (error) {
                    showStatus('error', 'Error: ' + error.message);
                }
            });

            function showStatus(type, message) {
                const statusDiv = document.getElementById('status');
                if (!type) {
                    statusDiv.style.display = 'none';
                    return;
                }
                statusDiv.className = type;
                statusDiv.textContent = message;
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
        link_token = plaid_integration.create_link_token()
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
        access_token = plaid_integration.item_public_token_exchange(public_token)

        # Print the access token clearly to the terminal so the user can copy it
        print("\n" + "="*70)
        print("✓ SUCCESS — New access token obtained:")
        print("="*70)
        print(f"Access Token: {access_token}")
        print("-"*70)
        print("Copy this token and add it to your .env file as:")
        print(f"  PLAID_{PLAID_ENV.upper()}_TOKEN_<INSTITUTIONNAME>=<token>")
        print("where <INSTITUTIONNAME> is the name of the bank (e.g., CHASE, AMEX).")
        print("="*70 + "\n")

        return jsonify({
            'success': True,
            'message': f'Access token obtained! Check the terminal for details.',
            'access_token': access_token,  # Also in JSON for reference
        })

    except Exception as e:
        logger.exception("Failed to exchange public token")
        return jsonify({
            'success': False,
            'message': f'Token exchange failed: {str(e)}'
        }), 500

@app.route('/update_all_link_tokens', methods=['POST'])
def generate_all_update_link_tokens():
    """
    Generates Plaid Link Tokens in UPDATE mode for all existing connections.
    Processes all PLAID_{ENV}_TOKEN_* environment variables and returns
    update tokens for each institution using working dictionary parameters.
    """
    try:
        prefix = f'PLAID_{PLAID_ENV.upper()}_TOKEN_'
        tokens = {}
        update_tokens = {}

        # Find all existing access tokens
        for key, value in os.environ.items():
            if key.startswith(prefix) and value:
                institution_name = key[len(prefix):]
                tokens[institution_name] = value

        if not tokens:
            return jsonify({
                'success': False,
                'message': f'No existing access tokens found matching {prefix}*'
            }), 404

        # Import required Plaid models
        from plaid.model.link_token_create_request import LinkTokenCreateRequest
        from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
        from plaid.model.products import Products
        from plaid.model.country_code import CountryCode

        client = plaid_integration.get_plaid_client()

        # Generate update tokens for each institution
        for institution_name, existing_access_token in tokens.items():
            try:
                # Build request using working dict structure for transactions
                link_request = LinkTokenCreateRequest(
                    user=LinkTokenCreateRequestUser(client_user_id='finance_sync_user'),
                    client_name='Finance Sync',
                    language='en',
                    country_codes=[CountryCode('US')],
                    access_token=existing_access_token, 
                    
                    # 1. Main baseline configuration
                    additional_consented_products=[Products('transactions')],
                    transactions={ "days_requested": 730 }, # Dictionary format retained
                    
                    # 2. Cleaned optional products to prevent INVALID_PRODUCT crashes
                    optional_products=[
                        Products('investments'),
                        Products('liabilities'),
                        Products('identity'),
                        Products('assets')
                    ]
                )

                response = client.link_token_create(link_request)
                
                # Check for standard dict-like or object-based response properties safely
                token_val = response.get('link_token') if isinstance(response, dict) else response.link_token
                update_tokens[institution_name] = token_val
                logger.info(f"Generated update link token for {institution_name}")

            except Exception as e:
                logger.error(f"Failed to generate update token for {institution_name}: {e}")
                update_tokens[institution_name] = f"ERROR: {str(e)}"

        successful_count = len([t for t in update_tokens.values() if not t.startswith('ERROR')])
        print(f"\n✓ Generated {successful_count} update link tokens out of {len(tokens)} institutions")

        # Returns the update_tokens payload required by your frontend Promise queue loop
        return jsonify({
            'success': True,
            'update_tokens': update_tokens,
            'total': len(tokens),
            'successful': successful_count
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
    Generates a Plaid Link Token in UPDATE mode for an existing connection.
    This adds investment endpoints.
    """
    try:
        data = request.get_json() or {}
        institution_name = data.get('institution') # e.g., 'fidelity', 'robinhood'

        if not institution_name:
            return jsonify({
                'success': False,
                'message': 'Missing target institution name'
            }), 400

        # 1. Fetch your existing access token from your environment configuration
        env_key = f"PLAID_{PLAID_ENV.upper()}_TOKEN_{institution_name.upper()}"
        existing_access_token = os.environ.get(env_key)

        if not existing_access_token:
            return jsonify({
                'success': False,
                'message': f'Existing access token not found in .env for: {env_key}'
            }), 404

        # Import required Plaid models
        from plaid.model.link_token_create_request import LinkTokenCreateRequest
        from plaid.model.link_token_create_request_user import (
            LinkTokenCreateRequestUser
        )
        from plaid.model.products import Products
        from plaid.model.country_code import CountryCode

        # 3. Formulate the update token query
        link_request = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(client_user_id='finance_sync_user'),
            client_name='Finance Sync',
            language='en',
            country_codes=[CountryCode('US')],
            
            # Crucial: This access token tells Plaid to update, not create
            access_token=existing_access_token, 
            
            # Appends investment capability to the account
            additional_consented_products=[Products('transactions')],
            transactions={ "days_requested": 730 },  # Forces the 24-month historical pull

            optional_products=[
                Products('investments'),        # Investment holdings and transactions
                Products('liabilities'),        # Loan/credit data (interest rates, payments)
                Products('identity'),           # User identity information
                Products('signal'),             # Transaction scores/risk analysis
                Products('statements'),         # Account statements
                Products('assets'),             # Asset reports
            ]
        )

        # 4. Generate the token from Plaid's SDK
        client = plaid_integration.get_plaid_client()
        response = client.link_token_create(link_request)

        print(f"\n✓ Generated Update Link Token for {institution_name.upper()}")

        return jsonify({
            'success': True,
            'link_token': response.link_token,
            'is_update': True  # Tells your frontend HTML template to skip the /exchange route
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
