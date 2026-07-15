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
            Click the button below to open Plaid Link. Search for and select your bank,
            then log in to authorize Finance Sync to access your transactions.
            After you authenticate, an access token will be generated and displayed.
            Copy it to your .env file and repeat for each bank you want to connect.
        </div>

        <button id="openLink" class="button">Open Plaid Link</button>
        
        <div id="status"></div>
    </div>

    <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
    <script>
        document.getElementById('openLink').addEventListener('click', async () => {
            try {
                // Fetch fresh link token from the backend
                const response = await fetch('/link_token');
                const data = await response.json();

                if (!data.link_token) {
                    throw new Error('No link token received from server');
                }

                // Initialize and open Plaid Link
                const handler = Plaid.create({
                    token: data.link_token,
                    onSuccess: async (public_token, metadata) => {
                        showStatus('loading', 'Exchanging token with server...');

                        // Exchange public token for access token
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
                        }
                    }
                });

                handler.open();
            } catch (error) {
                showStatus('error', `Error: ${error.message}`);
            }
        });

        function showStatus(type, message) {
            const statusDiv = document.getElementById('status');
            statusDiv.className = type;
            statusDiv.textContent = message;
        }
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
