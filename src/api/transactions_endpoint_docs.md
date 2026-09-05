Transactions 
=============

#### API reference for Transactions endpoints and webhooks 

Retrieve and refresh up to 24 months of historical transaction data, including geolocation, merchant, and category information. For how-to guidance, see the [Transactions documentation](https://plaid.com/docs/transactions/index.html.md) .

| Endpoints |  |
| --- | --- |
| [/transactions/sync](https://plaid.com/docs/api/products/transactions/index.html.md#transactionssync) | Get transaction data or incremental transaction updates |
| [/transactions/get](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsget) | Fetch transaction data |
| [/transactions/recurring/get](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsrecurringget) | Fetch recurring transaction data |
| [/transactions/refresh](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsrefresh) | Refresh transaction data |
| [/categories/get](https://plaid.com/docs/api/products/transactions/index.html.md#categoriesget) | (Deprecated) Fetch all legacy transaction categories |

| See also |  |
| --- | --- |
| [/processor/transactions/sync](https://plaid.com/docs/api/processor-partners/index.html.md#processortransactionssync) | Get transaction data or incremental transaction updates |
| [/processor/transactions/get](https://plaid.com/docs/api/processor-partners/index.html.md#processortransactionsget) | Fetch transaction data |
| [/processor/transactions/recurring/get](https://plaid.com/docs/api/processor-partners/index.html.md#processortransactionsrecurringget) | Fetch recurring transaction data |
| [/processor/transactions/refresh](https://plaid.com/docs/api/processor-partners/index.html.md#processortransactionsrefresh) | Refresh transaction data |
| [/sandbox/transactions/create](https://plaid.com/docs/api/sandbox/index.html.md#sandboxtransactionscreate) | Create custom transactions for testing |

| Webhooks |  |
| --- | --- |
| [SYNC\_UPDATES\_AVAILABLE](https://plaid.com/docs/api/products/transactions/index.html.md#sync_updates_available) | New updates available |
| [RECURRING\_TRANSACTIONS\_UPDATE](https://plaid.com/docs/api/products/transactions/index.html.md#recurring_transactions_update) | New recurring updates available |
| [INITIAL\_UPDATE](https://plaid.com/docs/api/products/transactions/index.html.md#initial_update) | Initial transactions ready |
| [HISTORICAL\_UPDATE](https://plaid.com/docs/api/products/transactions/index.html.md#historical_update) | Historical transactions ready |
| [DEFAULT\_UPDATE](https://plaid.com/docs/api/products/transactions/index.html.md#default_update) | New transactions available |
| [TRANSACTIONS\_REMOVED](https://plaid.com/docs/api/products/transactions/index.html.md#transactions_removed) | Deleted transactions detected |

### Endpoints 

\=\*=\*=\*=

#### /transactions/sync 

If you are migrating to [/transactions/sync](https://plaid.com/docs/api/products/transactions/index.html.md#transactionssync) from an existing [/transactions/get](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsget) integration, also refer to the [Transactions Sync migration guide](https://plaid.com/docs/transactions/sync-migration/index.html.md) .

#### Get incremental transaction updates on an Item 

The [/transactions/sync](https://plaid.com/docs/api/products/transactions/index.html.md#transactionssync) endpoint retrieves transactions associated with an Item and can fetch updates using a cursor to track which updates have already been seen.

For important instructions on integrating with [/transactions/sync](https://plaid.com/docs/api/products/transactions/index.html.md#transactionssync) , see the [Transactions integration overview](https://plaid.com/docs/transactions/index.html.md#integration-overview) . If you are migrating from an existing integration using [/transactions/get](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsget) , see the [Transactions Sync migration guide](https://plaid.com/docs/transactions/sync-migration/index.html.md) .

This endpoint supports `credit`, `depository`, and some `loan`\-type accounts (only those with account subtype `student` or `mortgage`). For `investments` accounts, use [/investments/transactions/get](https://plaid.com/docs/api/products/investments/index.html.md#investmentstransactionsget) instead.

When retrieving paginated updates, track both the `next_cursor` from the latest response and the original cursor from the first call in which `has_more` was `true`; if a call to [/transactions/sync](https://plaid.com/docs/api/products/transactions/index.html.md#transactionssync) fails when retrieving a paginated update (e.g. due to the [TRANSACTIONS\_SYNC\_MUTATION\_DURING\_PAGINATION](https://plaid.com/docs/errors/transactions/index.html.md#transactions_sync_mutation_during_pagination) error), the entire pagination request loop must be restarted beginning with the cursor for the first page of the update, rather than retrying only the single request that failed.

If transactions data is not yet available for the Item, which can happen if the Item was not initialized with transactions during the [/link/token/create](https://plaid.com/docs/api/link/index.html.md#linktokencreate) call or if [/transactions/sync](https://plaid.com/docs/api/products/transactions/index.html.md#transactionssync) was called within a few seconds of Item creation, [/transactions/sync](https://plaid.com/docs/api/products/transactions/index.html.md#transactionssync) will return empty transactions arrays.

Plaid typically checks for new transactions data between one and four times per day, depending on the institution. To find out when transactions were last updated for an Item, use the [Item Debugger](https://plaid.com/docs/account/activity/index.html.md#troubleshooting-with-item-debugger) or call [/item/get](https://plaid.com/docs/api/items/index.html.md#itemget) ; the `item.status.transactions.last_successful_update` field will show the timestamp of the most recent successful update. To force Plaid to check for new transactions, use the [/transactions/refresh](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsrefresh) endpoint.

To be alerted when new transactions are available, listen for the [SYNC\_UPDATES\_AVAILABLE](https://plaid.com/docs/api/products/transactions/index.html.md#sync_updates_available) webhook.

#### Request fields 

string

Your Plaid API `client_id`. The `client_id` is required and may be provided either in the `PLAID-CLIENT-ID` header or as part of a request body.

required, string

The access token associated with the Item for which data is being requested.

string

Your Plaid API `secret`. The `secret` is required and may be provided either in the `PLAID-SECRET` header or as part of a request body.

string

The cursor value represents the last update requested. Providing it will cause the response to only return changes after this update. If omitted, the entire history of updates will be returned, starting with the first-added transactions on the Item. The cursor also accepts the special value of `"now"`, which can be used to fast-forward the cursor as part of migrating an existing Item from `/transactions/get` to `/transactions/sync`. For more information, see the [Transactions sync migration guide](https://plaid.com/docs/transactions/sync-migration/index.html.md) . Note that using the `"now"` value is not supported for any use case other than migrating existing Items from `/transactions/get`.

The upper-bound length of this cursor is 256 characters of base64.

integer

The number of transaction updates to fetch.

Default: `100`

Minimum: `1`

Maximum: `500`

Exclusive min: `false`

object

An optional object to be used with the request. If specified, `options` must not be `null`.

boolean

Include the raw unparsed transaction description from the financial institution.

Default: `false`

string

Indicates which version of the personal finance category taxonomy is being used. [View PFCv2 and PFCv1 taxonomies](https://plaid.com/documents/pfc-taxonomy-all.csv) .

If you enabled Transactions or Enrich before December 3, 2025 you will receive the `v1` taxonomy by default and may request `v2` by explicitly setting this field to `v2` in the request.

If you enabled Transactions or Enrich on or after December 3, 2025, you may only receive the `v2` taxonomy.

Possible values: `v1`, `v2`

integer

This field only applies to calls for Items where the Transactions product has not already been initialized (i.e., by specifying `transactions` in the `products`, `required_if_supported_products`, or `optional_products` array when calling `/link/token/create` or by making a previous call to `/transactions/sync` or `/transactions/get`). In those cases, the field controls the maximum number of days of transaction history that Plaid will request from the financial institution. The more transaction history is requested, the longer the historical update poll will take. If no value is specified, 90 days of history will be requested by default. In Production, if a value less than 30 is provided, a minimum of 30 days of transaction history will be requested.

If you are initializing your Items with transactions during the `/link/token/create` call (e.g. by including `transactions` in the `/link/token/create` `products` array), you must use the [transactions.days\_requested](https://plaid.com/docs/api/link/index.html.md#link-token-create-request-transactions-days-requested) field in the `/link/token/create` request instead of in the `/transactions/sync` request.

If the Item has already been initialized with the Transactions product, this field will have no effect. The maximum amount of transaction history to request on an Item cannot be updated if Transactions has already been added to the Item. To request older transaction history on an Item where Transactions has already been added, you must delete the Item via `/item/remove` and send the user through Link to create a new Item.

Customers using [Recurring Transactions](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsrecurringget) should request at least 180 days of history for optimal results.

Minimum: `1`

Maximum: `730`

Default: `90`

string

If provided, the returned updates and cursor will only reflect the specified account's transactions. Omitting `account_id` returns updates for all accounts under the Item. Note that specifying an `account_id` effectively creates a separate incremental update stream -- and therefore a separate cursor -- for that account. If multiple accounts are queried this way, you will maintain multiple cursors, one per `account_id`.

If you decide to begin filtering by `account_id` after using no `account_id`, start fresh with a null cursor and maintain separate `(account_id, cursor)` pairs going forward. Do not reuse any previously saved cursors, as this can cause pagination errors or incomplete data.

Note: An error will be returned if a provided `account_id` is not associated with the Item.

```node
// Provide a cursor from your database if you've previously
// received one for the Item. Leave null if this is your
// first sync call for this Item. The first request will
// return a cursor.
let cursor = database.getLatestCursorOrNull(itemId);

// New transaction updates since "cursor"
let added: Array = [];
let modified: Array = [];
// Removed transaction ids
let removed: Array = [];
let hasMore = true;

// Iterate through each page of new transaction updates for item
while (hasMore) {
  const request: TransactionsSyncRequest = {
    access_token: accessToken,
    cursor: cursor,
  };
  const response = await client.transactionsSync(request);
  const data = response.data;

  // Add this page of results
  added = added.concat(data.added);
  modified = modified.concat(data.modified);
  removed = removed.concat(data.removed);

  hasMore = data.has_more;

  // Update cursor to the next cursor
  cursor = data.next_cursor;
}

// Persist cursor and updated data
database.applyUpdates(itemId, added, modified, removed, cursor);

```

```bash
curl -X POST https://sandbox.plaid.com/transactions/sync \
-H 'Content-Type: application/json' \
-d '{
  "client_id": "${PLAID_CLIENT_ID}",
  "secret": "${PLAID_SECRET}",
  "access_token": String,
  "cursor": String,
  "count": 250
}'

```

```ruby
# Provide a cursor from your database if you've previously
# received one for the Item. Leave null if this is your
# first sync call for this item. The first request will
# return a cursor.
cursor = database.get_latest_cursor_or_none(item_id)

# New transaction updates since "cursor"
added = []
modified = []
removed = [] # Removed transaction ids
has_more = true

# Iterate through each page of new transaction updates for item
while has_more
  request = Plaid::TransactionsSyncRequest.new(
    {
      access_token: access_token,
      cursor: cursor,
    }
  )

  response = client.transactions_sync(request)

  # Add this page of results
  added += response.added
  modified += response.modified
  removed += response.removed

  has_more = response.has_more

  # Update cursor to the next cursor
  cursor = response.next_cursor
end

# Persist cursor and updated data
database.apply_updates(item_id, added, modified, removed, cursor)

```

```java
// Provide a cursor from your database if you've previously
// received one for the item leave null if this is your
// first sync call for this item. The first request will
// return a cursor.
String cursor = database.getLatestCursorOrNull(itemId);

// New transaction updates since "cursor"
List added = new ArrayList();
List modified = new ArrayList();
List removed = new ArrayList();
boolean hasMore = true;

// Iterate through each page of new transaction updates for item
while (hasMore) {
  TransactionsSyncRequest request = new TransactionsSyncRequest()
    .accessToken(accessToken)
    .cursor(cursor);

  TransactionsSyncResponse response = plaidClient.transactionsSync(request).execute().body();

  // Add this page of results
  added.addAll(response.getAdded());
  modified.addAll(response.getModified());
  removed.addAll(response.getRemoved());

  hasMore = response.getHasMore();

  // Update cursor to the next cursor
  cursor = response.getNextCursor();
}
// Persist cursor and updated data
database.applyUpdates(itemId, added, modified, removed, cursor);

```

```python
# Provide a cursor from your database if you've previously
# received one for the Item. Leave null if this is your
# first sync call for this Item. The first request will
# return a cursor.
cursor = database.get_latest_cursor_or_none(item_id)

# New transaction updates since "cursor"
added = []
modified = []
removed = [] # Removed transaction ids
has_more = True

# Iterate through each page of new transaction updates for item
while has_more:
  request = TransactionsSyncRequest(
    access_token=access_token,
    cursor=cursor,
  )
  response = plaid_client.transactions_sync(request)

  # Add this page of results
  added.extend(response['added'])
  modified.extend(response['modified'])
  removed.extend(response['removed'])

  has_more = response['has_more']

  # Update cursor to the next cursor
  cursor = response['next_cursor']

# Persist cursor and updated data
database.apply_updates(item_id, added, modified, removed, cursor)

```

```go
// Provide a cursor from your database if you've previously
// received one for the Item. Leave null if this is your
// first sync call for this Item. The first request will
// return a cursor.
cursor := database.getLatestCursorOrNil(itemId)

// New transaction updates since "cursor"
var added []Transaction
var modified []Transaction
var removed []RemovedTransaction // Removed transaction ids
hasMore := true

// Iterate through each page of new transaction updates for item
for hasMore {
    request := plaid.NewTransactionsSyncRequest(accessToken)
    if cursor != nil {
        request.SetCursor(*cursor)
    }
    resp, _, err := client.PlaidApi.TransactionsSync(
        ctx,
    ).TransactionsSyncRequest(*request).Execute()

    // Add this page of results
    added = append(added, resp.GetAdded()...)
    modified = append(modified, resp.GetModified()...)
    removed = append(removed, resp.GetRemoved()...)

    hasMore = resp.GetHasMore()

    // Update cursor to the next cursor
    nextCursor := resp.GetNextCursor()
    cursor = &nextCursor
}

// Persist cursor and updated data
database.applyUpdates(itemId, added, modified, removed, cursor)

```

#### Response fields 

string

A description of the update status for transaction pulls of an Item. This field contains the same information provided by transactions webhooks, and may be helpful for webhook troubleshooting or when recovering from missed webhooks.

`TRANSACTIONS_UPDATE_STATUS_UNKNOWN`: Unable to fetch transactions update status for Item. `NOT_READY`: The Item is pending transaction pull. `INITIAL_UPDATE_COMPLETE`: Initial pull for the Item is complete, historical pull is pending. `HISTORICAL_UPDATE_COMPLETE`: Both initial and historical pull for Item are complete.

Possible values: `TRANSACTIONS_UPDATE_STATUS_UNKNOWN`, `NOT_READY`, `INITIAL_UPDATE_COMPLETE`, `HISTORICAL_UPDATE_COMPLETE`

\[object\]

An array of accounts at a financial institution associated with the transactions in this response. Only accounts that have associated transactions will be shown. For example, `investment`\-type accounts will be omitted.

string

Plaid's unique identifier for the account. This value will not change unless Plaid can't reconcile the account with the data returned by the financial institution. This may occur, for example, when the name of the account changes. If this happens a new `account_id` will be assigned to the account.

The `account_id` can also change if the `access_token` is deleted and the same credentials that were used to generate that `access_token` are used to generate a new `access_token` on a later date. In that case, the new `account_id` will be different from the old `account_id`.

If an account with a specific `account_id` disappears instead of changing, the account is likely closed. Closed accounts are not returned by the Plaid API.

When using a CRA endpoint (an endpoint associated with Plaid Check Consumer Report, i.e. any endpoint beginning with `/cra/`), the `account_id` returned will not match the `account_id` returned by a non-CRA endpoint.

Like all Plaid identifiers, the `account_id` is case sensitive.

object

A set of fields describing the balance for an account. For real-time values, use `/accounts/balance/get` or `/signal/evaluate` (with a Balance-only ruleset), which are fetched live from the institution at request time. Values returned by other endpoints may be cached, or adjusted by Plaid to reflect transaction activity received since the last refresh.

nullable, number

The amount of funds available to be withdrawn from the account, as determined by the financial institution.

For `credit`\-type accounts, the `available` balance typically equals the `limit` less the `current` balance, less any pending outflows plus any pending inflows.

For `depository`\-type accounts, the `available` balance typically equals the `current` balance less any pending outflows plus any pending inflows. For `depository`\-type accounts, the `available` balance does not include the overdraft limit.

For `investment`\-type accounts (or `brokerage`\-type accounts for API versions 2018-05-22 and earlier), the `available` balance is the total cash available to withdraw as presented by the institution.

Note that not all institutions calculate the `available` balance. In the event that `available` balance is unavailable, Plaid will return an `available` balance value of `null`.

Available balance may be cached and is not guaranteed to be up-to-date in real-time unless the value was returned by `/accounts/balance/get`, or by `/signal/evaluate` with a Balance-only ruleset.

If `current` is `null` this field is guaranteed not to be `null`, unless you have opted into enabling [limited-purpose checking accounts](https://plaid.com/docs/auth/index.html.md#enabling-limited-purpose-checking-accounts-for-rent-or-mortgage) , which always have `null` values for both `available` and `current` balance.

Format: `double`

nullable, number

The total amount of funds in or owed by the account.

For `credit`\-type accounts, a positive balance indicates the amount owed; a negative amount indicates the lender owing the account holder.

For `loan`\-type accounts, the current balance is the principal remaining on the loan, except in the case of student loan accounts at Sallie Mae (`ins_116944`). For Sallie Mae student loans, the account's balance includes both principal and any outstanding interest. Similar to `credit`\-type accounts, a positive balance is typically expected, while a negative amount indicates the lender owing the account holder.

For `investment`\-type accounts (or `brokerage`\-type accounts for API versions 2018-05-22 and earlier), the current balance is the total value of assets as presented by the institution.

Note that balance information may be cached unless the value was returned by `/accounts/balance/get` or by `/signal/evaluate` with a Balance-only ruleset; if the Item is enabled for Transactions, the balance will be at least as recent as the most recent Transaction update. If you require real-time balance information, use the `available` balance as provided by `/accounts/balance/get` or `/signal/evaluate` called with a Balance-only `ruleset_key`.

When returned by `/accounts/balance/get`, this field may be `null`. When this happens, `available` is guaranteed not to be `null`, unless you have opted into enabling [limited-purpose checking accounts](https://plaid.com/docs/auth/index.html.md#enabling-limited-purpose-checking-accounts-for-rent-or-mortgage) , which always have `null` values for both `available` and `current` balance.

Format: `double`

nullable, number

For `credit`\-type accounts, this represents the credit limit.

For `depository`\-type accounts, this represents the pre-arranged overdraft limit, which is common for current (checking) accounts in Europe.

In North America, this field is typically only available for `credit`\-type accounts.

Format: `double`

nullable, string

The ISO-4217 currency code of the balance. Always null if `unofficial_currency_code` is non-null.

nullable, string

The unofficial currency code associated with the balance. Always null if `iso_currency_code` is non-null. Unofficial currency codes are used for currencies that do not have official ISO currency codes, such as cryptocurrencies and the currencies of certain countries.

See the [currency code schema](https://plaid.com/docs/api/accounts/index.html.md#currency-code-schema) for a full listing of supported `unofficial_currency_code`s.

nullable, string

Timestamp in [ISO 8601](https://en.wikipedia.org/wiki/ISO_8601) format (`YYYY-MM-DDTHH:mm:ssZ`) indicating the last time the balance was updated.

This field is returned only when the institution is `ins_128026` (Capital One).

Format: `date-time`

nullable, string

The last 2-4 alphanumeric characters of either the account's displayed mask or the account's official account number. Note that the mask may be non-unique between an Item's accounts.

string

The name of the account, either assigned by the user or by the financial institution itself

nullable, string

The official name of the account as given by the financial institution

string

`investment:` Investment account. In API versions 2018-05-22 and earlier, this type is called `brokerage` instead.

`credit:` Credit card

`depository:` Depository account

`loan:` Loan account

`other:` Non-specified account type

See the [Account type schema](https://plaid.com/docs/api/accounts/index.html.md#account-type-schema) for a full listing of account types and corresponding subtypes.

Possible values: `investment`, `credit`, `depository`, `loan`, `brokerage`, `other`

nullable, string

See the [Account type schema](https://plaid.com/docs/api/accounts/index.html.md#account-type-schema) for a full listing of account types and corresponding subtypes.

Possible values: `401a`, `401k`, `403B`, `457b`, `529`, `auto`, `brokerage`, `business`, `cash isa`, `cash management`, `cd`, `checking`, `commercial`, `construction`, `consumer`, `credit card`, `crypto exchange`, `ebt`, `education savings account`, `fhsa`, `fixed annuity`, `gic`, `health reimbursement arrangement`, `home equity`, `hsa`, `isa`, `ira`, `keogh`, `lif`, `life insurance`, `limited purpose checking`, `line of credit`, `lira`, `loan`, `lrif`, `lrsp`, `money market`, `mortgage`, `mutual fund`, `non-custodial wallet`, `non-taxable brokerage account`, `other`, `other insurance`, `other annuity`, `overdraft`, `paypal`, `payroll`, `pension`, `prepaid`, `prif`, `profit sharing plan`, `qshr`, `rdsp`, `resp`, `retirement`, `rlif`, `roth`, `roth 401k`, `roth 403B`, `roth 457b`, `roth pension`, `roth profit sharing plan`, `roth thrift savings plan`, `rrif`, `rrsp`, `sarsep`, `savings`, `sep ira`, `simple ira`, `sipp`, `stock plan`, `student`, `thrift savings plan`, `tfsa`, `trust`, `ugma`, `utma`, `variable annuity`

string

Indicates an Item's micro-deposit-based verification or database verification status. This field is only populated when using Auth and falling back to micro-deposit or database verification. Possible values are:

`pending_automatic_verification`: The Item is pending automatic verification.

`pending_manual_verification`: The Item is pending manual micro-deposit verification. Items remain in this state until the user successfully verifies the code.

`automatically_verified`: The Item has successfully been automatically verified.

`manually_verified`: The Item has successfully been manually verified.

`verification_expired`: Plaid was unable to automatically verify the deposit within 7 calendar days and will no longer attempt to validate the Item. Users may retry by submitting their information again through Link.

`verification_failed`: The Item failed manual micro-deposit verification because the user exhausted all 3 verification attempts. Users may retry by submitting their information again through Link.

`unsent`: The Item is pending micro-deposit verification, but Plaid has not yet sent the micro-deposit.

`database_insights_fail`: The Item's numbers have been verified using Plaid's data sources and have signal for being invalid and/or have no signal for being valid. Typically this indicates that the routing number is invalid, the account number does not match the account number format associated with the routing number, or the account has been reported as closed or frozen. Only returned for Auth Items created via Database Auth.

`database_insights_pass`: The Item's numbers have been verified using Plaid's data sources: the routing and account number match a routing and account number of an account recognized on the Plaid network, and the account is not known by Plaid to be frozen or closed. Only returned for Auth Items created via Database Auth.

`database_insights_pass_with_caution`: The Item's numbers have been verified using Plaid's data sources and have some signal for being valid: the routing and account number were not recognized on the Plaid network, but the routing number is valid and the account number is a potential valid account number for that routing number. Only returned for Auth Items created via Database Auth.

`database_matched`: (deprecated) The Item has successfully been verified using Plaid's data sources. Only returned for Auth Items created via Database Match.

`null` or empty string: Neither micro-deposit-based verification nor database verification are being used for the Item.

Possible values: `automatically_verified`, `pending_automatic_verification`, `pending_manual_verification`, `unsent`, `manually_verified`, `verification_expired`, `verification_failed`, `database_matched`, `database_insights_pass`, `database_insights_pass_with_caution`, `database_insights_fail`

string

The account holder name that was used for micro-deposit and/or database verification. Only returned for Auth Items created via micro-deposit or database verification. This name was manually-entered by the user during Link, unless it was otherwise provided via the `user.legal_name` request field in `/link/token/create` for the Link session that created the Item.

object

Insights from performing database verification for the account. Only returned for Auth Items using Database Auth.

nullable, integer

Indicates the score of the name match between the given name provided during database verification (available in the [verification\_name](https://plaid.com/docs/api/products/auth/index.html.md#auth-get-response-accounts-verification-name) field if using standard Database Auth, or provided in the request if using `/auth/verify`) and matched Plaid network accounts. If defined, will be a value between 0 and 100. Will be undefined if name matching was not enabled for the database verification session or if there were no eligible Plaid network matches to compare the given name with.

object

Status information about the account and routing number in the Plaid network.

boolean

Indicates whether we found at least one matching account for the ACH account and routing number.

boolean

Indicates if at least one matching account for the ACH account and routing number is already verified.

object

Information about known ACH returns for the account and routing number.

boolean

Indicates whether Plaid's data sources include a known administrative ACH return for this account and routing number.

string

Indicator of account number format validity for institution.

`valid`: indicates that the account number has a correct format for the institution.

`invalid`: indicates that the account number has an incorrect format for the institution.

`unknown`: indicates that there was not enough information to determine whether the format is correct for the institution.

Possible values: `valid`, `invalid`, `unknown`

string

A unique and persistent identifier for accounts that can be used to trace multiple instances of the same account across different Items for depository accounts. This field is currently supported only for Items at institutions that use Tokenized Account Numbers (i.e., Chase, PNC, and US Bank). Because these accounts have a different account number each time they are linked, this field may be used instead of the account number to uniquely identify an account across multiple Items for payments use cases, helping to reduce duplicate Items or attempted fraud. In Sandbox, this field is populated for TAN-based institutions (`ins_56`, `ins_13`, `ins_127990`) as well as the OAuth Sandbox institution (`ins_127287`); in Production, it will only be populated for accounts at applicable institutions.

nullable, string

Indicates the account's categorization as either a personal or a business account. This field is currently in beta; to request access, contact your account manager.

Possible values: `business`, `personal`, `unrecognized`

\[object\]

Transactions that have been added to the Item since `cursor` ordered by ascending last modified time.

string

The ID of the account in which this transaction occurred.

number

The settled value of the transaction, denominated in the transaction's currency, as stated in `iso_currency_code` or `unofficial_currency_code`. For all products except Income: Positive values when money moves out of the account; negative values when money moves in. For example, debit card purchases are positive; credit card payments, direct deposits, and refunds are negative. For Income endpoints, values are positive when representing income.

Format: `double`

nullable, string

The ISO-4217 currency code of the transaction. Always `null` if `unofficial_currency_code` is non-null.

nullable, string

The unofficial currency code associated with the transaction. Always `null` if `iso_currency_code` is non-`null`. Unofficial currency codes are used for currencies that do not have official ISO currency codes, such as cryptocurrencies and the currencies of certain countries.

See the [currency code schema](https://plaid.com/docs/api/accounts/index.html.md#currency-code-schema) for a full listing of supported `unofficial_currency_code`s.

nullable, string

The check number of the transaction. This field is only populated for check transactions.

string

For pending transactions, the date that the transaction occurred; for posted transactions, the date that the transaction posted. Both dates are returned in an [ISO 8601](https://wikipedia.org/wiki/ISO_8601) format ( `YYYY-MM-DD` ). To receive information about the date that a posted transaction was initiated, see the `authorized_date` field.

Format: `date`

object

A representation of where a transaction took place. Location data is provided only for transactions at physical locations, not for online transactions. Location data availability depends primarily on the merchant and is most likely to be populated for transactions at large retail chains; small, local businesses are less likely to have location data available.

nullable, string

The street address where the transaction occurred.

nullable, string

The city where the transaction occurred.

nullable, string

The region or state where the transaction occurred. In API versions 2018-05-22 and earlier, this field is called `state`.

nullable, string

The postal code where the transaction occurred. In API versions 2018-05-22 and earlier, this field is called `zip`.

nullable, string

The ISO 3166-1 alpha-2 country code where the transaction occurred.

nullable, number

The latitude where the transaction occurred.

Format: `double`

nullable, number

The longitude where the transaction occurred.

Format: `double`

nullable, string

The merchant defined store number where the transaction occurred.

deprecated, string

The merchant name or transaction description.

Note: While Plaid does not currently plan to remove this field, it is a legacy field that is not actively maintained. Use `merchant_name` instead for the merchant name.

If the `transactions` object was returned by a Transactions endpoint such as `/transactions/sync` or `/transactions/get`, this field will always appear. If the `transactions` object was returned by an Assets endpoint such as `/asset_report/get` or `/asset_report/pdf/get`, this field will only appear in an Asset Report with Insights.

nullable, string

The merchant name, as enriched by Plaid from the `name` field. This is typically a more human-readable version of the merchant counterparty in the transaction. For some bank transactions (such as checks or account transfers) where there is no meaningful merchant name, this value will be `null`.

nullable, string

The string returned by the financial institution to describe the transaction. For transactions returned by `/transactions/sync` or `/transactions/get`, this field will only be included if the client has set `options.include_original_description` to `true`.

object

Transaction information specific to inter-bank transfers. If the transaction was not an inter-bank transfer, all fields will be `null`.

If the `transactions` object was returned by a Transactions endpoint such as `/transactions/sync` or `/transactions/get`, the `payment_meta` key will always appear, but no data elements are guaranteed. If the `transactions` object was returned by an Assets endpoint such as `/asset_report/get` or `/asset_report/pdf/get`, this field will only appear in an Asset Report with Insights.

nullable, string

The transaction reference number supplied by the financial institution.

nullable, string

The ACH PPD ID for the payer.

nullable, string

For transfers, the party that is receiving the transaction.

nullable, string

The party initiating a wire transfer. Will be `null` if the transaction is not a wire transfer.

nullable, string

For transfers, the party that is paying the transaction.

nullable, string

The type of transfer, e.g. 'ACH'

nullable, string

The name of the payment processor

nullable, string

The payer-supplied description of the transfer.

boolean

When `true`, identifies the transaction as pending or unsettled. Pending transaction details (name, type, amount, category ID) may change before they are settled. Not all institutions provide pending transactions.

nullable, string

The ID of a posted transaction's associated pending transaction, where applicable. Not all institutions provide pending transactions.

nullable, string

This field is not typically populated and only relevant when dealing with sub-accounts. A sub-account most commonly exists in cases where a single account is linked to multiple cards, each with its own card number and card holder name; each card will be considered a sub-account. If the account does have sub-accounts, this field will typically be some combination of the sub-account owner's name and/or the sub-account mask. The format of this field is not standardized and will vary based on institution.

string

The unique ID of the transaction. Like all Plaid identifiers, the `transaction_id` is case sensitive.

deprecated, string

Please use the `payment_channel` field, `transaction_type` will be deprecated in the future.

`digital:` transactions that took place online.

`place:` transactions that were made at a physical location.

`special:` transactions that relate to banks, e.g. fees or deposits.

`unresolved:` transactions that do not fit into the other three types.

Possible values: `digital`, `place`, `special`, `unresolved`

nullable, string

The URL of a logo associated with this transaction, if available. The logo will always be a 100×100 pixel PNG file.

nullable, string

The website associated with this transaction, if available.

nullable, string

The date that the transaction was authorized. For posted transactions, the `date` field will indicate the posted date, but `authorized_date` will indicate the day the transaction was authorized by the financial institution. If presenting transactions to the user in a UI, the `authorized_date`, when available, is generally preferable to use over the `date` field for posted transactions, as it will generally represent the date the user actually made the transaction. Dates are returned in an [ISO 8601](https://wikipedia.org/wiki/ISO_8601) format ( `YYYY-MM-DD` ).

Format: `date`

nullable, string

Date and time when a transaction was authorized in [ISO 8601](https://wikipedia.org/wiki/ISO_8601) format ( `YYYY-MM-DDTHH:mm:ssZ` ). For posted transactions, the `datetime` field will indicate the posted date, but `authorized_datetime` will indicate the day the transaction was authorized by the financial institution. If presenting transactions to the user in a UI, the `authorized_datetime`, when available, is generally preferable to use over the `datetime` field for posted transactions, as it will generally represent the date the user actually made the transaction.

This field is returned for select financial institutions and comes as provided by the institution. It may contain default time values (such as 00:00:00). This field is only populated in API version 2019-05-29 and later.

Format: `date-time`

nullable, string

Date and time when a transaction was posted in [ISO 8601](https://wikipedia.org/wiki/ISO_8601) format ( `YYYY-MM-DDTHH:mm:ssZ` ). For the date that the transaction was initiated, rather than posted, see the `authorized_datetime` field.

This field is returned for select financial institutions and comes as provided by the institution. It may contain default time values (such as 00:00:00). This field is only populated in API version 2019-05-29 and later.

Format: `date-time`

string

The channel used to make a payment. `online:` transactions that took place online.

`in store:` transactions that were made at a physical location.

`other:` transactions that relate to banks, e.g. fees or deposits.

This field replaces the `transaction_type` field.

Possible values: `online`, `in store`, `other`

nullable, object

Information describing the intent of the transaction. Most relevant for personal finance use cases, but not limited to such use cases.

See the [taxonomy CSV file](https://plaid.com/documents/pfc-taxonomy-all.csv) for a full list of personal finance categories. If you are migrating to personal finance categories from the legacy categories, also refer to the [migration guide](https://plaid.com/docs/transactions/pfc-migration/index.html.md) .

string

A high level category that communicates the broad category of the transaction.

string

A granular category conveying the transaction's intent. This field can also be used as a unique identifier for the category.

nullable, string

A description of how confident we are that the provided categories accurately describe the transaction intent.

`VERY_HIGH`: We are more than 98% confident that this category reflects the intent of the transaction. `HIGH`: We are more than 90% confident that this category reflects the intent of the transaction. `MEDIUM`: We are moderately confident that this category reflects the intent of the transaction. `LOW`: This category may reflect the intent, but there may be other categories that are more accurate. `UNKNOWN`: We don't know the confidence level for this category.

string

Indicates which version of the personal finance category taxonomy is being used. [View PFCv2 and PFCv1 taxonomies](https://plaid.com/documents/pfc-taxonomy-all.csv) .

If you enabled Transactions or Enrich before December 3, 2025 you will receive the `v1` taxonomy by default and may request `v2` by explicitly setting this field to `v2` in the request.

If you enabled Transactions or Enrich on or after December 3, 2025, you may only receive the `v2` taxonomy.

Possible values: `v1`, `v2`

nullable, string

An identifier classifying the transaction type.

This field is populated for European institutions, as well as certain institutions in the United States. For institutions where this classification is not available, this field is set to `null`.

`adjustment:` Bank adjustment

`atm:` Cash deposit or withdrawal via an automated teller machine

`bank charge:` Charge or fee levied by the institution

`bill payment`: Payment of a bill

`cash:` Cash deposit or withdrawal

`cash advance:` Cash advance drawn against a credit card or line of credit

`cashback:` Cash withdrawal while making a debit card purchase

`cheque:` Document ordering the payment of money to another person or organization

`direct debit:` Automatic withdrawal of funds initiated by a third party at a regular interval

`interest:` Interest earned or incurred

`late fee:` Fee associated with a late or past-due payment

`membership fee:` Annual or recurring membership fee

`payment:` One-off outbound payment not classified as a bill payment, direct debit, or standing order

`purchase:` Purchase made with a debit or credit card

`refund:` Merchant credit or return, such as a refund of a prior purchase

`returned item fee:` Fee for a returned item, such as a returned check or stop payment

`standing order:` Payment instructed by the account holder to a third party at a regular interval

`transfer:` Transfer of money between accounts

Possible values: `adjustment`, `atm`, `bank charge`, `bill payment`, `cash`, `cash advance`, `cashback`, `cheque`, `direct debit`, `interest`, `late fee`, `membership fee`, `payment`, `purchase`, `refund`, `returned item fee`, `standing order`, `transfer`, `null`

string

The URL of an icon associated with the primary personal finance category. The icon will always be a 100×100 pixel PNG file.

\[object\]

The counterparties present in the transaction. Counterparties, such as the merchant or the financial institution, are extracted by Plaid from the raw description.

string

The name of the counterparty, such as the merchant or the financial institution, as extracted by Plaid from the raw description.

nullable, string

A unique, stable, Plaid-generated ID that maps to the counterparty.

string

The counterparty type.

`merchant`: a provider of goods or services for purchase `financial_institution`: a financial entity (bank, credit union, BNPL, fintech) `payment_app`: a transfer or P2P app (e.g. Zelle) `marketplace`: a marketplace (e.g. DoorDash, Google Play Store) `payment_terminal`: a point-of-sale payment terminal (e.g. Square, Toast) `income_source`: the payer in an income transaction (e.g., an employer, client, or government agency)

Possible values: `merchant`, `financial_institution`, `payment_app`, `marketplace`, `payment_terminal`, `income_source`

nullable, string

The website associated with the counterparty.

nullable, string

The URL of a logo associated with the counterparty, if available. The logo will always be a 100×100 pixel PNG file.

nullable, string

A description of how confident we are that the provided counterparty is involved in the transaction.

`VERY_HIGH`: We recognize this counterparty and we are more than 98% confident that it is involved in this transaction. `HIGH`: We recognize this counterparty and we are more than 90% confident that it is involved in this transaction. `MEDIUM`: We are moderately confident that this counterparty was involved in this transaction, but some details may differ from our records. `LOW`: We didn't find a matching counterparty in our records, so we are returning a cleansed name parsed out of the request description. `UNKNOWN`: We don't know the confidence level for this counterparty.

nullable, object

Account numbers associated with the counterparty, when available. This field is currently only filled in for select financial institutions in Europe.

nullable, object

Identifying information for a UK bank account via Bacs.

nullable, string

The Bacs account number for the account.

nullable, string

The Bacs sort code for the account.

nullable, object

Account numbers using the International Bank Account Number and BIC/SWIFT code format.

nullable, string

International Bank Account Number (IBAN).

Min length: `15`

Max length: `34`

nullable, string

Business Identifier Code (BIC) for this counterparty.

Min length: `8`

Max length: `11`

nullable, string

A unique, stable, Plaid-generated ID that maps to the merchant. In the case of a merchant with multiple retail locations, this field will map to the broader merchant, not a specific location or store.

\[object\]

Transactions that have been modified on the Item since `cursor` ordered by ascending last modified time.

string

The ID of the account in which this transaction occurred.

number

The settled value of the transaction, denominated in the transaction's currency, as stated in `iso_currency_code` or `unofficial_currency_code`. For all products except Income: Positive values when money moves out of the account; negative values when money moves in. For example, debit card purchases are positive; credit card payments, direct deposits, and refunds are negative. For Income endpoints, values are positive when representing income.

Format: `double`

nullable, string

The ISO-4217 currency code of the transaction. Always `null` if `unofficial_currency_code` is non-null.

nullable, string

The unofficial currency code associated with the transaction. Always `null` if `iso_currency_code` is non-`null`. Unofficial currency codes are used for currencies that do not have official ISO currency codes, such as cryptocurrencies and the currencies of certain countries.

See the [currency code schema](https://plaid.com/docs/api/accounts/index.html.md#currency-code-schema) for a full listing of supported `unofficial_currency_code`s.

nullable, string

The check number of the transaction. This field is only populated for check transactions.

string

For pending transactions, the date that the transaction occurred; for posted transactions, the date that the transaction posted. Both dates are returned in an [ISO 8601](https://wikipedia.org/wiki/ISO_8601) format ( `YYYY-MM-DD` ). To receive information about the date that a posted transaction was initiated, see the `authorized_date` field.

Format: `date`

object

A representation of where a transaction took place. Location data is provided only for transactions at physical locations, not for online transactions. Location data availability depends primarily on the merchant and is most likely to be populated for transactions at large retail chains; small, local businesses are less likely to have location data available.

nullable, string

The street address where the transaction occurred.

nullable, string

The city where the transaction occurred.

nullable, string

The region or state where the transaction occurred. In API versions 2018-05-22 and earlier, this field is called `state`.

nullable, string

The postal code where the transaction occurred. In API versions 2018-05-22 and earlier, this field is called `zip`.

nullable, string

The ISO 3166-1 alpha-2 country code where the transaction occurred.

nullable, number

The latitude where the transaction occurred.

Format: `double`

nullable, number

The longitude where the transaction occurred.

Format: `double`

nullable, string

The merchant defined store number where the transaction occurred.

deprecated, string

The merchant name or transaction description.

Note: While Plaid does not currently plan to remove this field, it is a legacy field that is not actively maintained. Use `merchant_name` instead for the merchant name.

If the `transactions` object was returned by a Transactions endpoint such as `/transactions/sync` or `/transactions/get`, this field will always appear. If the `transactions` object was returned by an Assets endpoint such as `/asset_report/get` or `/asset_report/pdf/get`, this field will only appear in an Asset Report with Insights.

nullable, string

The merchant name, as enriched by Plaid from the `name` field. This is typically a more human-readable version of the merchant counterparty in the transaction. For some bank transactions (such as checks or account transfers) where there is no meaningful merchant name, this value will be `null`.

nullable, string

The string returned by the financial institution to describe the transaction. For transactions returned by `/transactions/sync` or `/transactions/get`, this field will only be included if the client has set `options.include_original_description` to `true`.

object

Transaction information specific to inter-bank transfers. If the transaction was not an inter-bank transfer, all fields will be `null`.

If the `transactions` object was returned by a Transactions endpoint such as `/transactions/sync` or `/transactions/get`, the `payment_meta` key will always appear, but no data elements are guaranteed. If the `transactions` object was returned by an Assets endpoint such as `/asset_report/get` or `/asset_report/pdf/get`, this field will only appear in an Asset Report with Insights.

nullable, string

The transaction reference number supplied by the financial institution.

nullable, string

The ACH PPD ID for the payer.

nullable, string

For transfers, the party that is receiving the transaction.

nullable, string

The party initiating a wire transfer. Will be `null` if the transaction is not a wire transfer.

nullable, string

For transfers, the party that is paying the transaction.

nullable, string

The type of transfer, e.g. 'ACH'

nullable, string

The name of the payment processor

nullable, string

The payer-supplied description of the transfer.

boolean

When `true`, identifies the transaction as pending or unsettled. Pending transaction details (name, type, amount, category ID) may change before they are settled. Not all institutions provide pending transactions.

nullable, string

The ID of a posted transaction's associated pending transaction, where applicable. Not all institutions provide pending transactions.

nullable, string

This field is not typically populated and only relevant when dealing with sub-accounts. A sub-account most commonly exists in cases where a single account is linked to multiple cards, each with its own card number and card holder name; each card will be considered a sub-account. If the account does have sub-accounts, this field will typically be some combination of the sub-account owner's name and/or the sub-account mask. The format of this field is not standardized and will vary based on institution.

string

The unique ID of the transaction. Like all Plaid identifiers, the `transaction_id` is case sensitive.

deprecated, string

Please use the `payment_channel` field, `transaction_type` will be deprecated in the future.

`digital:` transactions that took place online.

`place:` transactions that were made at a physical location.

`special:` transactions that relate to banks, e.g. fees or deposits.

`unresolved:` transactions that do not fit into the other three types.

Possible values: `digital`, `place`, `special`, `unresolved`

nullable, string

The URL of a logo associated with this transaction, if available. The logo will always be a 100×100 pixel PNG file.

nullable, string

The website associated with this transaction, if available.

nullable, string

The date that the transaction was authorized. For posted transactions, the `date` field will indicate the posted date, but `authorized_date` will indicate the day the transaction was authorized by the financial institution. If presenting transactions to the user in a UI, the `authorized_date`, when available, is generally preferable to use over the `date` field for posted transactions, as it will generally represent the date the user actually made the transaction. Dates are returned in an [ISO 8601](https://wikipedia.org/wiki/ISO_8601) format ( `YYYY-MM-DD` ).

Format: `date`

nullable, string

Date and time when a transaction was authorized in [ISO 8601](https://wikipedia.org/wiki/ISO_8601) format ( `YYYY-MM-DDTHH:mm:ssZ` ). For posted transactions, the `datetime` field will indicate the posted date, but `authorized_datetime` will indicate the day the transaction was authorized by the financial institution. If presenting transactions to the user in a UI, the `authorized_datetime`, when available, is generally preferable to use over the `datetime` field for posted transactions, as it will generally represent the date the user actually made the transaction.

This field is returned for select financial institutions and comes as provided by the institution. It may contain default time values (such as 00:00:00). This field is only populated in API version 2019-05-29 and later.

Format: `date-time`

nullable, string

Date and time when a transaction was posted in [ISO 8601](https://wikipedia.org/wiki/ISO_8601) format ( `YYYY-MM-DDTHH:mm:ssZ` ). For the date that the transaction was initiated, rather than posted, see the `authorized_datetime` field.

This field is returned for select financial institutions and comes as provided by the institution. It may contain default time values (such as 00:00:00). This field is only populated in API version 2019-05-29 and later.

Format: `date-time`

string

The channel used to make a payment. `online:` transactions that took place online.

`in store:` transactions that were made at a physical location.

`other:` transactions that relate to banks, e.g. fees or deposits.

This field replaces the `transaction_type` field.

Possible values: `online`, `in store`, `other`

nullable, object

Information describing the intent of the transaction. Most relevant for personal finance use cases, but not limited to such use cases.

See the [taxonomy CSV file](https://plaid.com/documents/pfc-taxonomy-all.csv) for a full list of personal finance categories. If you are migrating to personal finance categories from the legacy categories, also refer to the [migration guide](https://plaid.com/docs/transactions/pfc-migration/index.html.md) .

string

A high level category that communicates the broad category of the transaction.

string

A granular category conveying the transaction's intent. This field can also be used as a unique identifier for the category.

nullable, string

A description of how confident we are that the provided categories accurately describe the transaction intent.

`VERY_HIGH`: We are more than 98% confident that this category reflects the intent of the transaction. `HIGH`: We are more than 90% confident that this category reflects the intent of the transaction. `MEDIUM`: We are moderately confident that this category reflects the intent of the transaction. `LOW`: This category may reflect the intent, but there may be other categories that are more accurate. `UNKNOWN`: We don't know the confidence level for this category.

string

Indicates which version of the personal finance category taxonomy is being used. [View PFCv2 and PFCv1 taxonomies](https://plaid.com/documents/pfc-taxonomy-all.csv) .

If you enabled Transactions or Enrich before December 3, 2025 you will receive the `v1` taxonomy by default and may request `v2` by explicitly setting this field to `v2` in the request.

If you enabled Transactions or Enrich on or after December 3, 2025, you may only receive the `v2` taxonomy.

Possible values: `v1`, `v2`

nullable, string

An identifier classifying the transaction type.

This field is populated for European institutions, as well as certain institutions in the United States. For institutions where this classification is not available, this field is set to `null`.

`adjustment:` Bank adjustment

`atm:` Cash deposit or withdrawal via an automated teller machine

`bank charge:` Charge or fee levied by the institution

`bill payment`: Payment of a bill

`cash:` Cash deposit or withdrawal

`cash advance:` Cash advance drawn against a credit card or line of credit

`cashback:` Cash withdrawal while making a debit card purchase

`cheque:` Document ordering the payment of money to another person or organization

`direct debit:` Automatic withdrawal of funds initiated by a third party at a regular interval

`interest:` Interest earned or incurred

`late fee:` Fee associated with a late or past-due payment

`membership fee:` Annual or recurring membership fee

`payment:` One-off outbound payment not classified as a bill payment, direct debit, or standing order

`purchase:` Purchase made with a debit or credit card

`refund:` Merchant credit or return, such as a refund of a prior purchase

`returned item fee:` Fee for a returned item, such as a returned check or stop payment

`standing order:` Payment instructed by the account holder to a third party at a regular interval

`transfer:` Transfer of money between accounts

Possible values: `adjustment`, `atm`, `bank charge`, `bill payment`, `cash`, `cash advance`, `cashback`, `cheque`, `direct debit`, `interest`, `late fee`, `membership fee`, `payment`, `purchase`, `refund`, `returned item fee`, `standing order`, `transfer`, `null`

string

The URL of an icon associated with the primary personal finance category. The icon will always be a 100×100 pixel PNG file.

\[object\]

The counterparties present in the transaction. Counterparties, such as the merchant or the financial institution, are extracted by Plaid from the raw description.

string

The name of the counterparty, such as the merchant or the financial institution, as extracted by Plaid from the raw description.

nullable, string

A unique, stable, Plaid-generated ID that maps to the counterparty.

string

The counterparty type.

`merchant`: a provider of goods or services for purchase `financial_institution`: a financial entity (bank, credit union, BNPL, fintech) `payment_app`: a transfer or P2P app (e.g. Zelle) `marketplace`: a marketplace (e.g. DoorDash, Google Play Store) `payment_terminal`: a point-of-sale payment terminal (e.g. Square, Toast) `income_source`: the payer in an income transaction (e.g., an employer, client, or government agency)

Possible values: `merchant`, `financial_institution`, `payment_app`, `marketplace`, `payment_terminal`, `income_source`

nullable, string

The website associated with the counterparty.

nullable, string

The URL of a logo associated with the counterparty, if available. The logo will always be a 100×100 pixel PNG file.

nullable, string

A description of how confident we are that the provided counterparty is involved in the transaction.

`VERY_HIGH`: We recognize this counterparty and we are more than 98% confident that it is involved in this transaction. `HIGH`: We recognize this counterparty and we are more than 90% confident that it is involved in this transaction. `MEDIUM`: We are moderately confident that this counterparty was involved in this transaction, but some details may differ from our records. `LOW`: We didn't find a matching counterparty in our records, so we are returning a cleansed name parsed out of the request description. `UNKNOWN`: We don't know the confidence level for this counterparty.

nullable, object

Account numbers associated with the counterparty, when available. This field is currently only filled in for select financial institutions in Europe.

nullable, object

Identifying information for a UK bank account via Bacs.

nullable, string

The Bacs account number for the account.

nullable, string

The Bacs sort code for the account.

nullable, object

Account numbers using the International Bank Account Number and BIC/SWIFT code format.

nullable, string

International Bank Account Number (IBAN).

Min length: `15`

Max length: `34`

nullable, string

Business Identifier Code (BIC) for this counterparty.

Min length: `8`

Max length: `11`

nullable, string

A unique, stable, Plaid-generated ID that maps to the merchant. In the case of a merchant with multiple retail locations, this field will map to the broader merchant, not a specific location or store.

\[object\]

Transactions that have been removed from the Item since `cursor` ordered by ascending last modified time.

string

The ID of the removed transaction.

string

The ID of the account of the removed transaction.

string

Cursor used for fetching any future updates after the latest update provided in this response. The cursor obtained after all pages have been pulled (indicated by `has_more` being `false`) will be valid for at least 1 year. This cursor should be persisted for later calls. If transactions are not yet available, this will be an empty string.

If `account_id` is included in the request, the returned cursor will reflect updates for that specific account.

boolean

Represents if more than requested count of transaction updates exist. If true, the additional updates can be fetched by making an additional request with `cursor` set to `next_cursor`. If `has_more` is true, it's important to pull all available pages, to make it less likely for underlying data changes to conflict with pagination.

string

A unique identifier for the request, which can be used for troubleshooting. This identifier, like all Plaid identifiers, is case sensitive.

Response Object

```json
{
  "accounts": [
    {
      "account_id": "BxBXxLj1m4HMXBm9WZZmCWVbPjX16EHwv99vp",
      "balances": {
        "available": 110.94,
        "current": 110.94,
        "iso_currency_code": "USD",
        "limit": null,
        "unofficial_currency_code": null
      },
      "mask": "0000",
      "name": "Plaid Checking",
      "official_name": "Plaid Gold Standard 0% Interest Checking",
      "subtype": "checking",
      "type": "depository"
    }
  ],
  "added": [
    {
      "account_id": "BxBXxLj1m4HMXBm9WZZmCWVbPjX16EHwv99vp",
      "account_owner": null,
      "amount": 72.1,
      "iso_currency_code": "USD",
      "unofficial_currency_code": null,
      "check_number": null,
      "counterparties": [
        {
          "name": "Walmart",
          "type": "merchant",
          "logo_url": "https://plaid-merchant-logos.plaid.com/walmart_1100.png",
          "website": "walmart.com",
          "entity_id": "O5W5j4dN9OR3E6ypQmjdkWZZRoXEzVMz2ByWM",
          "confidence_level": "VERY_HIGH"
        }
      ],
      "date": "2023-09-24",
      "datetime": "2023-09-24T11:01:01Z",
      "authorized_date": "2023-09-22",
      "authorized_datetime": "2023-09-22T10:34:50Z",
      "location": {
        "address": "13425 Community Rd",
        "city": "Poway",
        "region": "CA",
        "postal_code": "92064",
        "country": "US",
        "lat": 32.959068,
        "lon": -117.037666,
        "store_number": "1700"
      },
      "name": "PURCHASE WM SUPERCENTER #1700",
      "merchant_name": "Walmart",
      "merchant_entity_id": "O5W5j4dN9OR3E6ypQmjdkWZZRoXEzVMz2ByWM",
      "logo_url": "https://plaid-merchant-logos.plaid.com/walmart_1100.png",
      "website": "walmart.com",
      "payment_meta": {
        "by_order_of": null,
        "payee": null,
        "payer": null,
        "payment_method": null,
        "payment_processor": null,
        "ppd_id": null,
        "reason": null,
        "reference_number": null
      },
      "payment_channel": "in store",
      "pending": false,
      "pending_transaction_id": "no86Eox18VHMvaOVL7gPUM9ap3aR1LsAVZ5nc",
      "personal_finance_category": {
        "primary": "GENERAL_MERCHANDISE",
        "detailed": "GENERAL_MERCHANDISE_SUPERSTORES",
        "confidence_level": "VERY_HIGH"
      },
      "personal_finance_category_icon_url": "https://plaid-category-icons.plaid.com/PFC_GENERAL_MERCHANDISE.png",
      "transaction_id": "lPNjeW1nR6CDn5okmGQ6hEpMo4lLNoSrzqDje",
      "transaction_code": null,
      "transaction_type": "place"
    }
  ],
  "modified": [
    {
      "account_id": "BxBXxLj1m4HMXBm9WZZmCWVbPjX16EHwv99vp",
      "account_owner": null,
      "amount": 28.34,
      "iso_currency_code": "USD",
      "unofficial_currency_code": null,
      "check_number": null,
      "counterparties": [
        {
          "name": "DoorDash",
          "type": "marketplace",
          "logo_url": "https://plaid-counterparty-logos.plaid.com/doordash_1.png",
          "website": "doordash.com",
          "entity_id": "YNRJg5o2djJLv52nBA1Yn1KpL858egYVo4dpm",
          "confidence_level": "HIGH"
        },
        {
          "name": "Burger King",
          "type": "merchant",
          "logo_url": "https://plaid-merchant-logos.plaid.com/burger_king_155.png",
          "website": "burgerking.com",
          "entity_id": "mVrw538wamwdm22mK8jqpp7qd5br0eeV9o4a1",
          "confidence_level": "VERY_HIGH"
        }
      ],
      "date": "2023-09-28",
      "datetime": "2023-09-28T15:10:09Z",
      "authorized_date": "2023-09-27",
      "authorized_datetime": "2023-09-27T08:01:58Z",
      "location": {
        "address": null,
        "city": null,
        "region": null,
        "postal_code": null,
        "country": null,
        "lat": null,
        "lon": null,
        "store_number": null
      },
      "name": "Dd Doordash Burgerkin",
      "merchant_name": "Burger King",
      "merchant_entity_id": "mVrw538wamwdm22mK8jqpp7qd5br0eeV9o4a1",
      "logo_url": "https://plaid-merchant-logos.plaid.com/burger_king_155.png",
      "website": "burgerking.com",
      "payment_meta": {
        "by_order_of": null,
        "payee": null,
        "payer": null,
        "payment_method": null,
        "payment_processor": null,
        "ppd_id": null,
        "reason": null,
        "reference_number": null
      },
      "payment_channel": "online",
      "pending": true,
      "pending_transaction_id": null,
      "personal_finance_category": {
        "primary": "FOOD_AND_DRINK",
        "detailed": "FOOD_AND_DRINK_FAST_FOOD",
        "confidence_level": "VERY_HIGH"
      },
      "personal_finance_category_icon_url": "https://plaid-category-icons.plaid.com/PFC_FOOD_AND_DRINK.png",
      "transaction_id": "yhnUVvtcGGcCKU0bcz8PDQr5ZUxUXebUvbKC0",
      "transaction_code": null,
      "transaction_type": "digital"
    }
  ],
  "removed": [
    {
      "account_id": "BxBXxLj1m4HMXBm9WZZmCWVbPjX16EHwv99vp",
      "transaction_id": "CmdQTNgems8BT1B7ibkoUXVPyAeehT3Tmzk0l"
    }
  ],
  "next_cursor": "tVUUL15lYQN5rBnfDIc1I8xudpGdIlw9nsgeXWvhOfkECvUeR663i3Dt1uf/94S8ASkitgLcIiOSqNwzzp+bh89kirazha5vuZHBb2ZA5NtCDkkV",
  "has_more": false,
  "request_id": "Wvhy9PZHQLV8njG",
  "transactions_update_status": "HISTORICAL_UPDATE_COMPLETE"
}
```

\=\*=\*=\*=

#### /transactions/get 

#### Get transaction data 

Note: All new implementations are encouraged to use [/transactions/sync](https://plaid.com/docs/api/products/transactions/index.html.md#transactionssync) rather than [/transactions/get](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsget) . [/transactions/sync](https://plaid.com/docs/api/products/transactions/index.html.md#transactionssync) provides the same functionality as [/transactions/get](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsget) and improves developer ease-of-use for handling transactions updates. The [/transactions/get](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsget) endpoint allows developers to receive user-authorized transaction data for credit, depository, and some loan-type accounts (only those with account subtype `student` or `mortgage`; coverage may be limited). For transaction history from investment accounts, use the [Investments endpoint](https://plaid.com/docs/api/products/investments/index.html.md) instead. Transaction data is standardized across financial institutions, and in many cases transactions are linked to a clean name, entity type, location, and category. Similarly, account data is standardized and returned with a clean name, number, balance, and other meta information where available. Transactions are returned in reverse-chronological order, and the sequence of transaction ordering is stable and will not shift. Transactions are not immutable and can also be removed altogether by the institution; a removed transaction will no longer appear in [/transactions/get](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsget) . For more details, see [Pending and posted transactions](https://plaid.com/docs/transactions/transactions-data/index.html.md#pending-and-posted-transactions) . Due to the potentially large number of transactions associated with an Item, results are paginated. Manipulate the `count` and `offset` parameters in conjunction with the `total_transactions` response body field to fetch all available transactions. Data returned by [/transactions/get](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsget) will be the data available for the Item as of the most recent successful check for new transactions. Plaid typically checks for new data multiple times a day, but these checks may occur less frequently, such as once a day, depending on the institution. To find out when the Item was last updated, use the [Item Debugger](https://plaid.com/docs/account/activity/index.html.md#troubleshooting-with-item-debugger) or call [/item/get](https://plaid.com/docs/api/items/index.html.md#itemget) ; the `item.status.transactions.last_successful_update` field will show the timestamp of the most recent successful update. To force Plaid to check for new transactions, you can use the [/transactions/refresh](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsrefresh) endpoint.

Note that data may not be immediately available to [/transactions/get](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsget) . Plaid will begin to prepare transactions data upon Item link, if Link was initialized with `transactions`, or upon the first call to [/transactions/get](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsget) , if it wasn't. To be alerted when transaction data is ready to be fetched, listen for the [INITIAL\_UPDATE](https://plaid.com/docs/api/products/transactions/index.html.md#initial_update) and [HISTORICAL\_UPDATE](https://plaid.com/docs/api/products/transactions/index.html.md#historical_update) webhooks. If no transaction history is ready when [/transactions/get](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsget) is called, it will return a `PRODUCT_NOT_READY` error.

#### Request fields 

string

Your Plaid API `client_id`. The `client_id` is required and may be provided either in the `PLAID-CLIENT-ID` header or as part of a request body.

object

An optional object to be used with the request. If specified, `options` must not be `null`.

\[string\]

A list of `account_ids` to retrieve for the Item

Note: An error will be returned if a provided `account_id` is not associated with the Item.

integer

The number of transactions to fetch.

Default: `100`

Minimum: `1`

Maximum: `500`

Exclusive min: `false`

integer

The number of transactions to skip. The default value is 0.

Default: `0`

Minimum: `0`

boolean

Include the raw unparsed transaction description from the financial institution.

Default: `false`

string

Indicates which version of the personal finance category taxonomy is being used. [View PFCv2 and PFCv1 taxonomies](https://plaid.com/documents/pfc-taxonomy-all.csv) .

If you enabled Transactions or Enrich before December 3, 2025 you will receive the `v1` taxonomy by default and may request `v2` by explicitly setting this field to `v2` in the request.

If you enabled Transactions or Enrich on or after December 3, 2025, you may only receive the `v2` taxonomy.

Possible values: `v1`, `v2`

integer

This field only applies to calls for Items where the Transactions product has not already been initialized (i.e. by specifying `transactions` in the `products`, `optional_products`, or `required_if_supported_products` array when calling `/link/token/create` or by making a previous call to `/transactions/sync` or `/transactions/get`). In those cases, the field controls the maximum number of days of transaction history that Plaid will request from the financial institution. The more transaction history is requested, the longer the historical update poll will take. If no value is specified, 90 days of history will be requested by default. In Production, if a value under 30 is provided, a minimum of 30 days of history will be requested.

If you are initializing your Items with transactions during the `/link/token/create` call (e.g. by including `transactions` in the `/link/token/create` `products` array), you must use the [transactions.days\_requested](https://plaid.com/docs/api/link/index.html.md#link-token-create-request-transactions-days-requested) field in the `/link/token/create` request instead of in the `/transactions/get` request.

If the Item has already been initialized with the Transactions product, this field will have no effect. The maximum amount of transaction history to request on an Item cannot be updated if Transactions has already been added to the Item. To request older transaction history on an Item where Transactions has already been added, you must delete the Item via `/item/remove` and send the user through Link to create a new Item.

Customers using [Recurring Transactions](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsrecurringget) should request at least 180 days of history for optimal results.

Minimum: `1`

Maximum: `730`

Default: `90`

required, string

The access token associated with the Item for which data is being requested.

string

Your Plaid API `secret`. The `secret` is required and may be provided either in the `PLAID-SECRET` header or as part of a request body.

required, string

The earliest date for which data should be returned. Dates should be formatted as YYYY-MM-DD.

Format: `date`

required, string

The latest date for which data should be returned. Dates should be formatted as YYYY-MM-DD.

Format: `date`

```node
const request: TransactionsGetRequest = {
  access_token: accessToken,
  start_date: '2018-01-01',
  end_date: '2020-02-01',
};
try {
  const response = await client.transactionsGet(request);
  let transactions = response.data.transactions;
  const total_transactions = response.data.total_transactions;
  // Manipulate the offset parameter to paginate
  // transactions and retrieve all available data
  while (transactions.length < total_transactions) {
    const paginatedRequest: TransactionsGetRequest = {
      access_token: accessToken,
      start_date: '2018-01-01',
      end_date: '2020-02-01',
      options: {
        offset: transactions.length,
      },
    };
    const paginatedResponse = await client.transactionsGet(paginatedRequest);
    transactions = transactions.concat(paginatedResponse.data.transactions);
  }
} catch (err) {
  // handle error
}

```

```bash
curl -X POST https://sandbox.plaid.com/transactions/get \
-H 'Content-Type: application/json' \
-d '{
  "client_id": "${PLAID_CLIENT_ID}",
  "secret": "${PLAID_SECRET}",
  "access_token": String,
  "start_date": "2018-01-01",
  "end_date": "2018-02-01",
  "options": {
    "count": 250,
    "offset": 100
  }
}'

```

```ruby
start_date = (Date.today - 30)
end_date = Date.today
# Pull transactions for a date range
request = Plaid::TransactionsGetRequest.new(
  {
    access_token: access_token,
    start_date: start_date,
    end_date: end_date
  }
)
response = client.transactions_get(request)
transactions = response.transactions

# Manipulate the offset parameter to paginate
# transactions and retrieve all available data
while transactions.length < response.total_transactions
  request = Plaid::TransactionsGetRequest.new(
    {
    access_token: access_token,
    start_date: start_date,
    end_date: end_date,
    options: {
      offset: transactions.length
    }
    }
  )
  response = client.transactions_get(request)
  transactions += response.transactions
end

```

```java
LocalDate startDate = LocalDate.now().minusDays(30);
LocalDate endDate = LocalDate.now();
// Pull transactions for a date range
TransactionsGetRequest request = new TransactionsGetRequest()
  .accessToken(accessToken)
  .startDate(startDate)
  .endDate(endDate);
Response response =
  plaidClient.transactionsGet(request).execute();

List transactions = new ArrayList();
transactions.addAll(response.body().getTransactions());

// Manipulate the offset parameter to paginate
// transactions and retrieve all available data
while (transactions.size() < response.body().getTotalTransactions()) {
  TransactionsGetRequestOptions options = new TransactionsGetRequestOptions()
    .offset(transactions.size());
  request = new TransactionsGetRequest()
    .accessToken(accessToken)
    .startDate(startDate)
    .endDate(endDate)
    .options(options);

  response = plaidClient.transactionsGet(request).execute();
  transactions.addAll(response.body().getTransactions());
}

```

```python
request = TransactionsGetRequest(
            access_token=access_token,
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2021, 2, 1)
)
response = client.transactions_get(request)
transactions = response['transactions']

# Manipulate the count and offset parameters to paginate
# transactions and retrieve all available data
while len(transactions) < response['total_transactions']:
  request = TransactionsGetRequest(
              access_token=access_token,
              start_date=datetime.date(2018, 1, 1),
              end_date=datetime.date(2018, 2, 1),
              options=TransactionsGetRequestOptions(
                offset=len(transactions)
              )
  )
  response = client.transactions_get(request)
  transactions.extend(response['transactions'])

```

```go
const iso8601TimeFormat = "2006-01-02"
startDate := time.Now().Add(-365 * 24 * time.Hour).Format(iso8601TimeFormat)
endDate := time.Now().Format(iso8601TimeFormat)

request := plaid.NewTransactionsGetRequest(
  accessToken,
  startDate,
  endDate,
)

options := plaid.NewTransactionsGetRequestOptions()
options.SetCount(100)
options.SetOffset(0)

request.SetOptions(*options)

transactionsResp, _, err := client.PlaidApi.TransactionsGet(ctx).TransactionsGetRequest(*request).Execute()

```

#### Response fields 

\[object\]

An array containing the `accounts` associated with the Item for which transactions are being returned. Each transaction can be mapped to its corresponding account via the `account_id` field.

string

Plaid's unique identifier for the account. This value will not change unless Plaid can't reconcile the account with the data returned by the financial institution. This may occur, for example, when the name of the account changes. If this happens a new `account_id` will be assigned to the account.

The `account_id` can also change if the `access_token` is deleted and the same credentials that were used to generate that `access_token` are used to generate a new `access_token` on a later date. In that case, the new `account_id` will be different from the old `account_id`.

If an account with a specific `account_id` disappears instead of changing, the account is likely closed. Closed accounts are not returned by the Plaid API.

When using a CRA endpoint (an endpoint associated with Plaid Check Consumer Report, i.e. any endpoint beginning with `/cra/`), the `account_id` returned will not match the `account_id` returned by a non-CRA endpoint.

Like all Plaid identifiers, the `account_id` is case sensitive.

object

A set of fields describing the balance for an account. For real-time values, use `/accounts/balance/get` or `/signal/evaluate` (with a Balance-only ruleset), which are fetched live from the institution at request time. Values returned by other endpoints may be cached, or adjusted by Plaid to reflect transaction activity received since the last refresh.

nullable, number

The amount of funds available to be withdrawn from the account, as determined by the financial institution.

For `credit`\-type accounts, the `available` balance typically equals the `limit` less the `current` balance, less any pending outflows plus any pending inflows.

For `depository`\-type accounts, the `available` balance typically equals the `current` balance less any pending outflows plus any pending inflows. For `depository`\-type accounts, the `available` balance does not include the overdraft limit.

For `investment`\-type accounts (or `brokerage`\-type accounts for API versions 2018-05-22 and earlier), the `available` balance is the total cash available to withdraw as presented by the institution.

Note that not all institutions calculate the `available` balance. In the event that `available` balance is unavailable, Plaid will return an `available` balance value of `null`.

Available balance may be cached and is not guaranteed to be up-to-date in real-time unless the value was returned by `/accounts/balance/get`, or by `/signal/evaluate` with a Balance-only ruleset.

If `current` is `null` this field is guaranteed not to be `null`, unless you have opted into enabling [limited-purpose checking accounts](https://plaid.com/docs/auth/index.html.md#enabling-limited-purpose-checking-accounts-for-rent-or-mortgage) , which always have `null` values for both `available` and `current` balance.

Format: `double`

nullable, number

The total amount of funds in or owed by the account.

For `credit`\-type accounts, a positive balance indicates the amount owed; a negative amount indicates the lender owing the account holder.

For `loan`\-type accounts, the current balance is the principal remaining on the loan, except in the case of student loan accounts at Sallie Mae (`ins_116944`). For Sallie Mae student loans, the account's balance includes both principal and any outstanding interest. Similar to `credit`\-type accounts, a positive balance is typically expected, while a negative amount indicates the lender owing the account holder.

For `investment`\-type accounts (or `brokerage`\-type accounts for API versions 2018-05-22 and earlier), the current balance is the total value of assets as presented by the institution.

Note that balance information may be cached unless the value was returned by `/accounts/balance/get` or by `/signal/evaluate` with a Balance-only ruleset; if the Item is enabled for Transactions, the balance will be at least as recent as the most recent Transaction update. If you require real-time balance information, use the `available` balance as provided by `/accounts/balance/get` or `/signal/evaluate` called with a Balance-only `ruleset_key`.

When returned by `/accounts/balance/get`, this field may be `null`. When this happens, `available` is guaranteed not to be `null`, unless you have opted into enabling [limited-purpose checking accounts](https://plaid.com/docs/auth/index.html.md#enabling-limited-purpose-checking-accounts-for-rent-or-mortgage) , which always have `null` values for both `available` and `current` balance.

Format: `double`

nullable, number

For `credit`\-type accounts, this represents the credit limit.

For `depository`\-type accounts, this represents the pre-arranged overdraft limit, which is common for current (checking) accounts in Europe.

In North America, this field is typically only available for `credit`\-type accounts.

Format: `double`

nullable, string

The ISO-4217 currency code of the balance. Always null if `unofficial_currency_code` is non-null.

nullable, string

The unofficial currency code associated with the balance. Always null if `iso_currency_code` is non-null. Unofficial currency codes are used for currencies that do not have official ISO currency codes, such as cryptocurrencies and the currencies of certain countries.

See the [currency code schema](https://plaid.com/docs/api/accounts/index.html.md#currency-code-schema) for a full listing of supported `unofficial_currency_code`s.

nullable, string

Timestamp in [ISO 8601](https://en.wikipedia.org/wiki/ISO_8601) format (`YYYY-MM-DDTHH:mm:ssZ`) indicating the last time the balance was updated.

This field is returned only when the institution is `ins_128026` (Capital One).

Format: `date-time`

nullable, string

The last 2-4 alphanumeric characters of either the account's displayed mask or the account's official account number. Note that the mask may be non-unique between an Item's accounts.

string

The name of the account, either assigned by the user or by the financial institution itself

nullable, string

The official name of the account as given by the financial institution

string

`investment:` Investment account. In API versions 2018-05-22 and earlier, this type is called `brokerage` instead.

`credit:` Credit card

`depository:` Depository account

`loan:` Loan account

`other:` Non-specified account type

See the [Account type schema](https://plaid.com/docs/api/accounts/index.html.md#account-type-schema) for a full listing of account types and corresponding subtypes.

Possible values: `investment`, `credit`, `depository`, `loan`, `brokerage`, `other`

nullable, string

See the [Account type schema](https://plaid.com/docs/api/accounts/index.html.md#account-type-schema) for a full listing of account types and corresponding subtypes.

Possible values: `401a`, `401k`, `403B`, `457b`, `529`, `auto`, `brokerage`, `business`, `cash isa`, `cash management`, `cd`, `checking`, `commercial`, `construction`, `consumer`, `credit card`, `crypto exchange`, `ebt`, `education savings account`, `fhsa`, `fixed annuity`, `gic`, `health reimbursement arrangement`, `home equity`, `hsa`, `isa`, `ira`, `keogh`, `lif`, `life insurance`, `limited purpose checking`, `line of credit`, `lira`, `loan`, `lrif`, `lrsp`, `money market`, `mortgage`, `mutual fund`, `non-custodial wallet`, `non-taxable brokerage account`, `other`, `other insurance`, `other annuity`, `overdraft`, `paypal`, `payroll`, `pension`, `prepaid`, `prif`, `profit sharing plan`, `qshr`, `rdsp`, `resp`, `retirement`, `rlif`, `roth`, `roth 401k`, `roth 403B`, `roth 457b`, `roth pension`, `roth profit sharing plan`, `roth thrift savings plan`, `rrif`, `rrsp`, `sarsep`, `savings`, `sep ira`, `simple ira`, `sipp`, `stock plan`, `student`, `thrift savings plan`, `tfsa`, `trust`, `ugma`, `utma`, `variable annuity`

string

Indicates an Item's micro-deposit-based verification or database verification status. This field is only populated when using Auth and falling back to micro-deposit or database verification. Possible values are:

`pending_automatic_verification`: The Item is pending automatic verification.

`pending_manual_verification`: The Item is pending manual micro-deposit verification. Items remain in this state until the user successfully verifies the code.

`automatically_verified`: The Item has successfully been automatically verified.

`manually_verified`: The Item has successfully been manually verified.

`verification_expired`: Plaid was unable to automatically verify the deposit within 7 calendar days and will no longer attempt to validate the Item. Users may retry by submitting their information again through Link.

`verification_failed`: The Item failed manual micro-deposit verification because the user exhausted all 3 verification attempts. Users may retry by submitting their information again through Link.

`unsent`: The Item is pending micro-deposit verification, but Plaid has not yet sent the micro-deposit.

`database_insights_fail`: The Item's numbers have been verified using Plaid's data sources and have signal for being invalid and/or have no signal for being valid. Typically this indicates that the routing number is invalid, the account number does not match the account number format associated with the routing number, or the account has been reported as closed or frozen. Only returned for Auth Items created via Database Auth.

`database_insights_pass`: The Item's numbers have been verified using Plaid's data sources: the routing and account number match a routing and account number of an account recognized on the Plaid network, and the account is not known by Plaid to be frozen or closed. Only returned for Auth Items created via Database Auth.

`database_insights_pass_with_caution`: The Item's numbers have been verified using Plaid's data sources and have some signal for being valid: the routing and account number were not recognized on the Plaid network, but the routing number is valid and the account number is a potential valid account number for that routing number. Only returned for Auth Items created via Database Auth.

`database_matched`: (deprecated) The Item has successfully been verified using Plaid's data sources. Only returned for Auth Items created via Database Match.

`null` or empty string: Neither micro-deposit-based verification nor database verification are being used for the Item.

Possible values: `automatically_verified`, `pending_automatic_verification`, `pending_manual_verification`, `unsent`, `manually_verified`, `verification_expired`, `verification_failed`, `database_matched`, `database_insights_pass`, `database_insights_pass_with_caution`, `database_insights_fail`

string

The account holder name that was used for micro-deposit and/or database verification. Only returned for Auth Items created via micro-deposit or database verification. This name was manually-entered by the user during Link, unless it was otherwise provided via the `user.legal_name` request field in `/link/token/create` for the Link session that created the Item.

object

Insights from performing database verification for the account. Only returned for Auth Items using Database Auth.

nullable, integer

Indicates the score of the name match between the given name provided during database verification (available in the [verification\_name](https://plaid.com/docs/api/products/auth/index.html.md#auth-get-response-accounts-verification-name) field if using standard Database Auth, or provided in the request if using `/auth/verify`) and matched Plaid network accounts. If defined, will be a value between 0 and 100. Will be undefined if name matching was not enabled for the database verification session or if there were no eligible Plaid network matches to compare the given name with.

object

Status information about the account and routing number in the Plaid network.

boolean

Indicates whether we found at least one matching account for the ACH account and routing number.

boolean

Indicates if at least one matching account for the ACH account and routing number is already verified.

object

Information about known ACH returns for the account and routing number.

boolean

Indicates whether Plaid's data sources include a known administrative ACH return for this account and routing number.

string

Indicator of account number format validity for institution.

`valid`: indicates that the account number has a correct format for the institution.

`invalid`: indicates that the account number has an incorrect format for the institution.

`unknown`: indicates that there was not enough information to determine whether the format is correct for the institution.

Possible values: `valid`, `invalid`, `unknown`

string

A unique and persistent identifier for accounts that can be used to trace multiple instances of the same account across different Items for depository accounts. This field is currently supported only for Items at institutions that use Tokenized Account Numbers (i.e., Chase, PNC, and US Bank). Because these accounts have a different account number each time they are linked, this field may be used instead of the account number to uniquely identify an account across multiple Items for payments use cases, helping to reduce duplicate Items or attempted fraud. In Sandbox, this field is populated for TAN-based institutions (`ins_56`, `ins_13`, `ins_127990`) as well as the OAuth Sandbox institution (`ins_127287`); in Production, it will only be populated for accounts at applicable institutions.

nullable, string

Indicates the account's categorization as either a personal or a business account. This field is currently in beta; to request access, contact your account manager.

Possible values: `business`, `personal`, `unrecognized`

\[object\]

An array containing transactions from the account. Transactions are returned in reverse chronological order, with the most recent at the beginning of the array. The maximum number of transactions returned is determined by the `count` parameter.

string

The ID of the account in which this transaction occurred.

number

The settled value of the transaction, denominated in the transaction's currency, as stated in `iso_currency_code` or `unofficial_currency_code`. For all products except Income: Positive values when money moves out of the account; negative values when money moves in. For example, debit card purchases are positive; credit card payments, direct deposits, and refunds are negative. For Income endpoints, values are positive when representing income.

Format: `double`

nullable, string

The ISO-4217 currency code of the transaction. Always `null` if `unofficial_currency_code` is non-null.

nullable, string

The unofficial currency code associated with the transaction. Always `null` if `iso_currency_code` is non-`null`. Unofficial currency codes are used for currencies that do not have official ISO currency codes, such as cryptocurrencies and the currencies of certain countries.

See the [currency code schema](https://plaid.com/docs/api/accounts/index.html.md#currency-code-schema) for a full listing of supported `unofficial_currency_code`s.

nullable, string

The check number of the transaction. This field is only populated for check transactions.

string

For pending transactions, the date that the transaction occurred; for posted transactions, the date that the transaction posted. Both dates are returned in an [ISO 8601](https://wikipedia.org/wiki/ISO_8601) format ( `YYYY-MM-DD` ). To receive information about the date that a posted transaction was initiated, see the `authorized_date` field.

Format: `date`

object

A representation of where a transaction took place. Location data is provided only for transactions at physical locations, not for online transactions. Location data availability depends primarily on the merchant and is most likely to be populated for transactions at large retail chains; small, local businesses are less likely to have location data available.

nullable, string

The street address where the transaction occurred.

nullable, string

The city where the transaction occurred.

nullable, string

The region or state where the transaction occurred. In API versions 2018-05-22 and earlier, this field is called `state`.

nullable, string

The postal code where the transaction occurred. In API versions 2018-05-22 and earlier, this field is called `zip`.

nullable, string

The ISO 3166-1 alpha-2 country code where the transaction occurred.

nullable, number

The latitude where the transaction occurred.

Format: `double`

nullable, number

The longitude where the transaction occurred.

Format: `double`

nullable, string

The merchant defined store number where the transaction occurred.

deprecated, string

The merchant name or transaction description.

Note: While Plaid does not currently plan to remove this field, it is a legacy field that is not actively maintained. Use `merchant_name` instead for the merchant name.

If the `transactions` object was returned by a Transactions endpoint such as `/transactions/sync` or `/transactions/get`, this field will always appear. If the `transactions` object was returned by an Assets endpoint such as `/asset_report/get` or `/asset_report/pdf/get`, this field will only appear in an Asset Report with Insights.

nullable, string

The merchant name, as enriched by Plaid from the `name` field. This is typically a more human-readable version of the merchant counterparty in the transaction. For some bank transactions (such as checks or account transfers) where there is no meaningful merchant name, this value will be `null`.

nullable, string

The string returned by the financial institution to describe the transaction. For transactions returned by `/transactions/sync` or `/transactions/get`, this field will only be included if the client has set `options.include_original_description` to `true`.

object

Transaction information specific to inter-bank transfers. If the transaction was not an inter-bank transfer, all fields will be `null`.

If the `transactions` object was returned by a Transactions endpoint such as `/transactions/sync` or `/transactions/get`, the `payment_meta` key will always appear, but no data elements are guaranteed. If the `transactions` object was returned by an Assets endpoint such as `/asset_report/get` or `/asset_report/pdf/get`, this field will only appear in an Asset Report with Insights.

nullable, string

The transaction reference number supplied by the financial institution.

nullable, string

The ACH PPD ID for the payer.

nullable, string

For transfers, the party that is receiving the transaction.

nullable, string

The party initiating a wire transfer. Will be `null` if the transaction is not a wire transfer.

nullable, string

For transfers, the party that is paying the transaction.

nullable, string

The type of transfer, e.g. 'ACH'

nullable, string

The name of the payment processor

nullable, string

The payer-supplied description of the transfer.

boolean

When `true`, identifies the transaction as pending or unsettled. Pending transaction details (name, type, amount, category ID) may change before they are settled. Not all institutions provide pending transactions.

nullable, string

The ID of a posted transaction's associated pending transaction, where applicable. Not all institutions provide pending transactions.

nullable, string

This field is not typically populated and only relevant when dealing with sub-accounts. A sub-account most commonly exists in cases where a single account is linked to multiple cards, each with its own card number and card holder name; each card will be considered a sub-account. If the account does have sub-accounts, this field will typically be some combination of the sub-account owner's name and/or the sub-account mask. The format of this field is not standardized and will vary based on institution.

string

The unique ID of the transaction. Like all Plaid identifiers, the `transaction_id` is case sensitive.

deprecated, string

Please use the `payment_channel` field, `transaction_type` will be deprecated in the future.

`digital:` transactions that took place online.

`place:` transactions that were made at a physical location.

`special:` transactions that relate to banks, e.g. fees or deposits.

`unresolved:` transactions that do not fit into the other three types.

Possible values: `digital`, `place`, `special`, `unresolved`

nullable, string

The URL of a logo associated with this transaction, if available. The logo will always be a 100×100 pixel PNG file.

nullable, string

The website associated with this transaction, if available.

nullable, string

The date that the transaction was authorized. For posted transactions, the `date` field will indicate the posted date, but `authorized_date` will indicate the day the transaction was authorized by the financial institution. If presenting transactions to the user in a UI, the `authorized_date`, when available, is generally preferable to use over the `date` field for posted transactions, as it will generally represent the date the user actually made the transaction. Dates are returned in an [ISO 8601](https://wikipedia.org/wiki/ISO_8601) format ( `YYYY-MM-DD` ).

Format: `date`

nullable, string

Date and time when a transaction was authorized in [ISO 8601](https://wikipedia.org/wiki/ISO_8601) format ( `YYYY-MM-DDTHH:mm:ssZ` ). For posted transactions, the `datetime` field will indicate the posted date, but `authorized_datetime` will indicate the day the transaction was authorized by the financial institution. If presenting transactions to the user in a UI, the `authorized_datetime`, when available, is generally preferable to use over the `datetime` field for posted transactions, as it will generally represent the date the user actually made the transaction.

This field is returned for select financial institutions and comes as provided by the institution. It may contain default time values (such as 00:00:00). This field is only populated in API version 2019-05-29 and later.

Format: `date-time`

nullable, string

Date and time when a transaction was posted in [ISO 8601](https://wikipedia.org/wiki/ISO_8601) format ( `YYYY-MM-DDTHH:mm:ssZ` ). For the date that the transaction was initiated, rather than posted, see the `authorized_datetime` field.

This field is returned for select financial institutions and comes as provided by the institution. It may contain default time values (such as 00:00:00). This field is only populated in API version 2019-05-29 and later.

Format: `date-time`

string

The channel used to make a payment. `online:` transactions that took place online.

`in store:` transactions that were made at a physical location.

`other:` transactions that relate to banks, e.g. fees or deposits.

This field replaces the `transaction_type` field.

Possible values: `online`, `in store`, `other`

nullable, object

Information describing the intent of the transaction. Most relevant for personal finance use cases, but not limited to such use cases.

See the [taxonomy CSV file](https://plaid.com/documents/pfc-taxonomy-all.csv) for a full list of personal finance categories. If you are migrating to personal finance categories from the legacy categories, also refer to the [migration guide](https://plaid.com/docs/transactions/pfc-migration/index.html.md) .

string

A high level category that communicates the broad category of the transaction.

string

A granular category conveying the transaction's intent. This field can also be used as a unique identifier for the category.

nullable, string

A description of how confident we are that the provided categories accurately describe the transaction intent.

`VERY_HIGH`: We are more than 98% confident that this category reflects the intent of the transaction. `HIGH`: We are more than 90% confident that this category reflects the intent of the transaction. `MEDIUM`: We are moderately confident that this category reflects the intent of the transaction. `LOW`: This category may reflect the intent, but there may be other categories that are more accurate. `UNKNOWN`: We don't know the confidence level for this category.

string

Indicates which version of the personal finance category taxonomy is being used. [View PFCv2 and PFCv1 taxonomies](https://plaid.com/documents/pfc-taxonomy-all.csv) .

If you enabled Transactions or Enrich before December 3, 2025 you will receive the `v1` taxonomy by default and may request `v2` by explicitly setting this field to `v2` in the request.

If you enabled Transactions or Enrich on or after December 3, 2025, you may only receive the `v2` taxonomy.

Possible values: `v1`, `v2`

nullable, string

An identifier classifying the transaction type.

This field is populated for European institutions, as well as certain institutions in the United States. For institutions where this classification is not available, this field is set to `null`.

`adjustment:` Bank adjustment

`atm:` Cash deposit or withdrawal via an automated teller machine

`bank charge:` Charge or fee levied by the institution

`bill payment`: Payment of a bill

`cash:` Cash deposit or withdrawal

`cash advance:` Cash advance drawn against a credit card or line of credit

`cashback:` Cash withdrawal while making a debit card purchase

`cheque:` Document ordering the payment of money to another person or organization

`direct debit:` Automatic withdrawal of funds initiated by a third party at a regular interval

`interest:` Interest earned or incurred

`late fee:` Fee associated with a late or past-due payment

`membership fee:` Annual or recurring membership fee

`payment:` One-off outbound payment not classified as a bill payment, direct debit, or standing order

`purchase:` Purchase made with a debit or credit card

`refund:` Merchant credit or return, such as a refund of a prior purchase

`returned item fee:` Fee for a returned item, such as a returned check or stop payment

`standing order:` Payment instructed by the account holder to a third party at a regular interval

`transfer:` Transfer of money between accounts

Possible values: `adjustment`, `atm`, `bank charge`, `bill payment`, `cash`, `cash advance`, `cashback`, `cheque`, `direct debit`, `interest`, `late fee`, `membership fee`, `payment`, `purchase`, `refund`, `returned item fee`, `standing order`, `transfer`, `null`

string

The URL of an icon associated with the primary personal finance category. The icon will always be a 100×100 pixel PNG file.

\[object\]

The counterparties present in the transaction. Counterparties, such as the merchant or the financial institution, are extracted by Plaid from the raw description.

string

The name of the counterparty, such as the merchant or the financial institution, as extracted by Plaid from the raw description.

nullable, string

A unique, stable, Plaid-generated ID that maps to the counterparty.

string

The counterparty type.

`merchant`: a provider of goods or services for purchase `financial_institution`: a financial entity (bank, credit union, BNPL, fintech) `payment_app`: a transfer or P2P app (e.g. Zelle) `marketplace`: a marketplace (e.g. DoorDash, Google Play Store) `payment_terminal`: a point-of-sale payment terminal (e.g. Square, Toast) `income_source`: the payer in an income transaction (e.g., an employer, client, or government agency)

Possible values: `merchant`, `financial_institution`, `payment_app`, `marketplace`, `payment_terminal`, `income_source`

nullable, string

The website associated with the counterparty.

nullable, string

The URL of a logo associated with the counterparty, if available. The logo will always be a 100×100 pixel PNG file.

nullable, string

A description of how confident we are that the provided counterparty is involved in the transaction.

`VERY_HIGH`: We recognize this counterparty and we are more than 98% confident that it is involved in this transaction. `HIGH`: We recognize this counterparty and we are more than 90% confident that it is involved in this transaction. `MEDIUM`: We are moderately confident that this counterparty was involved in this transaction, but some details may differ from our records. `LOW`: We didn't find a matching counterparty in our records, so we are returning a cleansed name parsed out of the request description. `UNKNOWN`: We don't know the confidence level for this counterparty.

nullable, object

Account numbers associated with the counterparty, when available. This field is currently only filled in for select financial institutions in Europe.

nullable, object

Identifying information for a UK bank account via Bacs.

nullable, string

The Bacs account number for the account.

nullable, string

The Bacs sort code for the account.

nullable, object

Account numbers using the International Bank Account Number and BIC/SWIFT code format.

nullable, string

International Bank Account Number (IBAN).

Min length: `15`

Max length: `34`

nullable, string

Business Identifier Code (BIC) for this counterparty.

Min length: `8`

Max length: `11`

nullable, string

A unique, stable, Plaid-generated ID that maps to the merchant. In the case of a merchant with multiple retail locations, this field will map to the broader merchant, not a specific location or store.

integer

The total number of transactions available within the date range specified. If `total_transactions` is larger than the size of the `transactions` array, more transactions are available and can be fetched via manipulating the `offset` parameter.

object

Metadata about the Item.

string

The Plaid Item ID. The `item_id` is always unique; linking the same account at the same institution twice will result in two Items with different `item_id` values. Like all Plaid identifiers, the `item_id` is case-sensitive.

nullable, string

The Plaid Institution ID associated with the Item. Field is `null` for Items created without an institution connection, such as Items created via Same-Day Micro-deposits.

nullable, string

The name of the institution associated with the Item. Field is `null` for Items created without an institution connection, such as Items created via Same-Day Micro-deposits.

nullable, string

The URL registered to receive webhooks for the Item.

nullable, string

The method used to populate Auth data for the Item. This field is only populated for Items that have had Auth numbers data set on at least one of their accounts, and will be `null` otherwise. For info about the various flows, see our [Auth coverage documentation](https://plaid.com/docs/auth/coverage/index.html.md) .

`INSTANT_AUTH`: The Item's Auth data was provided directly by the user's institution connection.

`INSTANT_MATCH`: The Item's Auth data was provided via the Instant Match fallback flow.

`AUTOMATED_MICRODEPOSITS`: The Item's Auth data was provided via the Automated Micro-deposits flow.

`SAME_DAY_MICRODEPOSITS`: The Item's Auth data was provided via the Same-Day Micro-deposits flow.

`INSTANT_MICRODEPOSITS`: The Item's Auth data was provided via the Instant Micro-deposits flow.

`DATABASE_MATCH`: The Item's Auth data was provided via the Database Match flow.

`DATABASE_INSIGHTS`: The Item's Auth data was provided via the Database Insights flow.

`TRANSFER_MIGRATED`: The Item's Auth data was provided via [/transfer/migrate\_account](https://plaid.com/docs/api/products/transfer/account-linking/index.html.md#migrate-account-into-transfers) .

`INVESTMENTS_FALLBACK`: The Item's Auth data for Investments Move was provided via a [fallback flow](https://plaid.com/docs/investments-move/index.html.md#fallback-flows) .

Possible values: `INSTANT_AUTH`, `INSTANT_MATCH`, `AUTOMATED_MICRODEPOSITS`, `SAME_DAY_MICRODEPOSITS`, `INSTANT_MICRODEPOSITS`, `DATABASE_MATCH`, `DATABASE_INSIGHTS`, `TRANSFER_MIGRATED`, `INVESTMENTS_FALLBACK`, `null`

nullable, object

Errors are identified by `error_code` and categorized by `error_type`. Use these in preference to HTTP status codes to identify and handle specific errors. HTTP status codes are set and provide the broadest categorization of errors: 4xx codes are for developer- or user-related errors, and 5xx codes are for Plaid-related errors, and the status will be 2xx in non-error cases. An Item with a non-`null` error object will only be part of an API response when calling `/item/get` to view Item status. Otherwise, error fields will be `null` if no error has occurred; if an error has occurred, an error code will be returned instead.

string

A broad categorization of the error. Safe for programmatic use.

Possible values: `INVALID_REQUEST`, `INVALID_RESULT`, `INVALID_INPUT`, `INSTITUTION_ERROR`, `RATE_LIMIT_EXCEEDED`, `API_ERROR`, `ITEM_ERROR`, `ASSET_REPORT_ERROR`, `BASE_REPORT_ERROR`, `RECAPTCHA_ERROR`, `OAUTH_ERROR`, `PAYMENT_ERROR`, `BANK_TRANSFER_ERROR`, `INCOME_VERIFICATION_ERROR`, `MICRODEPOSITS_ERROR`, `SANDBOX_ERROR`, `PARTNER_ERROR`, `SIGNAL_ERROR`, `TRANSACTIONS_ERROR`, `TRANSACTION_ERROR`, `TRANSFER_ERROR`, `CHECK_REPORT_ERROR`, `CONSUMER_REPORT_ERROR`, `USER_ERROR`, `IDEMPOTENCY_ERROR`, `ASSETS_ERROR`, `CRA_MONITORING_ERROR`, `CREDIT_PROFILE_REPORT_ERROR`, `ENCOMPASS_ERROR`, `ENRICH_ERROR`, `FRAUD_INSIGHTS_ERROR`, `FREDDIE_MAC_ERROR`, `LINK_DELIVERY_ERROR`, `PROFILE_ERROR`, `RECURRING_TRANSACTIONS_ERROR`, `STATEMENTS_ERROR`, `TRANSFER_RECURRING_ERROR`, `TRANSFER_REFUND_ERROR`

string

The particular error code. Safe for programmatic use.

nullable, string

The specific reason for the error code. Currently, reasons are only supported for OAuth-based item errors; `null` will be returned otherwise. Safe for programmatic use.

Possible values: `OAUTH_INVALID_TOKEN`: The user's OAuth connection to this institution has been invalidated.

`OAUTH_CONSENT_EXPIRED`: The user's access consent for this OAuth connection to this institution has expired.

`OAUTH_USER_REVOKED`: The user's OAuth connection to this institution is invalid because the user revoked their connection.

string

A developer-friendly representation of the error code. This may change over time and is not safe for programmatic use.

nullable, string

A user-friendly representation of the error code. `null` if the error is not related to user action.

This may change over time and is not safe for programmatic use.

string

A unique ID identifying the request, to be used for troubleshooting purposes. This field will be omitted in errors provided by webhooks.

array

In this product, a request can pertain to more than one Item. If an error is returned for such a request, `causes` will return an array of errors containing a breakdown of these errors on the individual Item level, if any can be identified.

`causes` will be provided for the `error_type` `ASSET_REPORT_ERROR` or `CHECK_REPORT_ERROR`. `causes` will also not be populated inside an error nested within a `warning` object.

nullable, integer

The HTTP status code associated with the error. This will only be returned in the response body when the error information is provided via a webhook.

string

The URL of a Plaid documentation page with more information about the error

nullable, string

Suggested steps for resolving the error

\[string\]

A list of the account subtypes that were requested via the `account_filters` parameter in `/link/token/create`. Currently only populated for `NO_ACCOUNTS` errors from Items with `investments_auth` as an enabled product.

\[string\]

A list of the account subtypes that were extracted but did not match the requested subtypes via the `account_filters` parameter in `/link/token/create`. Currently only populated for `NO_ACCOUNTS` errors from Items with `investments_auth` as an enabled product.

\[string\]

A list of products available for the Item that have not yet been accessed. The contents of this array will be mutually exclusive with `billed_products`.

Possible values: `assets`, `auth`, `balance`, `balance_plus`, `beacon`, `identity`, `identity_match`, `investments`, `investments_auth`, `liabilities`, `payment_initiation`, `identity_verification`, `transactions`, `credit_details`, `income`, `income_verification`, `standing_orders`, `transfer`, `employment`, `recurring_transactions`, `transactions_refresh`, `signal`, `statements`, `processor_payments`, `processor_identity`, `profile`, `cra_base_report`, `cra_income_insights`, `cra_partner_insights`, `cra_network_insights`, `cra_cashflow_insights`, `cra_monitoring`, `cra_lend_score`, `cra_plaid_credit_score`, `cra_qualify`, `cra_home_lending`, `layer`, `pay_by_bank`, `protect_linked_bank`, `protect_transactions`

\[string\]

A list of products that have been billed for the Item. The contents of this array will be mutually exclusive with `available_products`. Note - `billed_products` is populated in all environments but only requests in Production are billed. Also note that products that are billed on a pay-per-call basis rather than a pay-per-Item basis, such as `balance`, will not appear here.

Possible values: `assets`, `auth`, `balance`, `balance_plus`, `beacon`, `identity`, `identity_match`, `investments`, `investments_auth`, `liabilities`, `payment_initiation`, `identity_verification`, `transactions`, `credit_details`, `income`, `income_verification`, `standing_orders`, `transfer`, `employment`, `recurring_transactions`, `transactions_refresh`, `signal`, `statements`, `processor_payments`, `processor_identity`, `profile`, `cra_base_report`, `cra_income_insights`, `cra_partner_insights`, `cra_network_insights`, `cra_cashflow_insights`, `cra_monitoring`, `cra_lend_score`, `cra_plaid_credit_score`, `cra_qualify`, `cra_home_lending`, `layer`, `pay_by_bank`, `protect_linked_bank`, `protect_transactions`

\[string\]

A list of products added to the Item. In almost all cases, this will be the same as the `billed_products` field. For some products, it is possible for the product to be added to an Item but not yet billed (e.g. Assets, before `/asset_report/create` has been called, or Auth or Identity when added as Optional Products but before their endpoints have been called), in which case the product may appear in `products` but not in `billed_products`.

Possible values: `assets`, `auth`, `balance`, `balance_plus`, `beacon`, `identity`, `identity_match`, `investments`, `investments_auth`, `liabilities`, `payment_initiation`, `identity_verification`, `transactions`, `credit_details`, `income`, `income_verification`, `standing_orders`, `transfer`, `employment`, `recurring_transactions`, `transactions_refresh`, `signal`, `statements`, `processor_payments`, `processor_identity`, `profile`, `cra_base_report`, `cra_income_insights`, `cra_partner_insights`, `cra_network_insights`, `cra_cashflow_insights`, `cra_monitoring`, `cra_lend_score`, `cra_plaid_credit_score`, `cra_qualify`, `cra_home_lending`, `layer`, `pay_by_bank`, `protect_linked_bank`, `protect_transactions`

\[string\]

A list of products that the user has consented to for the Item via [Data Transparency Messaging](https://plaid.com/docs/link/data-transparency-messaging-migration-guide/index.html.md) . This will consist of all products where both of the following are true: the user has consented to the required data scopes for that product and you have Production access for that product.

Possible values: `assets`, `auth`, `balance`, `balance_plus`, `beacon`, `identity`, `identity_match`, `investments`, `investments_auth`, `liabilities`, `transactions`, `income`, `income_verification`, `transfer`, `employment`, `recurring_transactions`, `signal`, `statements`, `processor_payments`, `processor_identity`, `cra_base_report`, `cra_income_insights`, `cra_lend_score`, `cra_partner_insights`, `cra_cashflow_insights`, `cra_monitoring`, `layer`

nullable, string

The date and time at which the Item's access consent will expire, in [ISO 8601](https://wikipedia.org/wiki/ISO_8601) format. If the Item does not have consent expiration scheduled, this field will be `null`. Currently, only institutions in Europe and a small number of institutions in the US have expiring consent. For a list of US institutions that currently expire consent, see the [OAuth Guide](https://plaid.com/docs/link/oauth/index.html.md#refreshing-item-consent) .

Format: `date-time`

string

Indicates whether an Item requires user interaction to be updated, which can be the case for Items with some forms of two-factor authentication.

`background` - Item can be updated in the background

`user_present_required` - Item requires user interaction to be updated

Possible values: `background`, `user_present_required`

string

A unique identifier for the request, which can be used for troubleshooting. This identifier, like all Plaid identifiers, is case sensitive.

Response Object

```json
{
  "accounts": [
    {
      "account_id": "BxBXxLj1m4HMXBm9WZZmCWVbPjX16EHwv99vp",
      "balances": {
        "available": 110.94,
        "current": 110.94,
        "iso_currency_code": "USD",
        "limit": null,
        "unofficial_currency_code": null
      },
      "mask": "0000",
      "name": "Plaid Checking",
      "official_name": "Plaid Gold Standard 0% Interest Checking",
      "subtype": "checking",
      "type": "depository"
    }
  ],
  "transactions": [
    {
      "account_id": "BxBXxLj1m4HMXBm9WZZmCWVbPjX16EHwv99vp",
      "account_owner": null,
      "amount": 28.34,
      "iso_currency_code": "USD",
      "unofficial_currency_code": null,
      "check_number": null,
      "counterparties": [
        {
          "name": "DoorDash",
          "type": "marketplace",
          "logo_url": "https://plaid-counterparty-logos.plaid.com/doordash_1.png",
          "website": "doordash.com",
          "entity_id": "YNRJg5o2djJLv52nBA1Yn1KpL858egYVo4dpm",
          "confidence_level": "HIGH"
        },
        {
          "name": "Burger King",
          "type": "merchant",
          "logo_url": "https://plaid-merchant-logos.plaid.com/burger_king_155.png",
          "website": "burgerking.com",
          "entity_id": "mVrw538wamwdm22mK8jqpp7qd5br0eeV9o4a1",
          "confidence_level": "VERY_HIGH"
        }
      ],
      "date": "2023-09-28",
      "datetime": "2023-09-28T15:10:09Z",
      "authorized_date": "2023-09-27",
      "authorized_datetime": "2023-09-27T08:01:58Z",
      "location": {
        "address": null,
        "city": null,
        "region": null,
        "postal_code": null,
        "country": null,
        "lat": null,
        "lon": null,
        "store_number": null
      },
      "name": "Dd Doordash Burgerkin",
      "merchant_name": "Burger King",
      "merchant_entity_id": "mVrw538wamwdm22mK8jqpp7qd5br0eeV9o4a1",
      "logo_url": "https://plaid-merchant-logos.plaid.com/burger_king_155.png",
      "website": "burgerking.com",
      "payment_meta": {
        "by_order_of": null,
        "payee": null,
        "payer": null,
        "payment_method": null,
        "payment_processor": null,
        "ppd_id": null,
        "reason": null,
        "reference_number": null
      },
      "payment_channel": "online",
      "pending": true,
      "pending_transaction_id": null,
      "personal_finance_category": {
        "primary": "FOOD_AND_DRINK",
        "detailed": "FOOD_AND_DRINK_FAST_FOOD",
        "confidence_level": "VERY_HIGH"
      },
      "personal_finance_category_icon_url": "https://plaid-category-icons.plaid.com/PFC_FOOD_AND_DRINK.png",
      "transaction_id": "yhnUVvtcGGcCKU0bcz8PDQr5ZUxUXebUvbKC0",
      "transaction_code": null,
      "transaction_type": "digital"
    },
    {
      "account_id": "BxBXxLj1m4HMXBm9WZZmCWVbPjX16EHwv99vp",
      "account_owner": null,
      "amount": 72.1,
      "iso_currency_code": "USD",
      "unofficial_currency_code": null,
      "check_number": null,
      "counterparties": [
        {
          "name": "Walmart",
          "type": "merchant",
          "logo_url": "https://plaid-merchant-logos.plaid.com/walmart_1100.png",
          "website": "walmart.com",
          "entity_id": "O5W5j4dN9OR3E6ypQmjdkWZZRoXEzVMz2ByWM",
          "confidence_level": "VERY_HIGH"
        }
      ],
      "date": "2023-09-24",
      "datetime": "2023-09-24T11:01:01Z",
      "authorized_date": "2023-09-22",
      "authorized_datetime": "2023-09-22T10:34:50Z",
      "location": {
        "address": "13425 Community Rd",
        "city": "Poway",
        "region": "CA",
        "postal_code": "92064",
        "country": "US",
        "lat": 32.959068,
        "lon": -117.037666,
        "store_number": "1700"
      },
      "name": "PURCHASE WM SUPERCENTER #1700",
      "merchant_name": "Walmart",
      "merchant_entity_id": "O5W5j4dN9OR3E6ypQmjdkWZZRoXEzVMz2ByWM",
      "logo_url": "https://plaid-merchant-logos.plaid.com/walmart_1100.png",
      "website": "walmart.com",
      "payment_meta": {
        "by_order_of": null,
        "payee": null,
        "payer": null,
        "payment_method": null,
        "payment_processor": null,
        "ppd_id": null,
        "reason": null,
        "reference_number": null
      },
      "payment_channel": "in store",
      "pending": false,
      "pending_transaction_id": "no86Eox18VHMvaOVL7gPUM9ap3aR1LsAVZ5nc",
      "personal_finance_category": {
        "primary": "GENERAL_MERCHANDISE",
        "detailed": "GENERAL_MERCHANDISE_SUPERSTORES",
        "confidence_level": "VERY_HIGH"
      },
      "personal_finance_category_icon_url": "https://plaid-category-icons.plaid.com/PFC_GENERAL_MERCHANDISE.png",
      "transaction_id": "lPNjeW1nR6CDn5okmGQ6hEpMo4lLNoSrzqDje",
      "transaction_code": null,
      "transaction_type": "place"
    }
  ],
  "item": {
    "available_products": [
      "balance",
      "identity",
      "investments"
    ],
    "billed_products": [
      "assets",
      "auth",
      "liabilities",
      "transactions"
    ],
    "consent_expiration_time": null,
    "error": null,
    "institution_id": "ins_56",
    "institution_name": "Chase",
    "item_id": "eVBnVMp7zdTJLkRNr33Rs6zr7KNJqBFL9DrE6",
    "update_type": "background",
    "webhook": "https://www.genericwebhookurl.com/webhook",
    "auth_method": "INSTANT_AUTH"
  },
  "total_transactions": 2,
  "request_id": "45QSn"
}
```

\=\*=\*=\*=

#### /transactions/recurring/get 

#### Fetch recurring transaction streams 

The [/transactions/recurring/get](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsrecurringget) endpoint allows developers to receive a summary of the recurring outflow and inflow streams (expenses and deposits) from a user's checking, savings or credit card accounts. Additionally, Plaid provides key insights about each recurring stream including the category, merchant, last amount, and more. Developers can use these insights to build tools and experiences that help their users better manage cash flow, monitor subscriptions, reduce spend, and stay on track with bill payments.

This endpoint is offered as an add-on to Transactions. To request access to this endpoint, submit a [product access request](https://dashboard.plaid.com/team/products) or contact your Plaid account manager.

This endpoint can only be called on an Item that has already been initialized with Transactions (either during Link, by specifying it in [/link/token/create](https://plaid.com/docs/api/link/index.html.md#linktokencreate) ; or after Link, by calling [/transactions/get](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsget) or [/transactions/sync](https://plaid.com/docs/api/products/transactions/index.html.md#transactionssync) ).

When using Recurring Transactions, for best results, make sure to use the [days\_requested](https://plaid.com/docs/api/link/index.html.md#link-token-create-request-transactions-days-requested) parameter to request at least 180 days of history when initializing Items with Transactions. Once all historical transactions have been fetched, call [/transactions/recurring/get](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsrecurringget) to receive the Recurring Transactions streams and subscribe to the [RECURRING\_TRANSACTIONS\_UPDATE](https://plaid.com/docs/api/products/transactions/index.html.md#recurring_transactions_update) webhook. To know when historical transactions have been fetched, if you are using [/transactions/sync](https://plaid.com/docs/api/products/transactions/index.html.md#transactionssync) listen for the [SYNC\_UPDATES\_AVAILABLE](https://plaid.com/docs/api/products/transactions/index.html.md#SyncUpdatesAvailableWebhook-historical-update-complete) webhook and check that the `historical_update_complete` field in the payload is `true`. If using [/transactions/get](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsget) , listen for the [HISTORICAL\_UPDATE](https://plaid.com/docs/api/products/transactions/index.html.md#historical_update) webhook.

After the initial call, you can call the [/transactions/recurring/get](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsrecurringget) endpoint at any point in the future to retrieve the latest summary of recurring streams. Listen to the [RECURRING\_TRANSACTIONS\_UPDATE](https://plaid.com/docs/api/products/transactions/index.html.md#recurring_transactions_update) webhook to be notified when new updates are available.

#### Request fields 

string

Your Plaid API `client_id`. The `client_id` is required and may be provided either in the `PLAID-CLIENT-ID` header or as part of a request body.

required, string

The access token associated with the Item for which data is being requested.

string

Your Plaid API `secret`. The `secret` is required and may be provided either in the `PLAID-SECRET` header or as part of a request body.

object

An optional object to be used with the request. If specified, `options` must not be `null`.

string

Indicates which version of the personal finance category taxonomy is being used. [View PFCv2 and PFCv1 taxonomies](https://plaid.com/documents/pfc-taxonomy-all.csv) .

If you enabled Transactions or Enrich before December 3, 2025 you will receive the `v1` taxonomy by default and may request `v2` by explicitly setting this field to `v2` in the request.

If you enabled Transactions or Enrich on or after December 3, 2025, you may only receive the `v2` taxonomy.

Possible values: `v1`, `v2`

\[string\]

An optional list of `account_ids` to retrieve for the Item. Retrieves all active accounts on item if no `account_id`s are provided.

Note: An error will be returned if a provided `account_id` is not associated with the Item.

```bash
curl -X POST https://sandbox.plaid.com/transactions/recurring/get \
-H 'Content-Type: application/json' \
-d '{
     "client_id": "${PLAID_CLIENT_ID}",
     "secret": "${PLAID_SECRET}",
     "access_token":"access-production-12345678-1234-abcd-9c8f-fd5406010eee",
     "account_ids":[
        "iRMxGT59gs5zPcE8yoHrUb0kU33jo899RCEyw",
        "4fPFAM3KDA2bi0ctj8SYX0KgwJQGx8A2Y6OLP",
        "kYcHNDmCoBDwIyD2ssgwTcZOASdvZZRjIg6I6"
     ]
    }'

```

```node
const request: TransactionsRecurringGetRequest = {
  access_token: accessToken,
  account_ids: accountIds,
};
try {
  const response = await client.transactionsRecurringGet(request);
  let inflowStreams = response.data.inflow_streams;
  let outflowStreams = response.data.outflow_streams;
} catch (err) {
  // handle error
}

```

```python
request = TransactionsRecurringGetRequest(
  access_token=access_token,
  account_ids=account_ids
)
response = client.transactions_recurring_get(request)
inflow_streams = response.inflow_streams
outflow_streams = response.outflow_streams

```

```ruby
request = Plaid::TransactionsRecurringGetRequest.new(
  {
    access_token: access_token,
    account_ids: account_ids
  }
)
response = client.transactions_recurring_get(request)
inflow_streams = response.inflow_streams
outflow_streams = response.outflow_streams

```

```java
TransactionsRecurringGetRequest request = new TransactionsRecurringGetRequest()
  .accessToken(accessToken)
  .accountIds(accountIds);

Response
  response = plaidClient.transactionsRecurringGet(request).execute();

List inflowStreams = new ArrayList ();
inflowStreams.addAll(response.body().getInflowStreams());
List outflowStreams = new ArrayList ();
outflowStreams.addAll(response.body().getOutflowStreams());

```

```go
request := plaid.NewTransactionsRecurringGetRequest(accessToken)
request.SetAccountIds(accountIds)
response, _, err := client.PlaidApi.TransactionsRecurringGet(ctx).TransactionsRecurringGetRequest(*request).Execute()

```

#### Response fields 

\[object\]

An array of inflow transaction streams.

string

The ID of the account to which the stream belongs

string

A unique id for the stream

string

A description of the transaction stream.

nullable, string

The merchant associated with the transaction stream.

string

The posted date of the earliest transaction in the stream.

Format: `date`

string

The posted date of the latest transaction in the stream.

Format: `date`

nullable, string

The predicted date of the next payment. This will only be set if the next payment date can be predicted.

Format: `date`

string

Describes the frequency of the transaction stream.

`WEEKLY`: Assigned to a transaction stream that occurs approximately every week.

`BIWEEKLY`: Assigned to a transaction stream that occurs approximately every 2 weeks.

`SEMI_MONTHLY`: Assigned to a transaction stream that occurs approximately twice per month. This frequency is typically seen for inflow transaction streams.

`MONTHLY`: Assigned to a transaction stream that occurs approximately every month.

`ANNUALLY`: Assigned to a transaction stream that occurs approximately every year.

`UNKNOWN`: Assigned to a transaction stream that does not fit any of the pre-defined frequencies.

Possible values: `UNKNOWN`, `WEEKLY`, `BIWEEKLY`, `SEMI_MONTHLY`, `MONTHLY`, `ANNUALLY`

\[string\]

An array of Plaid transaction IDs belonging to the stream, sorted by posted date.

object

Object with data pertaining to an amount on the transaction stream.

number

Represents the numerical value of an amount.

Format: `double`

nullable, string

The ISO-4217 currency code of the amount. Always `null` if `unofficial_currency_code` is non-`null`.

See the [currency code schema](https://plaid.com/docs/api/accounts/index.html.md#currency-code-schema) for a full listing of supported `iso_currency_code`s.

nullable, string

The unofficial currency code of the amount. Always `null` if `iso_currency_code` is non-`null`. Unofficial currency codes are used for currencies that do not have official ISO currency codes, such as cryptocurrencies and the currencies of certain countries.

object

Object with data pertaining to an amount on the transaction stream.

number

Represents the numerical value of an amount.

Format: `double`

nullable, string

The ISO-4217 currency code of the amount. Always `null` if `unofficial_currency_code` is non-`null`.

See the [currency code schema](https://plaid.com/docs/api/accounts/index.html.md#currency-code-schema) for a full listing of supported `iso_currency_code`s.

nullable, string

The unofficial currency code of the amount. Always `null` if `iso_currency_code` is non-`null`. Unofficial currency codes are used for currencies that do not have official ISO currency codes, such as cryptocurrencies and the currencies of certain countries.

boolean

Indicates whether the transaction stream is still live.

string

The current status of the transaction stream.

`MATURE`: A `MATURE` recurring stream should have at least 3 transactions and happen on a regular cadence (For Annual recurring stream, we will mark it `MATURE` after 2 instances).

`EARLY_DETECTION`: When a recurring transaction first appears in the transaction history and before it fulfills the requirement of a mature stream, the status will be `EARLY_DETECTION`.

`TOMBSTONED`: A stream that was previously in the `EARLY_DETECTION` status will move to the `TOMBSTONED` status when no further transactions were found at the next expected date.

`UNKNOWN`: A stream is assigned an `UNKNOWN` status when none of the other statuses are applicable.

Possible values: `UNKNOWN`, `MATURE`, `EARLY_DETECTION`, `TOMBSTONED`

nullable, object

Information describing the intent of the transaction. Most relevant for personal finance use cases, but not limited to such use cases.

See the [taxonomy CSV file](https://plaid.com/documents/pfc-taxonomy-all.csv) for a full list of personal finance categories. If you are migrating to personal finance categories from the legacy categories, also refer to the [migration guide](https://plaid.com/docs/transactions/pfc-migration/index.html.md) .

string

A high level category that communicates the broad category of the transaction.

string

A granular category conveying the transaction's intent. This field can also be used as a unique identifier for the category.

nullable, string

A description of how confident we are that the provided categories accurately describe the transaction intent.

`VERY_HIGH`: We are more than 98% confident that this category reflects the intent of the transaction. `HIGH`: We are more than 90% confident that this category reflects the intent of the transaction. `MEDIUM`: We are moderately confident that this category reflects the intent of the transaction. `LOW`: This category may reflect the intent, but there may be other categories that are more accurate. `UNKNOWN`: We don't know the confidence level for this category.

string

Indicates which version of the personal finance category taxonomy is being used. [View PFCv2 and PFCv1 taxonomies](https://plaid.com/documents/pfc-taxonomy-all.csv) .

If you enabled Transactions or Enrich before December 3, 2025 you will receive the `v1` taxonomy by default and may request `v2` by explicitly setting this field to `v2` in the request.

If you enabled Transactions or Enrich on or after December 3, 2025, you may only receive the `v2` taxonomy.

Possible values: `v1`, `v2`

deprecated, boolean

As the ability to modify transactions streams has been discontinued, this field will always be `false`.

\[object\]

An array of expense transaction streams.

string

The ID of the account to which the stream belongs

string

A unique id for the stream

string

A description of the transaction stream.

nullable, string

The merchant associated with the transaction stream.

string

The posted date of the earliest transaction in the stream.

Format: `date`

string

The posted date of the latest transaction in the stream.

Format: `date`

nullable, string

The predicted date of the next payment. This will only be set if the next payment date can be predicted.

Format: `date`

string

Describes the frequency of the transaction stream.

`WEEKLY`: Assigned to a transaction stream that occurs approximately every week.

`BIWEEKLY`: Assigned to a transaction stream that occurs approximately every 2 weeks.

`SEMI_MONTHLY`: Assigned to a transaction stream that occurs approximately twice per month. This frequency is typically seen for inflow transaction streams.

`MONTHLY`: Assigned to a transaction stream that occurs approximately every month.

`ANNUALLY`: Assigned to a transaction stream that occurs approximately every year.

`UNKNOWN`: Assigned to a transaction stream that does not fit any of the pre-defined frequencies.

Possible values: `UNKNOWN`, `WEEKLY`, `BIWEEKLY`, `SEMI_MONTHLY`, `MONTHLY`, `ANNUALLY`

\[string\]

An array of Plaid transaction IDs belonging to the stream, sorted by posted date.

object

Object with data pertaining to an amount on the transaction stream.

number

Represents the numerical value of an amount.

Format: `double`

nullable, string

The ISO-4217 currency code of the amount. Always `null` if `unofficial_currency_code` is non-`null`.

See the [currency code schema](https://plaid.com/docs/api/accounts/index.html.md#currency-code-schema) for a full listing of supported `iso_currency_code`s.

nullable, string

The unofficial currency code of the amount. Always `null` if `iso_currency_code` is non-`null`. Unofficial currency codes are used for currencies that do not have official ISO currency codes, such as cryptocurrencies and the currencies of certain countries.

object

Object with data pertaining to an amount on the transaction stream.

number

Represents the numerical value of an amount.

Format: `double`

nullable, string

The ISO-4217 currency code of the amount. Always `null` if `unofficial_currency_code` is non-`null`.

See the [currency code schema](https://plaid.com/docs/api/accounts/index.html.md#currency-code-schema) for a full listing of supported `iso_currency_code`s.

nullable, string

The unofficial currency code of the amount. Always `null` if `iso_currency_code` is non-`null`. Unofficial currency codes are used for currencies that do not have official ISO currency codes, such as cryptocurrencies and the currencies of certain countries.

boolean

Indicates whether the transaction stream is still live.

string

The current status of the transaction stream.

`MATURE`: A `MATURE` recurring stream should have at least 3 transactions and happen on a regular cadence (For Annual recurring stream, we will mark it `MATURE` after 2 instances).

`EARLY_DETECTION`: When a recurring transaction first appears in the transaction history and before it fulfills the requirement of a mature stream, the status will be `EARLY_DETECTION`.

`TOMBSTONED`: A stream that was previously in the `EARLY_DETECTION` status will move to the `TOMBSTONED` status when no further transactions were found at the next expected date.

`UNKNOWN`: A stream is assigned an `UNKNOWN` status when none of the other statuses are applicable.

Possible values: `UNKNOWN`, `MATURE`, `EARLY_DETECTION`, `TOMBSTONED`

nullable, object

Information describing the intent of the transaction. Most relevant for personal finance use cases, but not limited to such use cases.

See the [taxonomy CSV file](https://plaid.com/documents/pfc-taxonomy-all.csv) for a full list of personal finance categories. If you are migrating to personal finance categories from the legacy categories, also refer to the [migration guide](https://plaid.com/docs/transactions/pfc-migration/index.html.md) .

string

A high level category that communicates the broad category of the transaction.

string

A granular category conveying the transaction's intent. This field can also be used as a unique identifier for the category.

nullable, string

A description of how confident we are that the provided categories accurately describe the transaction intent.

`VERY_HIGH`: We are more than 98% confident that this category reflects the intent of the transaction. `HIGH`: We are more than 90% confident that this category reflects the intent of the transaction. `MEDIUM`: We are moderately confident that this category reflects the intent of the transaction. `LOW`: This category may reflect the intent, but there may be other categories that are more accurate. `UNKNOWN`: We don't know the confidence level for this category.

string

Indicates which version of the personal finance category taxonomy is being used. [View PFCv2 and PFCv1 taxonomies](https://plaid.com/documents/pfc-taxonomy-all.csv) .

If you enabled Transactions or Enrich before December 3, 2025 you will receive the `v1` taxonomy by default and may request `v2` by explicitly setting this field to `v2` in the request.

If you enabled Transactions or Enrich on or after December 3, 2025, you may only receive the `v2` taxonomy.

Possible values: `v1`, `v2`

deprecated, boolean

As the ability to modify transactions streams has been discontinued, this field will always be `false`.

string

Timestamp in [ISO 8601](https://wikipedia.org/wiki/ISO_8601) format (`YYYY-MM-DDTHH:mm:ssZ`) indicating the last time transaction streams for the given account were updated on

Format: `date-time`

string

Indicates which version of the personal finance category taxonomy is being used. [View PFCv2 and PFCv1 taxonomies](https://plaid.com/documents/pfc-taxonomy-all.csv) .

If you enabled Transactions or Enrich before December 3, 2025 you will receive the `v1` taxonomy by default and may request `v2` by explicitly setting this field to `v2` in the request.

If you enabled Transactions or Enrich on or after December 3, 2025, you may only receive the `v2` taxonomy.

Possible values: `v1`, `v2`

string

A unique identifier for the request, which can be used for troubleshooting. This identifier, like all Plaid identifiers, is case sensitive.

Response Object

```json
{
  "updated_datetime": "2022-05-01T00:00:00Z",
  "inflow_streams": [
    {
      "account_id": "lPNjeW1nR6CDn5okmGQ6hEpMo4lLNoSrzqDje",
      "stream_id": "no86Eox18VHMvaOVL7gPUM9ap3aR1LsAVZ5nc",
      "category": null,
      "category_id": null,
      "description": "Platypus Payroll",
      "merchant_name": null,
      "personal_finance_category": {
        "primary": "INCOME",
        "detailed": "INCOME_WAGES",
        "confidence_level": "UNKNOWN"
      },
      "first_date": "2022-02-28",
      "last_date": "2022-04-30",
      "predicted_next_date": "2022-05-15",
      "frequency": "SEMI_MONTHLY",
      "transaction_ids": [
        "nkeaNrDGrhdo6c4qZWDA8ekuIPuJ4Avg5nKfw",
        "EfC5ekksdy30KuNzad2tQupW8WIPwvjXGbGHL",
        "ozfvj3FFgp6frbXKJGitsDzck5eWQH7zOJBYd",
        "QvdDE8AqVWo3bkBZ7WvCd7LskxVix8Q74iMoK",
        "uQozFPfMzibBouS9h9tz4CsyvFll17jKLdPAF"
      ],
      "average_amount": {
        "amount": -800,
        "iso_currency_code": "USD",
        "unofficial_currency_code": null
      },
      "last_amount": {
        "amount": -1000,
        "iso_currency_code": "USD",
        "unofficial_currency_code": null
      },
      "is_active": true,
      "status": "MATURE",
      "is_user_modified": false
    }
  ],
  "outflow_streams": [
    {
      "account_id": "lPNjeW1nR6CDn5okmGQ6hEpMo4lLNoSrzqDff",
      "stream_id": "no86Eox18VHMvaOVL7gPUM9ap3aR1LsAVZ5nd",
      "category": null,
      "category_id": null,
      "description": "ConEd Bill Payment",
      "merchant_name": "ConEd",
      "personal_finance_category": {
        "primary": "RENT_AND_UTILITIES",
        "detailed": "RENT_AND_UTILITIES_GAS_AND_ELECTRICITY",
        "confidence_level": "UNKNOWN"
      },
      "first_date": "2022-02-04",
      "last_date": "2022-05-02",
      "predicted_next_date": "2022-06-02",
      "frequency": "MONTHLY",
      "transaction_ids": [
        "yhnUVvtcGGcCKU0bcz8PDQr5ZUxUXebUvbKC0",
        "HPDnUVgI5Pa0YQSl0rxwYRwVXeLyJXTWDAvpR",
        "jEPoSfF8xzMClE9Ohj1he91QnvYoSdwg7IT8L",
        "CmdQTNgems8BT1B7ibkoUXVPyAeehT3Tmzk0l"
      ],
      "average_amount": {
        "amount": 85,
        "iso_currency_code": "USD",
        "unofficial_currency_code": null
      },
      "last_amount": {
        "amount": 100,
        "iso_currency_code": "USD",
        "unofficial_currency_code": null
      },
      "is_active": true,
      "status": "MATURE",
      "is_user_modified": false
    },
    {
      "account_id": "lPNjeW1nR6CDn5okmGQ6hEpMo4lLNoSrzqDff",
      "stream_id": "SrBNJZDuUMweodmPmSOeOImwsWt53ZXfJQAfC",
      "category": null,
      "category_id": null,
      "description": "Costco Annual Membership",
      "merchant_name": "Costco",
      "personal_finance_category": {
        "primary": "GENERAL_MERCHANDISE",
        "detailed": "GENERAL_MERCHANDISE_SUPERSTORES",
        "confidence_level": "UNKNOWN"
      },
      "first_date": "2022-01-23",
      "last_date": "2023-01-22",
      "predicted_next_date": "2024-01-22",
      "frequency": "ANNUALLY",
      "transaction_ids": [
        "yqEBJ72cS4jFwcpxJcDuQr94oAQ1R1lMC33D4",
        "Kz5Hm3cZCgpn4tMEKUGAGD6kAcxMBsEZDSwJJ"
      ],
      "average_amount": {
        "amount": 120,
        "iso_currency_code": "USD",
        "unofficial_currency_code": null
      },
      "last_amount": {
        "amount": 120,
        "iso_currency_code": "USD",
        "unofficial_currency_code": null
      },
      "is_active": true,
      "status": "MATURE",
      "is_user_modified": false
    }
  ],
  "request_id": "tbFyCEqkU775ZGG"
}
```

\=\*=\*=\*=

#### /transactions/refresh 

#### Refresh transaction data 

[/transactions/refresh](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsrefresh) is an optional endpoint that initiates an on-demand extraction to fetch the newest transactions for an Item. The on-demand extraction takes place in addition to the periodic extractions that automatically occur one or more times per day for any Transactions-enabled Item. The Item must already have Transactions added as a product in order to call [/transactions/refresh](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsrefresh) .

If changes to transactions are discovered after calling [/transactions/refresh](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsrefresh) , Plaid will fire a webhook: for [/transactions/sync](https://plaid.com/docs/api/products/transactions/index.html.md#transactionssync) users, [SYNC\_UPDATES\_AVAILABLE](https://plaid.com/docs/api/products/transactions/index.html.md#sync_updates_available) will be fired if there are any transactions updated, added, or removed. For users of both [/transactions/sync](https://plaid.com/docs/api/products/transactions/index.html.md#transactionssync) and [/transactions/get](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsget) , [TRANSACTIONS\_REMOVED](https://plaid.com/docs/api/products/transactions/index.html.md#transactions_removed) will be fired if any removed transactions are detected, and [DEFAULT\_UPDATE](https://plaid.com/docs/api/products/transactions/index.html.md#default_update) will be fired if any new transactions are detected. New transactions can be fetched by calling [/transactions/get](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsget) or [/transactions/sync](https://plaid.com/docs/api/products/transactions/index.html.md#transactionssync) .

Note that the [/transactions/refresh](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsrefresh) endpoint is not supported for Capital One (`ins_128026`) non-depository accounts and will result in a `PRODUCTS_NOT_SUPPORTED` error if called on an Item that contains only non-depository accounts from that institution.

As this endpoint triggers a synchronous request for fresh data, latency may be higher than for other Plaid endpoints (typically less than 10 seconds, but occasionally up to 30 seconds or more); if you encounter errors, you may find it necessary to adjust your timeout period when making requests.

[/transactions/refresh](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsrefresh) is offered as an optional add-on to Transactions and has a separate [fee model](https://plaid.com/docs/account/billing/index.html.md#per-request-flat-fee) . To request access to this endpoint, submit a [product access request](https://dashboard.plaid.com/team/products) or contact your Plaid account manager.

#### Request fields 

string

Your Plaid API `client_id`. The `client_id` is required and may be provided either in the `PLAID-CLIENT-ID` header or as part of a request body.

required, string

The access token associated with the Item for which data is being requested.

string

Your Plaid API `secret`. The `secret` is required and may be provided either in the `PLAID-SECRET` header or as part of a request body.

```bash
curl -X POST https://sandbox.plaid.com/transactions/refresh \
 -H 'content-type: application/json' \
 -d '{
   "client_id": "${PLAID_CLIENT_ID}",
   "secret": "${PLAID_SECRET}",
   "access_token": String,
  }'

```

```node
const request: TransactionsRefreshRequest = {
  access_token: accessToken,
};
try {
  await plaidClient.transactionsRefresh(request);
} catch (error) {
  // handle error
}

```

```ruby
request = Plaid::TransactionsRefreshRequest.new({ access_token: access_token })
response = client.transactions_refresh(request)

```

```java
TransactionsRefreshRequest request = new TransactionsRefreshRequest()
  .accessToken(accessToken);
Response response = client()
  .transactionsRefresh(request)
  .execute();

```

```python
request = TransactionsRefreshRequest(access_token=access_token)
response = client.transactions_refresh(request)

```

```go
request := plaid.NewTransactionsRefreshRequest(accessToken)
response, _, err := client.PlaidApi.TransactionsRefresh(ctx).TransactionsRefreshRequest(*request).Execute()

```

#### Response fields 

string

A unique identifier for the request, which can be used for troubleshooting. This identifier, like all Plaid identifiers, is case sensitive.

Response Object

```json
{
  "request_id": "1vwmF5TBQwiqfwP"
}
```

\=\*=\*=\*=

#### /categories/get 

#### (Deprecated) Get legacy categories 

Send a request to the [/categories/get](https://plaid.com/docs/api/products/transactions/index.html.md#categoriesget) endpoint to get detailed information on legacy categories returned by Plaid. This endpoint does not require authentication.

All implementations are recommended to [use the newer personal\_finance\_category taxonomy](https://plaid.com/docs/transactions/pfc-migration/index.html.md) instead of the legacy `category` taxonomy supported by this endpoint.

#### Request fields 

This endpoint or method takes an empty request body.

```bash
curl -X POST https://sandbox.plaid.com/categories/get \
  -H 'Content-Type: application/json' \
  -d '{}'

```

```node
try {
  const response = await plaidClient.categoriesGet({});
  const categories = response.data.categories;
} catch (error) {
  // handle error
}

```

```python
response = client.categories_get({})
categories = response['categories']

```

```java
Response response = client().categoriesGet(new Object()).execute();
List categories =
  response.body().getCategories();

```

```ruby
response = client.categories_get({})
categories = response.categories

```

```go
categoriesGetResp, _, err := client.PlaidApi.CategoriesGet(ctx).Body(nil).Execute()

categories := categoriesGetResp.GetCategories()

```

#### Response fields 

\[object\]

An array of all of the transaction categories used by Plaid.

string

An identifying number for the category. `category_id` is a Plaid-specific identifier and does not necessarily correspond to merchant category codes.

string

`place` for physical transactions or `special` for other transactions such as bank charges.

\[string\]

A hierarchical array of the categories to which this `category_id` belongs.

string

A unique identifier for the request, which can be used for troubleshooting. This identifier, like all Plaid identifiers, is case sensitive.

Response Object

```json
{
  "categories": [
    {
      "category_id": "10000000",
      "group": "special",
      "hierarchy": [
        "Bank Fees"
      ]
    },
    {
      "category_id": "10001000",
      "group": "special",
      "hierarchy": [
        "Bank Fees",
        "Overdraft"
      ]
    },
    {
      "category_id": "12001000",
      "group": "place",
      "hierarchy": [
        "Community",
        "Animal Shelter"
      ]
    }
  ],
  "request_id": "ixTBLZGvhD4NnmB"
}
```

### Webhooks 

You can receive notifications via a webhook whenever there are new transactions associated with an Item, including when Plaid's initial and historical transaction pull are completed. All webhooks related to transactions have a `webhook_type` of `TRANSACTIONS`.

\=\*=\*=\*=

#### SYNC\_UPDATES\_AVAILABLE 

Fired when an Item's transactions change. This can be due to any event resulting in new changes, such as an initial 30-day transactions fetch upon the initialization of an Item with transactions, the backfill of historical transactions that occurs shortly after, or when changes are populated from a regularly-scheduled transactions update job. It is recommended to listen for the `SYNC_UPDATES_AVAILABLE` webhook when using the [/transactions/sync](https://plaid.com/docs/api/products/transactions/index.html.md#transactionssync) endpoint. Note that when using [/transactions/sync](https://plaid.com/docs/api/products/transactions/index.html.md#transactionssync) the older webhooks `INITIAL_UPDATE`, `HISTORICAL_UPDATE`, `DEFAULT_UPDATE`, and `TRANSACTIONS_REMOVED`, which are intended for use with [/transactions/get](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsget) , will also continue to be sent in order to maintain backwards compatibility. It is not necessary to listen for and respond to those webhooks when using [/transactions/sync](https://plaid.com/docs/api/products/transactions/index.html.md#transactionssync) .

After receipt of this webhook, the new changes can be fetched for the Item from [/transactions/sync](https://plaid.com/docs/api/products/transactions/index.html.md#transactionssync) .

Note that to receive this webhook for an Item, [/transactions/sync](https://plaid.com/docs/api/products/transactions/index.html.md#transactionssync) must have been called at least once on that Item. This means that, unlike the `INITIAL_UPDATE` and `HISTORICAL_UPDATE` webhooks, it will not fire immediately upon Item creation. If [/transactions/sync](https://plaid.com/docs/api/products/transactions/index.html.md#transactionssync) is called on an Item that was _not_ initialized with Transactions, the webhook will fire twice: once the first 30 days of transactions data has been fetched, and a second time when all available historical transactions data has been fetched.

This webhook will fire in the Sandbox environment as it would in Production. It can also be manually triggered in Sandbox by calling [/sandbox/item/fire\_webhook](https://plaid.com/docs/api/sandbox/index.html.md#sandboxitemfire_webhook) .

#### Properties 

string

`TRANSACTIONS`

string

`SYNC_UPDATES_AVAILABLE`

string

The `item_id` of the Item associated with this webhook, warning, or error

string

The Plaid `user_id` of the User associated with this webhook, warning, or error.

boolean

Indicates if initial pull information (most recent 30 days of transaction history) is available.

boolean

Indicates if historical pull information (maximum transaction history requested, up to 2 years) is available.

string

The Plaid environment the webhook was sent from

Possible values: `sandbox`, `production`

API Object

```json
{
  "webhook_type": "TRANSACTIONS",
  "webhook_code": "SYNC_UPDATES_AVAILABLE",
  "item_id": "wz666MBjYWTp2PDzzggYhM6oWWmBb",
  "user_id": "usr_9nSp2KuZ2x4JDw",
  "initial_update_complete": true,
  "historical_update_complete": false,
  "environment": "production"
}
```

\=\*=\*=\*=

#### RECURRING\_TRANSACTIONS\_UPDATE 

Fired when recurring transactions data is updated. This includes when a new recurring stream is detected or when a new transaction is added to an existing recurring stream. The `RECURRING_TRANSACTIONS_UPDATE` webhook will also fire when one or more attributes of the recurring stream changes, which is usually a result of the addition, update, or removal of transactions to the stream.

After receipt of this webhook, the updated data can be fetched from [/transactions/recurring/get](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsrecurringget) .

#### Properties 

string

`TRANSACTIONS`

string

`RECURRING_TRANSACTIONS_UPDATE`

string

The `item_id` of the Item associated with this webhook, warning, or error

\[string\]

A list of `account_ids` for accounts that have new or updated recurring transactions data.

string

The Plaid environment the webhook was sent from

Possible values: `sandbox`, `production`

API Object

```json
{
  "webhook_type": "TRANSACTIONS",
  "webhook_code": "RECURRING_TRANSACTIONS_UPDATE",
  "item_id": "wz666MBjYWTp2PDzzggYhM6oWWmBb",
  "account_ids": [
    "lPNjeW1nR6CDn5okmGQ6hEpMo4lLNoSrzqDje",
    "lPNjeW1nR6CDn5okmGQ6hEpMo4lLNoSrzqDff"
  ],
  "environment": "production"
}
```

\=\*=\*=\*=

#### INITIAL\_UPDATE 

Fired when an Item's initial transaction pull is completed. Once this webhook has been fired, transaction data for the most recent 30 days can be fetched for the Item. This webhook will also be fired if account selections for the Item are updated, with `new_transactions` set to the number of net new transactions pulled after the account selection update.

This webhook is intended for use with [/transactions/get](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsget) ; if you are using the newer [/transactions/sync](https://plaid.com/docs/api/products/transactions/index.html.md#transactionssync) endpoint, this webhook will still be fired to maintain backwards compatibility, but it is recommended to listen for and respond to the `SYNC_UPDATES_AVAILABLE` webhook instead.

#### Properties 

string

`TRANSACTIONS`

string

`INITIAL_UPDATE`

string

The error code associated with the webhook.

number

The number of new transactions available.

string

The `item_id` of the Item associated with this webhook, warning, or error

string

The Plaid environment the webhook was sent from

Possible values: `sandbox`, `production`

API Object

```json
{
  "webhook_type": "TRANSACTIONS",
  "webhook_code": "INITIAL_UPDATE",
  "item_id": "wz666MBjYWTp2PDzzggYhM6oWWmBb",
  "error": null,
  "new_transactions": 19,
  "environment": "production"
}
```

\=\*=\*=\*=

#### HISTORICAL\_UPDATE 

Fired when an Item's historical transaction pull is completed and Plaid has prepared as much historical transaction data as possible for the Item. Once this webhook has been fired, transaction data beyond the most recent 30 days can be fetched for the Item. This webhook will also be fired if account selections for the Item are updated, with `new_transactions` set to the number of net new transactions pulled after the account selection update.

This webhook is intended for use with [/transactions/get](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsget) ; if you are using the newer [/transactions/sync](https://plaid.com/docs/api/products/transactions/index.html.md#transactionssync) endpoint, this webhook will still be fired to maintain backwards compatibility, but it is recommended to listen for and respond to the `SYNC_UPDATES_AVAILABLE` webhook instead.

#### Properties 

string

`TRANSACTIONS`

string

`HISTORICAL_UPDATE`

object

Errors are identified by `error_code` and categorized by `error_type`. Use these in preference to HTTP status codes to identify and handle specific errors. HTTP status codes are set and provide the broadest categorization of errors: 4xx codes are for developer- or user-related errors, and 5xx codes are for Plaid-related errors, and the status will be 2xx in non-error cases. An Item with a non-`null` error object will only be part of an API response when calling `/item/get` to view Item status. Otherwise, error fields will be `null` if no error has occurred; if an error has occurred, an error code will be returned instead.

string

A broad categorization of the error. Safe for programmatic use.

Possible values: `INVALID_REQUEST`, `INVALID_RESULT`, `INVALID_INPUT`, `INSTITUTION_ERROR`, `RATE_LIMIT_EXCEEDED`, `API_ERROR`, `ITEM_ERROR`, `ASSET_REPORT_ERROR`, `BASE_REPORT_ERROR`, `RECAPTCHA_ERROR`, `OAUTH_ERROR`, `PAYMENT_ERROR`, `BANK_TRANSFER_ERROR`, `INCOME_VERIFICATION_ERROR`, `MICRODEPOSITS_ERROR`, `SANDBOX_ERROR`, `PARTNER_ERROR`, `SIGNAL_ERROR`, `TRANSACTIONS_ERROR`, `TRANSACTION_ERROR`, `TRANSFER_ERROR`, `CHECK_REPORT_ERROR`, `CONSUMER_REPORT_ERROR`, `USER_ERROR`, `IDEMPOTENCY_ERROR`, `ASSETS_ERROR`, `CRA_MONITORING_ERROR`, `CREDIT_PROFILE_REPORT_ERROR`, `ENCOMPASS_ERROR`, `ENRICH_ERROR`, `FRAUD_INSIGHTS_ERROR`, `FREDDIE_MAC_ERROR`, `LINK_DELIVERY_ERROR`, `PROFILE_ERROR`, `RECURRING_TRANSACTIONS_ERROR`, `STATEMENTS_ERROR`, `TRANSFER_RECURRING_ERROR`, `TRANSFER_REFUND_ERROR`

string

The particular error code. Safe for programmatic use.

string

The specific reason for the error code. Currently, reasons are only supported for OAuth-based item errors; `null` will be returned otherwise. Safe for programmatic use.

Possible values: `OAUTH_INVALID_TOKEN`: The user's OAuth connection to this institution has been invalidated.

`OAUTH_CONSENT_EXPIRED`: The user's access consent for this OAuth connection to this institution has expired.

`OAUTH_USER_REVOKED`: The user's OAuth connection to this institution is invalid because the user revoked their connection.

string

A developer-friendly representation of the error code. This may change over time and is not safe for programmatic use.

string

A user-friendly representation of the error code. `null` if the error is not related to user action.

This may change over time and is not safe for programmatic use.

string

A unique ID identifying the request, to be used for troubleshooting purposes. This field will be omitted in errors provided by webhooks.

array

In this product, a request can pertain to more than one Item. If an error is returned for such a request, `causes` will return an array of errors containing a breakdown of these errors on the individual Item level, if any can be identified.

`causes` will be provided for the `error_type` `ASSET_REPORT_ERROR` or `CHECK_REPORT_ERROR`. `causes` will also not be populated inside an error nested within a `warning` object.

integer

The HTTP status code associated with the error. This will only be returned in the response body when the error information is provided via a webhook.

string

The URL of a Plaid documentation page with more information about the error

string

Suggested steps for resolving the error

\[string\]

A list of the account subtypes that were requested via the `account_filters` parameter in `/link/token/create`. Currently only populated for `NO_ACCOUNTS` errors from Items with `investments_auth` as an enabled product.

\[string\]

A list of the account subtypes that were extracted but did not match the requested subtypes via the `account_filters` parameter in `/link/token/create`. Currently only populated for `NO_ACCOUNTS` errors from Items with `investments_auth` as an enabled product.

number

The number of new transactions available

string

The `item_id` of the Item associated with this webhook, warning, or error

string

The Plaid environment the webhook was sent from

Possible values: `sandbox`, `production`

API Object

```json
{
  "webhook_type": "TRANSACTIONS",
  "webhook_code": "HISTORICAL_UPDATE",
  "item_id": "wz666MBjYWTp2PDzzggYhM6oWWmBb",
  "error": null,
  "new_transactions": 231,
  "environment": "production"
}
```

\=\*=\*=\*=

#### DEFAULT\_UPDATE 

Fired when new transaction data is available for an Item. Plaid will typically check for new transaction data several times a day.

This webhook is intended for use with [/transactions/get](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsget) ; if you are using the newer [/transactions/sync](https://plaid.com/docs/api/products/transactions/index.html.md#transactionssync) endpoint, this webhook will still be fired to maintain backwards compatibility, but it is recommended to listen for and respond to the `SYNC_UPDATES_AVAILABLE` webhook instead.

#### Properties 

string

`TRANSACTIONS`

string

`DEFAULT_UPDATE`

object

Errors are identified by `error_code` and categorized by `error_type`. Use these in preference to HTTP status codes to identify and handle specific errors. HTTP status codes are set and provide the broadest categorization of errors: 4xx codes are for developer- or user-related errors, and 5xx codes are for Plaid-related errors, and the status will be 2xx in non-error cases. An Item with a non-`null` error object will only be part of an API response when calling `/item/get` to view Item status. Otherwise, error fields will be `null` if no error has occurred; if an error has occurred, an error code will be returned instead.

string

A broad categorization of the error. Safe for programmatic use.

Possible values: `INVALID_REQUEST`, `INVALID_RESULT`, `INVALID_INPUT`, `INSTITUTION_ERROR`, `RATE_LIMIT_EXCEEDED`, `API_ERROR`, `ITEM_ERROR`, `ASSET_REPORT_ERROR`, `BASE_REPORT_ERROR`, `RECAPTCHA_ERROR`, `OAUTH_ERROR`, `PAYMENT_ERROR`, `BANK_TRANSFER_ERROR`, `INCOME_VERIFICATION_ERROR`, `MICRODEPOSITS_ERROR`, `SANDBOX_ERROR`, `PARTNER_ERROR`, `SIGNAL_ERROR`, `TRANSACTIONS_ERROR`, `TRANSACTION_ERROR`, `TRANSFER_ERROR`, `CHECK_REPORT_ERROR`, `CONSUMER_REPORT_ERROR`, `USER_ERROR`, `IDEMPOTENCY_ERROR`, `ASSETS_ERROR`, `CRA_MONITORING_ERROR`, `CREDIT_PROFILE_REPORT_ERROR`, `ENCOMPASS_ERROR`, `ENRICH_ERROR`, `FRAUD_INSIGHTS_ERROR`, `FREDDIE_MAC_ERROR`, `LINK_DELIVERY_ERROR`, `PROFILE_ERROR`, `RECURRING_TRANSACTIONS_ERROR`, `STATEMENTS_ERROR`, `TRANSFER_RECURRING_ERROR`, `TRANSFER_REFUND_ERROR`

string

The particular error code. Safe for programmatic use.

string

The specific reason for the error code. Currently, reasons are only supported for OAuth-based item errors; `null` will be returned otherwise. Safe for programmatic use.

Possible values: `OAUTH_INVALID_TOKEN`: The user's OAuth connection to this institution has been invalidated.

`OAUTH_CONSENT_EXPIRED`: The user's access consent for this OAuth connection to this institution has expired.

`OAUTH_USER_REVOKED`: The user's OAuth connection to this institution is invalid because the user revoked their connection.

string

A developer-friendly representation of the error code. This may change over time and is not safe for programmatic use.

string

A user-friendly representation of the error code. `null` if the error is not related to user action.

This may change over time and is not safe for programmatic use.

string

A unique ID identifying the request, to be used for troubleshooting purposes. This field will be omitted in errors provided by webhooks.

array

In this product, a request can pertain to more than one Item. If an error is returned for such a request, `causes` will return an array of errors containing a breakdown of these errors on the individual Item level, if any can be identified.

`causes` will be provided for the `error_type` `ASSET_REPORT_ERROR` or `CHECK_REPORT_ERROR`. `causes` will also not be populated inside an error nested within a `warning` object.

integer

The HTTP status code associated with the error. This will only be returned in the response body when the error information is provided via a webhook.

string

The URL of a Plaid documentation page with more information about the error

string

Suggested steps for resolving the error

\[string\]

A list of the account subtypes that were requested via the `account_filters` parameter in `/link/token/create`. Currently only populated for `NO_ACCOUNTS` errors from Items with `investments_auth` as an enabled product.

\[string\]

A list of the account subtypes that were extracted but did not match the requested subtypes via the `account_filters` parameter in `/link/token/create`. Currently only populated for `NO_ACCOUNTS` errors from Items with `investments_auth` as an enabled product.

number

The number of new transactions detected since the last time this webhook was fired.

string

The `item_id` of the Item the webhook relates to.

string

The Plaid environment the webhook was sent from

Possible values: `sandbox`, `production`

API Object

```json
{
  "webhook_type": "TRANSACTIONS",
  "webhook_code": "DEFAULT_UPDATE",
  "item_id": "wz666MBjYWTp2PDzzggYhM6oWWmBb",
  "error": null,
  "new_transactions": 3,
  "environment": "production"
}
```

\=\*=\*=\*=

#### TRANSACTIONS\_REMOVED 

Fired when transaction(s) for an Item are deleted. The deleted transaction IDs are included in the webhook payload. Plaid will typically check for deleted transaction data several times a day.

This webhook is intended for use with [/transactions/get](https://plaid.com/docs/api/products/transactions/index.html.md#transactionsget) ; if you are using the newer [/transactions/sync](https://plaid.com/docs/api/products/transactions/index.html.md#transactionssync) endpoint, this webhook will still be fired to maintain backwards compatibility, but it is recommended to listen for and respond to the `SYNC_UPDATES_AVAILABLE` webhook instead.

#### Properties 

string

`TRANSACTIONS`

string

`TRANSACTIONS_REMOVED`

object

Errors are identified by `error_code` and categorized by `error_type`. Use these in preference to HTTP status codes to identify and handle specific errors. HTTP status codes are set and provide the broadest categorization of errors: 4xx codes are for developer- or user-related errors, and 5xx codes are for Plaid-related errors, and the status will be 2xx in non-error cases. An Item with a non-`null` error object will only be part of an API response when calling `/item/get` to view Item status. Otherwise, error fields will be `null` if no error has occurred; if an error has occurred, an error code will be returned instead.

string

A broad categorization of the error. Safe for programmatic use.

Possible values: `INVALID_REQUEST`, `INVALID_RESULT`, `INVALID_INPUT`, `INSTITUTION_ERROR`, `RATE_LIMIT_EXCEEDED`, `API_ERROR`, `ITEM_ERROR`, `ASSET_REPORT_ERROR`, `BASE_REPORT_ERROR`, `RECAPTCHA_ERROR`, `OAUTH_ERROR`, `PAYMENT_ERROR`, `BANK_TRANSFER_ERROR`, `INCOME_VERIFICATION_ERROR`, `MICRODEPOSITS_ERROR`, `SANDBOX_ERROR`, `PARTNER_ERROR`, `SIGNAL_ERROR`, `TRANSACTIONS_ERROR`, `TRANSACTION_ERROR`, `TRANSFER_ERROR`, `CHECK_REPORT_ERROR`, `CONSUMER_REPORT_ERROR`, `USER_ERROR`, `IDEMPOTENCY_ERROR`, `ASSETS_ERROR`, `CRA_MONITORING_ERROR`, `CREDIT_PROFILE_REPORT_ERROR`, `ENCOMPASS_ERROR`, `ENRICH_ERROR`, `FRAUD_INSIGHTS_ERROR`, `FREDDIE_MAC_ERROR`, `LINK_DELIVERY_ERROR`, `PROFILE_ERROR`, `RECURRING_TRANSACTIONS_ERROR`, `STATEMENTS_ERROR`, `TRANSFER_RECURRING_ERROR`, `TRANSFER_REFUND_ERROR`

string

The particular error code. Safe for programmatic use.

string

The specific reason for the error code. Currently, reasons are only supported for OAuth-based item errors; `null` will be returned otherwise. Safe for programmatic use.

Possible values: `OAUTH_INVALID_TOKEN`: The user's OAuth connection to this institution has been invalidated.

`OAUTH_CONSENT_EXPIRED`: The user's access consent for this OAuth connection to this institution has expired.

`OAUTH_USER_REVOKED`: The user's OAuth connection to this institution is invalid because the user revoked their connection.

string

A developer-friendly representation of the error code. This may change over time and is not safe for programmatic use.

string

A user-friendly representation of the error code. `null` if the error is not related to user action.

This may change over time and is not safe for programmatic use.

string

A unique ID identifying the request, to be used for troubleshooting purposes. This field will be omitted in errors provided by webhooks.

array

In this product, a request can pertain to more than one Item. If an error is returned for such a request, `causes` will return an array of errors containing a breakdown of these errors on the individual Item level, if any can be identified.

`causes` will be provided for the `error_type` `ASSET_REPORT_ERROR` or `CHECK_REPORT_ERROR`. `causes` will also not be populated inside an error nested within a `warning` object.

integer

The HTTP status code associated with the error. This will only be returned in the response body when the error information is provided via a webhook.

string

The URL of a Plaid documentation page with more information about the error

string

Suggested steps for resolving the error

\[string\]

A list of the account subtypes that were requested via the `account_filters` parameter in `/link/token/create`. Currently only populated for `NO_ACCOUNTS` errors from Items with `investments_auth` as an enabled product.

\[string\]

A list of the account subtypes that were extracted but did not match the requested subtypes via the `account_filters` parameter in `/link/token/create`. Currently only populated for `NO_ACCOUNTS` errors from Items with `investments_auth` as an enabled product.

\[string\]

An array of `transaction_ids` corresponding to the removed transactions

string

The `item_id` of the Item associated with this webhook, warning, or error

string

The Plaid environment the webhook was sent from

Possible values: `sandbox`, `production`

API Object

```json
{
  "webhook_type": "TRANSACTIONS",
  "webhook_code": "TRANSACTIONS_REMOVED",
  "item_id": "wz666MBjYWTp2PDzzggYhM6oWWmBb",
  "removed_transactions": [
    "yBVBEwrPyJs8GvR77N7QTxnGg6wG74H7dEDN6",
    "kgygNvAVPzSX9KkddNdWHaVGRVex1MHm3k9no"
  ],
  "error": null,
  "environment": "production"
}
```