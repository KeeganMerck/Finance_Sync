Investments 
============

#### API reference for Investments endpoints and webhooks 

For how-to guidance, see the [Investments documentation](https://plaid.com/docs/investments/index.html.md) .

| Endpoints |  |
| --- | --- |
| [/investments/holdings/get](https://plaid.com/docs/api/products/investments/index.html.md#investmentsholdingsget) | Fetch investment holdings |
| [/investments/transactions/get](https://plaid.com/docs/api/products/investments/index.html.md#investmentstransactionsget) | Fetch investment transactions |
| [/investments/refresh](https://plaid.com/docs/api/products/investments/index.html.md#investmentsrefresh) | Refresh investment transactions |

| See also |  |
| --- | --- |
| [/processor/investments/holdings/get](https://plaid.com/docs/api/processor-partners/index.html.md#processorinvestmentsholdingsget) | Fetch Investments Holdings data |
| [/processor/investments/transactions/get](https://plaid.com/docs/api/processor-partners/index.html.md#processorinvestmentstransactionsget) | Fetch Investments Transactions data |

| Webhooks |  |
| --- | --- |
| [HOLDINGS: DEFAULT\_UPDATE](https://plaid.com/docs/api/products/investments/index.html.md#holdings-default_update) | New holdings available |
| [INVESTMENTS\_TRANSACTIONS: DEFAULT\_UPDATE](https://plaid.com/docs/api/products/investments/index.html.md#investments_transactions-default_update) | New transactions available |
| [INVESTMENTS\_TRANSACTIONS: HISTORICAL\_UPDATE](https://plaid.com/docs/api/products/investments/index.html.md#investments_transactions-historical_update) | Investments data ready |

### Endpoints 

\=\*=\*=\*=

#### /investments/holdings/get 

#### Get Investment holdings 

The [/investments/holdings/get](https://plaid.com/docs/api/products/investments/index.html.md#investmentsholdingsget) endpoint allows developers to receive user-authorized stock position data for `investment`\-type accounts.

#### Request fields 

string

Your Plaid API `client_id`. The `client_id` is required and may be provided either in the `PLAID-CLIENT-ID` header or as part of a request body.

string

Your Plaid API `secret`. The `secret` is required and may be provided either in the `PLAID-SECRET` header or as part of a request body.

required, string

The access token associated with the Item for which data is being requested.

object

An optional object to filter `/investments/holdings/get` results. If provided, must not be `null`.

\[string\]

An array of `account_id`s to retrieve for the Item. An error will be returned if a provided `account_id` is not associated with the Item.

```go
holdingsGetReq := plaid.NewInvestmentsHoldingsGetRequest("ACCESS_TOKEN")
holdingsGetReqOptions := plaid.NewInvestmentHoldingsGetRequestOptions()
holdingsGetReqOptions.SetAccountIds([]string{"ACCOUNT_ID"})
holdingsGetReq.SetOptions(*holdingsGetReqOptions)
holdingsGetResp, _, err := client.PlaidApi.InvestmentsHoldingsGet(ctx).InvestmentsHoldingsGetRequest(
  *holdingsGetReq,
).Execute()
securities := holdingsGetResp.GetSecurities()
holdings := holdingsGetResp.GetHoldings()

```

```node
// Pull Holdings for an Item
const request: InvestmentsHoldingsGetRequest = {
  access_token: accessToken,
};
try {
  const response = await plaidClient.investmentsHoldingsGet(request);
  const holdings = response.data.holdings;
  const securities = response.data.securities;
} catch (error) {
  // handle error
}

```

```python
# Pull Holdings for an Item
request = InvestmentsHoldingsGetRequest(access_token=access_token)
response = client.investments_holdings_get(request)

# Handle Holdings response
holdings = response['holdings']

# Handle Securities response
securities = response['securities']

```

```ruby
# Pull Holdings for an Item
request = Plaid::InvestmentsHoldingsGetRequest.new({ access_token: access_token })
response = client.investments_holdings_get(request)

# Handle Holdings response
holdings = response.holdings

# Handle Securities response
securities = response.securities

```

```java
// Pull Holdings for an Item
InvestmentsHoldingsGetRequest request = new InvestmentsHoldingsGetRequest()
  .accessToken(accessToken);
Response response = client()
  .investmentsHoldingsGet(request)
  .execute();

// Handle Holdings response
List holdings = response.body().getHoldings();

// Handle Securities response
List securities = response.body().getSecurities();

```

```bash
curl -X POST https://sandbox.plaid.com/investments/holdings/get \
-H 'Content-Type: application/json' \
-d '{
  "client_id": "${PLAID_CLIENT_ID}",
  "secret": "${PLAID_SECRET}",
  "access_token": string
}'

```

#### Response fields 

\[object\]

The accounts associated with the Item

string

Plaid's unique identifier for the account. This value will not change unless Plaid can't reconcile the account with the data returned by the financial institution. This may occur, for example, when the name of the account changes. If this happens a new `account_id` will be assigned to the account.

The `account_id` can also change if the `access_token` is deleted and the same credentials that were used to generate that `access_token` are used to generate a new `access_token` on a later date. In that case, the new `account_id` will be different from the old `account_id`.

If an account with a specific `account_id` disappears instead of changing, the account is likely closed. Closed accounts are not returned by the Plaid API.

When using a CRA endpoint (an endpoint associated with Plaid Check Consumer Report, i.e. any endpoint beginning with `/cra/`), the `account_id` returned will not match the `account_id` returned by a non-CRA endpoint.

Like all Plaid identifiers, the `account_id` is case sensitive.

object

A set of fields describing the balance for an account, including margin loan information for investment accounts.

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

nullable, number

The total amount of borrowed funds in the account, as determined by the financial institution. For investment-type accounts, the margin balance is the total value of borrowed assets in the account, as presented by the institution. This is commonly referred to as margin or a loan.

Format: `double`

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

The holdings belonging to investment accounts associated with the Item. Details of the securities in the holdings are provided in the `securities` field.

string

The Plaid `account_id` associated with the holding.

string

The Plaid `security_id` associated with the holding. Security data is not specific to a user's account; any user who held the same security at the same financial institution at the same time would have identical security data. The `security_id` for the same security will typically be the same across different institutions, but this is not guaranteed. The `security_id` does not typically change, but may change if inherent details of the security change due to a corporate action, for example, in the event of a ticker symbol change or CUSIP change.

number

The last price given by the institution for this security.

Format: `double`

nullable, string

The date at which `institution_price` was current.

Format: `date`

nullable, string

Date and time at which `institution_price` was current, in ISO 8601 format (YYYY-MM-DDTHH:mm:ssZ).

This field is returned for select financial institutions and comes as provided by the institution. It may contain default time values (such as 00:00:00).

Format: `date-time`

number

The value of the holding, as reported by the institution.

Format: `double`

nullable, number

The total cost basis of the holding (e.g., the total amount spent to acquire all assets currently in the holding).

Format: `double`

number

The total quantity of the asset held, as reported by the financial institution. If the security is an option, `quantity` will reflect the total number of options (typically the number of contracts multiplied by 100), not the number of contracts.

Format: `double`

nullable, string

The ISO-4217 currency code of the holding. Always `null` if `unofficial_currency_code` is non-`null`.

nullable, string

The unofficial currency code associated with the holding. Always `null` if `iso_currency_code` is non-`null`. Unofficial currency codes are used for currencies that do not have official ISO currency codes, such as cryptocurrencies and the currencies of certain countries.

See the [currency code schema](https://plaid.com/docs/api/accounts/index.html.md#currency-code-schema) for a full listing of supported `unofficial_currency_code`s.

nullable, number

The total quantity of vested assets held, as reported by the financial institution. Vested assets are only associated with [equities](https://plaid.com/docs/api/products/investments/index.html.md#investments-holdings-get-response-securities-type) .

Format: `double`

nullable, number

The value of the vested holdings as reported by the institution.

Format: `double`

\[object\]

Per-lot acquisition data for this holding. An empty array indicates the institution does not provide lot-level data.

nullable, string

The financial institution's identifier for this lot. Null if the institution does not provide a lot identifier.

nullable, string

The date and time this lot was acquired, in ISO 8601 format. Null if the institution does not provide acquisition datetime data.

Format: `date-time`

nullable, number

The number of units of the security in this lot.

Format: `double`

nullable, number

The price per unit of the security at the time this lot was acquired.

Format: `double`

nullable, number

The total cost basis of this lot, inclusive of any fees.

Format: `double`

nullable, number

The current market value of this lot.

Format: `double`

nullable, string

Indicates whether a holding lot position is long or short. Possible values are `LONG` and `SHORT`.

Possible values: `LONG`, `SHORT`

\[object\]

Objects describing the securities held in the accounts associated with the Item.

string

A unique, Plaid-specific identifier for the security, used to associate securities with holdings. Like all Plaid identifiers, the `security_id` is case sensitive. The `security_id` may change if inherent details of the security change due to a corporate action, for example, in the event of a ticker symbol change or CUSIP change.

nullable, string

12-character ISIN, a globally unique securities identifier. A verified CUSIP Global Services license is required to receive this data. This field will be null by default for new customers, and null for existing customers starting March 12, 2024. If you would like access to this field, please start the verification process [here](https://docs.google.com/forms/d/e/1FAIpQLSd9asHEYEfmf8fxJTHZTAfAzW4dugsnSu-HS2J51f1mxwd6Sw/viewform) .

nullable, string

9-character CUSIP, an identifier assigned to North American securities. A verified CUSIP Global Services license is required to receive this data. This field will be null by default for new customers, and null for existing customers starting March 12, 2024. If you would like access to this field, please start the verification process [here](https://docs.google.com/forms/d/e/1FAIpQLSd9asHEYEfmf8fxJTHZTAfAzW4dugsnSu-HS2J51f1mxwd6Sw/viewform) .

deprecated, nullable, string

(Deprecated) 7-character SEDOL, an identifier assigned to securities in the UK.

nullable, string

An identifier given to the security by the institution

nullable, string

If `institution_security_id` is present, this field indicates the Plaid `institution_id` of the institution to whom the identifier belongs.

nullable, string

In certain cases, Plaid will provide the ID of another security whose performance resembles this security, typically when the original security has low volume, or when a private security can be modeled with a publicly traded security.

nullable, string

A descriptive name for the security, suitable for display.

nullable, string

The security's trading symbol for publicly traded securities, and otherwise a short identifier if available.

nullable, boolean

Indicates that a security is a highly liquid asset and can be treated like cash.

nullable, string

The security type of the holding.

In rare instances, a null value is returned when institutional data is insufficient to determine the security type.

Valid security types are:

`cash`: Cash, currency, and money market funds

`cryptocurrency`: Digital or virtual currencies

`derivative`: Options, warrants, and other derivative instruments

`equity`: Domestic and foreign equities

`etf`: Multi-asset exchange-traded investment funds

`fixed income`: Bonds and certificates of deposit (CDs)

`loan`: Loans and loan receivables

`mutual fund`: Open- and closed-end vehicles pooling funds of multiple investors

`other`: Unknown or other investment types

nullable, string

The security subtype of the holding.

In rare instances, a null value is returned when institutional data is insufficient to determine the security subtype.

Possible values: `asset backed security`, `bill`, `bond`, `bond with warrants`, `cash`, `cash management bill`, `common stock`, `convertible bond`, `convertible equity`, `cryptocurrency`, `depositary receipt`, `depositary receipt on debt`, `etf`, `float rating note`, `fund of funds`, `hedge fund`, `limited partnership unit`, `medium term note`, `money market debt`, `mortgage backed security`, `municipal bond`, `mutual fund`, `note`, `option`, `other`, `preferred convertible`, `preferred equity`, `private equity fund`, `real estate investment trust`, `structured equity product`, `treasury inflation protected securities`, `unit`, `warrant`.

nullable, number

Price of the security at the close of the previous trading session. Null for non-public securities.

If the security is a foreign currency this field will be updated daily and will be priced in USD.

If the security is a cryptocurrency, this field will be updated multiple times a day. As crypto prices can fluctuate quickly and data may become stale sooner than other asset classes, refer to `update_datetime` with the time when the price was last updated.

Format: `double`

nullable, string

Date for which `close_price` is accurate. Always `null` if `close_price` is `null`.

Format: `date`

nullable, string

Date and time at which `close_price` is accurate, in ISO 8601 format (YYYY-MM-DDTHH:mm:ssZ). Always `null` if `close_price` is `null`.

Format: `date-time`

nullable, string

The ISO-4217 currency code of the price given. Always `null` if `unofficial_currency_code` is non-`null`.

nullable, string

The unofficial currency code associated with the security. Always `null` if `iso_currency_code` is non-`null`. Unofficial currency codes are used for currencies that do not have official ISO currency codes, such as cryptocurrencies and the currencies of certain countries.

See the [currency code schema](https://plaid.com/docs/api/accounts/index.html.md#currency-code-schema) for a full listing of supported `unofficial_currency_code`s.

nullable, string

The ISO-10383 Market Identifier Code of the exchange or market in which the security is being traded.

nullable, string

The sector classification of the security, such as Finance, Health Technology, etc.

For a complete list of possible values, please refer to the ["Sectors and Industries" spreadsheet](https://docs.google.com/spreadsheets/d/1L7aXUdqLhxgM8qe7hK67qqKXiUdQqILpwZ0LpxvCVnc) .

nullable, string

The industry classification of the security, such as Biotechnology, Airlines, etc.

For a complete list of possible values, please refer to the ["Sectors and Industries" spreadsheet](https://docs.google.com/spreadsheets/d/1L7aXUdqLhxgM8qe7hK67qqKXiUdQqILpwZ0LpxvCVnc) .

nullable, string

The ISO-10962 Classification of Financial Instruments Code used to classify the security based on its structure and function.

nullable, string

12-character FIGI, a unique Financial Instrument Global Identifier assigned to securities that is immutable and stays consistent across most corporate actions. This is an open data standard issued by the Object Management Group and administered by Bloomberg L.P.

nullable, object

Details about the option security.

For the Sandbox environment, this data is currently only available if the Item is using a [custom Sandbox user](https://plaid.com/docs/sandbox/user-custom/index.html.md) and the `ticker` field of the custom security follows the [OCC Option Symbol](https://en.wikipedia.org/wiki/Option_symbol#The_OCC_Option_Symbol) standard with no spaces. For an example of simulating this in Sandbox, see the [custom Sandbox GitHub](https://github.com/plaid/sandbox-custom-users) .

string

The type of this option contract. It is one of:

`put`: for Put option contracts

`call`: for Call option contracts

string

The expiration date for this option contract, in [ISO 8601](https://wikipedia.org/wiki/ISO_8601) format.

Format: `date`

number

The strike price for this option contract, per share of security.

Format: `double`

string

The ticker of the underlying security for this option contract.

nullable, object

Details about the fixed income security.

nullable, object

Details about a fixed income security's expected rate of return.

number

The fixed income security's expected rate of return.

Format: `double`

nullable, string

The type of rate which indicates how the predicted yield was calculated. It is one of:

`coupon`: the annualized interest rate for securities with a one-year term or longer, such as treasury notes and bonds.

`coupon_equivalent`: the calculated equivalent for the annualized interest rate factoring in the discount rate and time to maturity, for shorter term, non-interest-bearing securities such as treasury bills.

`discount`: the rate at which the present value or cost is discounted from the future value upon maturity, also known as the face value.

`yield`: the total predicted rate of return factoring in both the discount rate and the coupon rate, applicable to securities such as exchange-traded bonds which can both be interest-bearing as well as sold at a discount off their face value.

Possible values: `coupon`, `coupon_equivalent`, `discount`, `yield`, `null`

nullable, string

The maturity date for this fixed income security, in [ISO 8601](https://wikipedia.org/wiki/ISO_8601) format.

Format: `date`

nullable, string

The issue date for this fixed income security, in [ISO 8601](https://wikipedia.org/wiki/ISO_8601) format.

Format: `date`

nullable, number

The face value that is paid upon maturity of the fixed income security, per unit of security.

Format: `double`

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

boolean

When true, this field indicates that the Item's portfolio was manually created with the Investments Fallback flow.

Response Object

```json
{
  "accounts": [
    {
      "account_id": "5Bvpj4QknlhVWk7GygpwfVKdd133GoCxB814g",
      "balances": {
        "available": 43200,
        "current": 43200,
        "iso_currency_code": "USD",
        "limit": null,
        "margin_loan_amount": null,
        "unofficial_currency_code": null
      },
      "mask": "4444",
      "name": "Plaid Money Market",
      "official_name": "Plaid Platinum Standard 1.85% Interest Money Market",
      "subtype": "money market",
      "type": "depository"
    },
    {
      "account_id": "JqMLm4rJwpF6gMPJwBqdh9ZjjPvvpDcb7kDK1",
      "balances": {
        "available": null,
        "current": 110.01,
        "iso_currency_code": "USD",
        "limit": null,
        "margin_loan_amount": null,
        "unofficial_currency_code": null
      },
      "mask": "5555",
      "name": "Plaid IRA",
      "official_name": null,
      "subtype": "ira",
      "type": "investment"
    },
    {
      "account_id": "k67E4xKvMlhmleEa4pg9hlwGGNnnEeixPolGm",
      "balances": {
        "available": null,
        "current": 24580.0605,
        "iso_currency_code": "USD",
        "limit": null,
        "margin_loan_amount": null,
        "unofficial_currency_code": null
      },
      "mask": "6666",
      "name": "Plaid 401k",
      "official_name": null,
      "subtype": "401k",
      "type": "investment"
    },
    {
      "account_id": "ax0xgOBYRAIqOOjeLZr0iZBb8r6K88HZXpvmq",
      "balances": {
        "available": 48200.03,
        "current": 48200.03,
        "iso_currency_code": "USD",
        "limit": null,
        "margin_loan_amount": null,
        "unofficial_currency_code": null
      },
      "mask": "4092",
      "name": "Plaid Crypto Exchange Account",
      "official_name": null,
      "subtype": "crypto exchange",
      "type": "investment"
    }
  ],
  "holdings": [
    {
      "account_id": "JqMLm4rJwpF6gMPJwBqdh9ZjjPvvpDcb7kDK1",
      "cost_basis": 1,
      "institution_price": 1,
      "institution_price_as_of": "2021-04-13",
      "institution_price_datetime": null,
      "institution_value": 0.01,
      "iso_currency_code": "USD",
      "quantity": 0.01,
      "security_id": "d6ePmbPxgWCWmMVv66q9iPV94n91vMtov5Are",
      "unofficial_currency_code": null,
      "vested_quantity": null,
      "vested_value": null,
      "tax_lots": []
    },
    {
      "account_id": "k67E4xKvMlhmleEa4pg9hlwGGNnnEeixPolGm",
      "cost_basis": 1.5,
      "institution_price": 2.11,
      "institution_price_as_of": "2021-04-13",
      "institution_price_datetime": null,
      "institution_value": 2.11,
      "iso_currency_code": "USD",
      "quantity": 1,
      "security_id": "KDwjlXj1Rqt58dVvmzRguxJybmyQL8FgeWWAy",
      "unofficial_currency_code": null,
      "vested_quantity": null,
      "vested_value": null,
      "tax_lots": []
    },
    {
      "account_id": "k67E4xKvMlhmleEa4pg9hlwGGNnnEeixPolGm",
      "cost_basis": 10,
      "institution_price": 10.42,
      "institution_price_as_of": "2021-04-13",
      "institution_price_datetime": null,
      "institution_value": 20.84,
      "iso_currency_code": "USD",
      "quantity": 2,
      "security_id": "NDVQrXQoqzt5v3bAe8qRt4A7mK7wvZCLEBBJk",
      "unofficial_currency_code": null,
      "vested_quantity": null,
      "vested_value": null,
      "tax_lots": [
        {
          "institution_lot_id": "1",
          "original_purchase_datetime": "2021-01-15T00:00:00Z",
          "quantity": 1,
          "purchase_price": 4.75,
          "cost_basis": 4.75,
          "current_value": 10.42,
          "position_type": "LONG"
        },
        {
          "institution_lot_id": "2",
          "original_purchase_datetime": "2021-03-22T00:00:00Z",
          "quantity": 1,
          "purchase_price": 5.25,
          "cost_basis": 5.25,
          "current_value": 10.42,
          "position_type": "LONG"
        }
      ]
    },
    {
      "account_id": "JqMLm4rJwpF6gMPJwBqdh9ZjjPvvpDcb7kDK1",
      "cost_basis": 0.01,
      "institution_price": 0.011,
      "institution_price_as_of": "2021-04-13",
      "institution_price_datetime": null,
      "institution_value": 110,
      "iso_currency_code": "USD",
      "quantity": 10000,
      "security_id": "8E4L9XLl6MudjEpwPAAgivmdZRdBPJuvMPlPb",
      "unofficial_currency_code": null,
      "vested_quantity": null,
      "vested_value": null,
      "tax_lots": []
    },
    {
      "account_id": "k67E4xKvMlhmleEa4pg9hlwGGNnnEeixPolGm",
      "cost_basis": 23,
      "institution_price": 27,
      "institution_price_as_of": "2021-04-13",
      "institution_price_datetime": null,
      "institution_value": 636.309,
      "iso_currency_code": "USD",
      "quantity": 23.567,
      "security_id": "JDdP7XPMklt5vwPmDN45t3KAoWAPmjtpaW7DP",
      "unofficial_currency_code": null,
      "vested_quantity": null,
      "vested_value": null,
      "tax_lots": []
    },
    {
      "account_id": "k67E4xKvMlhmleEa4pg9hlwGGNnnEeixPolGm",
      "cost_basis": 15,
      "institution_price": 13.73,
      "institution_price_as_of": "2021-04-13",
      "institution_price_datetime": null,
      "institution_value": 1373.6865,
      "iso_currency_code": "USD",
      "quantity": 100.05,
      "security_id": "nnmo8doZ4lfKNEDe3mPJipLGkaGw3jfPrpxoN",
      "unofficial_currency_code": null,
      "vested_quantity": null,
      "vested_value": null,
      "tax_lots": []
    },
    {
      "account_id": "k67E4xKvMlhmleEa4pg9hlwGGNnnEeixPolGm",
      "cost_basis": 948.08,
      "institution_price": 94.808,
      "institution_price_as_of": "2021-04-13",
      "institution_price_datetime": null,
      "institution_value": 948.08,
      "iso_currency_code": "USD",
      "quantity": 10,
      "security_id": "Lxe4yz4XQEtwb2YArO7RFMpPDvPxy7FALRyea",
      "unofficial_currency_code": null,
      "vested_quantity": null,
      "vested_value": null,
      "tax_lots": []
    },
    {
      "account_id": "k67E4xKvMlhmleEa4pg9hlwGGNnnEeixPolGm",
      "cost_basis": 1,
      "institution_price": 1,
      "institution_price_as_of": "2021-04-13",
      "institution_price_datetime": null,
      "institution_value": 12345.67,
      "iso_currency_code": "USD",
      "quantity": 12345.67,
      "security_id": "d6ePmbPxgWCWmMVv66q9iPV94n91vMtov5Are",
      "unofficial_currency_code": null,
      "vested_quantity": null,
      "vested_value": null,
      "tax_lots": []
    },
    {
      "account_id": "ax0xgOBYRAIqOOjeLZr0iZBb8r6K88HZXpvmq",
      "cost_basis": 92.47,
      "institution_price": 0.177494362,
      "institution_price_as_of": "2022-01-14",
      "institution_price_datetime": "2022-06-07T23:01:00Z",
      "institution_value": 4437.35905,
      "iso_currency_code": "USD",
      "quantity": 25000,
      "security_id": "vLRMV3MvY1FYNP91on35CJD5QN5rw9Fpa9qOL",
      "unofficial_currency_code": null,
      "vested_quantity": null,
      "vested_value": null,
      "tax_lots": []
    }
  ],
  "item": {
    "available_products": [
      "balance",
      "identity",
      "liabilities",
      "transactions"
    ],
    "billed_products": [
      "assets",
      "auth",
      "investments"
    ],
    "consent_expiration_time": null,
    "error": null,
    "institution_id": "ins_56",
    "institution_name": "Chase",
    "item_id": "4z9LPae1nRHWy8pvg9jrsgbRP4ZNQvIdbLq7g",
    "update_type": "background",
    "webhook": "https://www.genericwebhookurl.com/webhook",
    "auth_method": "INSTANT_AUTH"
  },
  "request_id": "l68wb8zpS0hqmsJ",
  "securities": [
    {
      "close_price": 0.011,
      "close_price_as_of": "2021-04-13",
      "cusip": null,
      "institution_id": null,
      "institution_security_id": null,
      "is_cash_equivalent": false,
      "isin": null,
      "iso_currency_code": "USD",
      "name": "Nflx Feb 01'18 $355 Call",
      "proxy_security_id": null,
      "security_id": "8E4L9XLl6MudjEpwPAAgivmdZRdBPJuvMPlPb",
      "sedol": null,
      "ticker_symbol": "NFLX180201C00355000",
      "type": "derivative",
      "subtype": "option",
      "unofficial_currency_code": null,
      "update_datetime": null,
      "market_identifier_code": "XNAS",
      "sector": "Technology Services",
      "industry": "Internet Software or Services",
      "cfi_code": "OCASPS",
      "figi": null,
      "option_contract": {
        "contract_type": "call",
        "expiration_date": "2018-02-01",
        "strike_price": 355,
        "underlying_security_ticker": "NFLX"
      },
      "fixed_income": null
    },
    {
      "close_price": 27,
      "close_price_as_of": null,
      "cusip": "577130834",
      "institution_id": null,
      "institution_security_id": null,
      "is_cash_equivalent": false,
      "isin": "US5771308344",
      "iso_currency_code": "USD",
      "name": "Matthews Pacific Tiger Fund Insti Class",
      "proxy_security_id": null,
      "security_id": "JDdP7XPMklt5vwPmDN45t3KAoWAPmjtpaW7DP",
      "sedol": null,
      "ticker_symbol": "MIPTX",
      "type": "mutual fund",
      "subtype": "mutual fund",
      "unofficial_currency_code": null,
      "update_datetime": null,
      "market_identifier_code": "XNAS",
      "sector": "Miscellaneous",
      "industry": "Investment Trusts or Mutual Funds",
      "cfi_code": "CIOGES",
      "figi": null,
      "option_contract": null,
      "fixed_income": null
    },
    {
      "close_price": 2.11,
      "close_price_as_of": null,
      "cusip": "00448Q201",
      "institution_id": null,
      "institution_security_id": null,
      "is_cash_equivalent": false,
      "isin": "US00448Q2012",
      "iso_currency_code": "USD",
      "name": "Achillion Pharmaceuticals Inc.",
      "proxy_security_id": null,
      "security_id": "KDwjlXj1Rqt58dVvmzRguxJybmyQL8FgeWWAy",
      "sedol": null,
      "ticker_symbol": "ACHN",
      "type": "equity",
      "subtype": "common stock",
      "unofficial_currency_code": null,
      "update_datetime": null,
      "market_identifier_code": "XNAS",
      "sector": "Health Technology",
      "industry": "Major Pharmaceuticals",
      "cfi_code": "ESVUFR",
      "figi": null,
      "option_contract": null,
      "fixed_income": null
    },
    {
      "close_price": 10.42,
      "close_price_as_of": null,
      "cusip": "258620103",
      "institution_id": null,
      "institution_security_id": null,
      "is_cash_equivalent": false,
      "isin": "US2586201038",
      "iso_currency_code": "USD",
      "name": "DoubleLine Total Return Bond Fund",
      "proxy_security_id": null,
      "security_id": "NDVQrXQoqzt5v3bAe8qRt4A7mK7wvZCLEBBJk",
      "sedol": null,
      "ticker_symbol": "DBLTX",
      "type": "mutual fund",
      "subtype": "mutual fund",
      "unofficial_currency_code": null,
      "update_datetime": null,
      "market_identifier_code": "XNAS",
      "sector": null,
      "industry": null,
      "cfi_code": "CIOIBS",
      "figi": null,
      "option_contract": null,
      "fixed_income": null
    },
    {
      "close_price": 1,
      "close_price_as_of": null,
      "cusip": null,
      "institution_id": null,
      "institution_security_id": null,
      "is_cash_equivalent": true,
      "isin": null,
      "iso_currency_code": "USD",
      "name": "U S Dollar",
      "proxy_security_id": null,
      "security_id": "d6ePmbPxgWCWmMVv66q9iPV94n91vMtov5Are",
      "sedol": null,
      "ticker_symbol": "USD",
      "type": "cash",
      "subtype": "cash",
      "unofficial_currency_code": null,
      "update_datetime": null,
      "market_identifier_code": null,
      "sector": null,
      "industry": null,
      "cfi_code": null,
      "figi": null,
      "option_contract": null,
      "fixed_income": null
    },
    {
      "close_price": 13.73,
      "close_price_as_of": null,
      "cusip": null,
      "institution_id": "ins_56",
      "institution_security_id": "NHX105509",
      "is_cash_equivalent": false,
      "isin": null,
      "iso_currency_code": "USD",
      "name": "NH PORTFOLIO 1055 (FIDELITY INDEX)",
      "proxy_security_id": null,
      "security_id": "nnmo8doZ4lfKNEDe3mPJipLGkaGw3jfPrpxoN",
      "sedol": null,
      "ticker_symbol": "NHX105509",
      "type": "etf",
      "subtype": "etf",
      "unofficial_currency_code": null,
      "update_datetime": null,
      "market_identifier_code": "XNAS",
      "sector": null,
      "industry": null,
      "cfi_code": null,
      "figi": null,
      "option_contract": null,
      "fixed_income": null
    },
    {
      "close_price": 94.808,
      "close_price_as_of": "2023-11-02",
      "cusip": "912797HE0",
      "institution_id": null,
      "institution_security_id": null,
      "is_cash_equivalent": false,
      "isin": null,
      "iso_currency_code": "USD",
      "name": "US Treasury Bill - 5.43% 31/10/2024 USD 100",
      "proxy_security_id": null,
      "security_id": "Lxe4yz4XQEtwb2YArO7RFMpPDvPxy7FALRyea",
      "sedol": null,
      "ticker_symbol": null,
      "type": "fixed income",
      "subtype": "bill",
      "unofficial_currency_code": null,
      "update_datetime": null,
      "market_identifier_code": null,
      "sector": "Government",
      "industry": "Sovereign Government",
      "cfi_code": "DYZTXR",
      "figi": null,
      "option_contract": null,
      "fixed_income": {
        "face_value": 100,
        "issue_date": "2023-11-02",
        "maturity_date": "2024-10-31",
        "yield_rate": {
          "percentage": 5.43,
          "type": "coupon_equivalent"
        }
      }
    },
    {
      "close_price": 0.140034616,
      "close_price_as_of": "2022-01-24",
      "cusip": null,
      "institution_id": "ins_56",
      "institution_security_id": null,
      "is_cash_equivalent": true,
      "isin": null,
      "iso_currency_code": "USD",
      "name": "Dogecoin",
      "proxy_security_id": null,
      "security_id": "vLRMV3MvY1FYNP91on35CJD5QN5rw9Fpa9qOL",
      "sedol": null,
      "ticker_symbol": "DOGE",
      "type": "cryptocurrency",
      "subtype": "cryptocurrency",
      "unofficial_currency_code": null,
      "update_datetime": "2022-06-07T23:01:00Z",
      "market_identifier_code": "XNAS",
      "sector": null,
      "industry": null,
      "cfi_code": null,
      "figi": null,
      "option_contract": null,
      "fixed_income": null
    }
  ]
}
```

\=\*=\*=\*=

#### /investments/transactions/get 

#### Get investment transactions 

The [/investments/transactions/get](https://plaid.com/docs/api/products/investments/index.html.md#investmentstransactionsget) endpoint allows developers to retrieve up to 24 months of user-authorized transaction data for investment accounts.

Transactions are returned in reverse-chronological order, and the sequence of transaction ordering is stable and will not shift.

Due to the potentially large number of investment transactions associated with an Item, results are paginated. Manipulate the count and offset parameters in conjunction with the `total_investment_transactions` response body field to fetch all available investment transactions.

Note that Investments does not have a webhook to indicate when initial transaction data has loaded (unless you use the `async_update` option). Instead, if transactions data is not ready when [/investments/transactions/get](https://plaid.com/docs/api/products/investments/index.html.md#investmentstransactionsget) is first called, Plaid will wait for the data. For this reason, calling [/investments/transactions/get](https://plaid.com/docs/api/products/investments/index.html.md#investmentstransactionsget) immediately after Link may take up to one to two minutes to return.

Data returned by the asynchronous investments extraction flow (when `async_update` is set to true) may not be immediately available to [/investments/transactions/get](https://plaid.com/docs/api/products/investments/index.html.md#investmentstransactionsget) . To be alerted when the data is ready to be fetched, listen for the `HISTORICAL_UPDATE` webhook. If no investments history is ready when [/investments/transactions/get](https://plaid.com/docs/api/products/investments/index.html.md#investmentstransactionsget) is called, it will return a `PRODUCT_NOT_READY` error.

#### Request fields 

string

Your Plaid API `client_id`. The `client_id` is required and may be provided either in the `PLAID-CLIENT-ID` header or as part of a request body.

string

Your Plaid API `secret`. The `secret` is required and may be provided either in the `PLAID-SECRET` header or as part of a request body.

required, string

The access token associated with the Item for which data is being requested.

required, string

The earliest date for which to fetch transaction history. Dates should be formatted as YYYY-MM-DD.

Format: `date`

required, string

The most recent date for which to fetch transaction history. Dates should be formatted as YYYY-MM-DD.

Format: `date`

object

An optional object to filter `/investments/transactions/get` results. If provided, must be non-`null`.

\[string\]

An array of `account_ids` to retrieve for the Item.

integer

The number of transactions to fetch.

Default: `100`

Minimum: `1`

Maximum: `500`

integer

The number of transactions to skip when fetching transaction history

Default: `0`

Minimum: `0`

boolean

If the Item was not initialized with the investments product via the `products`, `required_if_supported_products`, or `optional_products` array when calling `/link/token/create`, and `async_update` is set to true, the initial Investments extraction will happen asynchronously. Plaid will subsequently fire a `HISTORICAL_UPDATE` webhook when the extraction completes. When `false`, Plaid will wait to return a response until extraction completion and no `HISTORICAL_UPDATE` webhook will fire. Note that while the extraction is happening asynchronously, calls to `/investments/transactions/get` and `/investments/refresh` will return `PRODUCT_NOT_READY` errors until the extraction completes.

Default: `false`

```bash
curl -X POST https://sandbox.plaid.com/investments/transactions/get \
-H 'Content-Type: application/json' \
-d '{
  "client_id": "${PLAID_CLIENT_ID}",
  "secret": "${PLAID_SECRET}",
  "access_token": string,
  "start_date": "2018-03-01",
  "end_date": "2018-04-30",
  "options": {
    "count": 250,
    "offset": 100
  }
}'

```

```ruby
# Pull investment transactions for a date range
request = Plaid::InvestmentsTransactionsGetRequest.new(
  {
    access_token: access_token,
    start_date: '2019-03-01',
    end_date: '2019-04-30'
  }
)
response = client.investments_transactions_get(request)
investmentTransactions = response.investment_transactions

# Manipulate the offset parameter to paginate transactions
# and retrieve all available data
while investmentTransactions.length < response.total_investment_transactions
request = Plaid::InvestmentsTransactionsGetRequest.new(
  {
    access_token: access_token,
    start_date: '2018-01-01',
    end_date: '2018-02-01',
    options: { offset: investmentTransactions.length }
  }
)
response = client.investments_transactions_get(request)
investmentTransactions += response.investment_transactions
end

```

```java
LocalDate startDate = LocalDate.parse("2019-03-01");
LocalDate endDate = LocalDate.parse("2019-04-30");

// Pull transactions for a date range
InvestmentsTransactionsGetRequest request = new InvestmentsTransactionsGetRequest()
  .accessToken(accessToken)
  .startDate(startDate)
  .endDate(endDate);

Response response =
  client().investmentsTransactionsGet(request).execute();

// Manipulate the count and offset parameters to paginate
// transactions and retrieve all available data

InvestmentsTransactionsGetRequestOptions options = new InvestmentsTransactionsGetRequestOptions()
  .count(100)
  .offset(1)
  .accountIds(Arrays.asList(someAccountId));

request = new InvestmentsTransactionsGetRequest()
  .accessToken(getItemPublicTokenExchangeResponse().getAccessToken())
  .startDate(startDate)
  .endDate(endDate)
  .options(options);

response = client().investmentsTransactionsGet(request).execute();

for (InvestmentTransaction txn : response.body().getInvestmentTransactions()) { ... }

```

```node
const request: InvestmentsTransactionsGetRequest = {
  access_token: accessToken,
  start_date: '2019-01-01',
  end_date: '2019-06-10',
};
try {
  const response = await plaidClient.investmentsTransactionsGet(request);
  const investmentTransactions = response.data.investment_transactions;
} catch (error) {
  // handle error
}

```

```python
request = InvestmentsTransactionsGetRequest(
    access_token=access_token,
    start_date=date.fromisoformat('2019-03-01'),
    end_date=date.fromisoformat('2019-04-30'),
    options=InvestmentsTransactionsGetRequestOptions()
)
response = client.investments_transactions_get(request)
investment_transactions = response['investment_transactions']

# Manipulate the count and offset parameters to paginate
# transactions and retrieve all available data
while len(investment_transactions) < response['total_investment_transactions']:
    request = InvestmentsTransactionsGetRequest(
        access_token=access_token,
        start_date=date.fromisoformat('2019-03-01'),
        end_date=date.fromisoformat('2019-04-30'),
        options=InvestmentsTransactionsGetRequestOptions(
          offset=len(investment_transactions)
        )
    )
    response = client.investments_transactions_get(request)
    investment_transactions.extend(response['investment_transactions'])

```

```go
request := plaid.NewInvestmentsTransactionsGetRequest(accessToken, startDateString, endDateString)
response, _, err := client.PlaidApi.InvestmentsTransactionsGet(ctx).InvestmentsTransactionsGetRequest(*request).Execute()
investmentTransactions := response.GetInvestmentTransactions()

```

#### Response fields 

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

\[object\]

The accounts for which transaction history is being fetched.

string

Plaid's unique identifier for the account. This value will not change unless Plaid can't reconcile the account with the data returned by the financial institution. This may occur, for example, when the name of the account changes. If this happens a new `account_id` will be assigned to the account.

The `account_id` can also change if the `access_token` is deleted and the same credentials that were used to generate that `access_token` are used to generate a new `access_token` on a later date. In that case, the new `account_id` will be different from the old `account_id`.

If an account with a specific `account_id` disappears instead of changing, the account is likely closed. Closed accounts are not returned by the Plaid API.

When using a CRA endpoint (an endpoint associated with Plaid Check Consumer Report, i.e. any endpoint beginning with `/cra/`), the `account_id` returned will not match the `account_id` returned by a non-CRA endpoint.

Like all Plaid identifiers, the `account_id` is case sensitive.

object

A set of fields describing the balance for an account, including margin loan information for investment accounts.

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

nullable, number

The total amount of borrowed funds in the account, as determined by the financial institution. For investment-type accounts, the margin balance is the total value of borrowed assets in the account, as presented by the institution. This is commonly referred to as margin or a loan.

Format: `double`

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

All securities for which there is a corresponding transaction being fetched.

string

A unique, Plaid-specific identifier for the security, used to associate securities with holdings. Like all Plaid identifiers, the `security_id` is case sensitive. The `security_id` may change if inherent details of the security change due to a corporate action, for example, in the event of a ticker symbol change or CUSIP change.

nullable, string

12-character ISIN, a globally unique securities identifier. A verified CUSIP Global Services license is required to receive this data. This field will be null by default for new customers, and null for existing customers starting March 12, 2024. If you would like access to this field, please start the verification process [here](https://docs.google.com/forms/d/e/1FAIpQLSd9asHEYEfmf8fxJTHZTAfAzW4dugsnSu-HS2J51f1mxwd6Sw/viewform) .

nullable, string

9-character CUSIP, an identifier assigned to North American securities. A verified CUSIP Global Services license is required to receive this data. This field will be null by default for new customers, and null for existing customers starting March 12, 2024. If you would like access to this field, please start the verification process [here](https://docs.google.com/forms/d/e/1FAIpQLSd9asHEYEfmf8fxJTHZTAfAzW4dugsnSu-HS2J51f1mxwd6Sw/viewform) .

deprecated, nullable, string

(Deprecated) 7-character SEDOL, an identifier assigned to securities in the UK.

nullable, string

An identifier given to the security by the institution

nullable, string

If `institution_security_id` is present, this field indicates the Plaid `institution_id` of the institution to whom the identifier belongs.

nullable, string

In certain cases, Plaid will provide the ID of another security whose performance resembles this security, typically when the original security has low volume, or when a private security can be modeled with a publicly traded security.

nullable, string

A descriptive name for the security, suitable for display.

nullable, string

The security's trading symbol for publicly traded securities, and otherwise a short identifier if available.

nullable, boolean

Indicates that a security is a highly liquid asset and can be treated like cash.

nullable, string

The security type of the holding.

In rare instances, a null value is returned when institutional data is insufficient to determine the security type.

Valid security types are:

`cash`: Cash, currency, and money market funds

`cryptocurrency`: Digital or virtual currencies

`derivative`: Options, warrants, and other derivative instruments

`equity`: Domestic and foreign equities

`etf`: Multi-asset exchange-traded investment funds

`fixed income`: Bonds and certificates of deposit (CDs)

`loan`: Loans and loan receivables

`mutual fund`: Open- and closed-end vehicles pooling funds of multiple investors

`other`: Unknown or other investment types

nullable, string

The security subtype of the holding.

In rare instances, a null value is returned when institutional data is insufficient to determine the security subtype.

Possible values: `asset backed security`, `bill`, `bond`, `bond with warrants`, `cash`, `cash management bill`, `common stock`, `convertible bond`, `convertible equity`, `cryptocurrency`, `depositary receipt`, `depositary receipt on debt`, `etf`, `float rating note`, `fund of funds`, `hedge fund`, `limited partnership unit`, `medium term note`, `money market debt`, `mortgage backed security`, `municipal bond`, `mutual fund`, `note`, `option`, `other`, `preferred convertible`, `preferred equity`, `private equity fund`, `real estate investment trust`, `structured equity product`, `treasury inflation protected securities`, `unit`, `warrant`.

nullable, number

Price of the security at the close of the previous trading session. Null for non-public securities.

If the security is a foreign currency this field will be updated daily and will be priced in USD.

If the security is a cryptocurrency, this field will be updated multiple times a day. As crypto prices can fluctuate quickly and data may become stale sooner than other asset classes, refer to `update_datetime` with the time when the price was last updated.

Format: `double`

nullable, string

Date for which `close_price` is accurate. Always `null` if `close_price` is `null`.

Format: `date`

nullable, string

Date and time at which `close_price` is accurate, in ISO 8601 format (YYYY-MM-DDTHH:mm:ssZ). Always `null` if `close_price` is `null`.

Format: `date-time`

nullable, string

The ISO-4217 currency code of the price given. Always `null` if `unofficial_currency_code` is non-`null`.

nullable, string

The unofficial currency code associated with the security. Always `null` if `iso_currency_code` is non-`null`. Unofficial currency codes are used for currencies that do not have official ISO currency codes, such as cryptocurrencies and the currencies of certain countries.

See the [currency code schema](https://plaid.com/docs/api/accounts/index.html.md#currency-code-schema) for a full listing of supported `unofficial_currency_code`s.

nullable, string

The ISO-10383 Market Identifier Code of the exchange or market in which the security is being traded.

nullable, string

The sector classification of the security, such as Finance, Health Technology, etc.

For a complete list of possible values, please refer to the ["Sectors and Industries" spreadsheet](https://docs.google.com/spreadsheets/d/1L7aXUdqLhxgM8qe7hK67qqKXiUdQqILpwZ0LpxvCVnc) .

nullable, string

The industry classification of the security, such as Biotechnology, Airlines, etc.

For a complete list of possible values, please refer to the ["Sectors and Industries" spreadsheet](https://docs.google.com/spreadsheets/d/1L7aXUdqLhxgM8qe7hK67qqKXiUdQqILpwZ0LpxvCVnc) .

nullable, string

The ISO-10962 Classification of Financial Instruments Code used to classify the security based on its structure and function.

nullable, string

12-character FIGI, a unique Financial Instrument Global Identifier assigned to securities that is immutable and stays consistent across most corporate actions. This is an open data standard issued by the Object Management Group and administered by Bloomberg L.P.

nullable, object

Details about the option security.

For the Sandbox environment, this data is currently only available if the Item is using a [custom Sandbox user](https://plaid.com/docs/sandbox/user-custom/index.html.md) and the `ticker` field of the custom security follows the [OCC Option Symbol](https://en.wikipedia.org/wiki/Option_symbol#The_OCC_Option_Symbol) standard with no spaces. For an example of simulating this in Sandbox, see the [custom Sandbox GitHub](https://github.com/plaid/sandbox-custom-users) .

string

The type of this option contract. It is one of:

`put`: for Put option contracts

`call`: for Call option contracts

string

The expiration date for this option contract, in [ISO 8601](https://wikipedia.org/wiki/ISO_8601) format.

Format: `date`

number

The strike price for this option contract, per share of security.

Format: `double`

string

The ticker of the underlying security for this option contract.

nullable, object

Details about the fixed income security.

nullable, object

Details about a fixed income security's expected rate of return.

number

The fixed income security's expected rate of return.

Format: `double`

nullable, string

The type of rate which indicates how the predicted yield was calculated. It is one of:

`coupon`: the annualized interest rate for securities with a one-year term or longer, such as treasury notes and bonds.

`coupon_equivalent`: the calculated equivalent for the annualized interest rate factoring in the discount rate and time to maturity, for shorter term, non-interest-bearing securities such as treasury bills.

`discount`: the rate at which the present value or cost is discounted from the future value upon maturity, also known as the face value.

`yield`: the total predicted rate of return factoring in both the discount rate and the coupon rate, applicable to securities such as exchange-traded bonds which can both be interest-bearing as well as sold at a discount off their face value.

Possible values: `coupon`, `coupon_equivalent`, `discount`, `yield`, `null`

nullable, string

The maturity date for this fixed income security, in [ISO 8601](https://wikipedia.org/wiki/ISO_8601) format.

Format: `date`

nullable, string

The issue date for this fixed income security, in [ISO 8601](https://wikipedia.org/wiki/ISO_8601) format.

Format: `date`

nullable, number

The face value that is paid upon maturity of the fixed income security, per unit of security.

Format: `double`

\[object\]

The transactions being fetched

string

The ID of the Investment transaction, unique across all Plaid transactions. Like all Plaid identifiers, the `investment_transaction_id` is case sensitive.

string

The `account_id` of the account against which this transaction posted.

nullable, string

The `security_id` to which this transaction is related.

string

The [ISO 8601](https://wikipedia.org/wiki/ISO_8601) posting date for the transaction. This is typically the settlement date.

Format: `date`

nullable, string

Timestamp in [ISO 8601](https://wikipedia.org/wiki/ISO_8601) format (`YYYY-MM-DDTHH:mm:ssZ`) representing when the order type was initiated. This field is returned for select financial institutions and reflects the value provided by the institution.

Format: `date-time`

string

The institution's description of the transaction.

number

The number of units of the security involved in this transaction. Positive for buy transactions; negative for sell transactions.

Format: `double`

number

The complete value of the transaction. Positive values when cash is debited, e.g. purchases of stock; negative values when cash is credited, e.g. sales of stock. Treatment remains the same for cash-only movements unassociated with securities. For transactions representing a simultaneous cash contribution and purchase of a security, the portion of the transaction representing the purchase takes precedence, and the `amount` is represented as positive.

Format: `double`

number

The price of the security at which this transaction occurred.

Format: `double`

nullable, number

The combined value of all fees applied to this transaction

Format: `double`

string

Value is one of the following: `buy`: Buying an investment `sell`: Selling an investment `cancel`: A cancellation of a pending transaction `cash`: Activity that modifies a cash position `fee`: A fee on the account `transfer`: Activity which modifies a position, but not through buy/sell activity e.g. options exercise, portfolio transfer

For descriptions of possible transaction types and subtypes, see the [Investment transaction types schema](https://plaid.com/docs/api/accounts/index.html.md#investment-transaction-types-schema) .

Possible values: `buy`, `sell`, `cancel`, `cash`, `fee`, `transfer`

string

For descriptions of possible transaction types and subtypes, see the [Investment transaction types schema](https://plaid.com/docs/api/accounts/index.html.md#investment-transaction-types-schema) .

Possible values: `account fee`, `adjustment`, `assignment`, `buy`, `buy to cover`, `contribution`, `deposit`, `distribution`, `dividend`, `dividend reinvestment`, `exercise`, `expire`, `fund fee`, `interest`, `interest receivable`, `interest reinvestment`, `legal fee`, `loan payment`, `long-term capital gain`, `long-term capital gain reinvestment`, `management fee`, `margin expense`, `merger`, `miscellaneous fee`, `non-qualified dividend`, `non-resident tax`, `pending credit`, `pending debit`, `qualified dividend`, `rebalance`, `return of principal`, `request`, `sell`, `sell short`, `send`, `short-term capital gain`, `short-term capital gain reinvestment`, `spin off`, `split`, `stock distribution`, `tax`, `tax withheld`, `trade`, `transfer`, `transfer fee`, `trust fee`, `unqualified gain`, `withdrawal`

nullable, string

The ISO-4217 currency code of the transaction. Always `null` if `unofficial_currency_code` is non-`null`.

nullable, string

The unofficial currency code associated with the transaction. Always `null` if `iso_currency_code` is non-`null`. Unofficial currency codes are used for currencies that do not have official ISO currency codes, such as cryptocurrencies and the currencies of certain countries.

See the [currency code schema](https://plaid.com/docs/api/accounts/index.html.md#currency-code-schema) for a full listing of supported `unofficial_currency_code`s.

integer

The total number of transactions available within the date range specified. If `total_investment_transactions` is larger than the size of the `transactions` array, more transactions are available and can be fetched via manipulating the `offset` parameter.

string

A unique identifier for the request, which can be used for troubleshooting. This identifier, like all Plaid identifiers, is case sensitive.

boolean

When true, this field indicates that the Item's portfolio was manually created with the Investments Fallback flow.

Response Object

```json
{
  "accounts": [
    {
      "account_id": "5e66Dl6jNatx3nXPGwZ7UkJed4z6KBcZA4Rbe",
      "balances": {
        "available": 100,
        "current": 110,
        "iso_currency_code": "USD",
        "limit": null,
        "margin_loan_amount": null,
        "unofficial_currency_code": null
      },
      "mask": "0000",
      "name": "Plaid Checking",
      "official_name": "Plaid Gold Standard 0% Interest Checking",
      "subtype": "checking",
      "type": "depository"
    },
    {
      "account_id": "KqZZMoZmBWHJlz7yKaZjHZb78VNpaxfVa7e5z",
      "balances": {
        "available": null,
        "current": 320.76,
        "iso_currency_code": "USD",
        "limit": null,
        "margin_loan_amount": null,
        "unofficial_currency_code": null
      },
      "mask": "5555",
      "name": "Plaid IRA",
      "official_name": null,
      "subtype": "ira",
      "type": "investment"
    },
    {
      "account_id": "rz99ex9ZQotvnjXdgQLEsR81e3ArPgulVWjGj",
      "balances": {
        "available": null,
        "current": 23631.9805,
        "iso_currency_code": "USD",
        "limit": null,
        "margin_loan_amount": null,
        "unofficial_currency_code": null
      },
      "mask": "6666",
      "name": "Plaid 401k",
      "official_name": null,
      "subtype": "401k",
      "type": "investment"
    }
  ],
  "investment_transactions": [
    {
      "account_id": "rz99ex9ZQotvnjXdgQLEsR81e3ArPgulVWjGj",
      "amount": -8.72,
      "cancel_transaction_id": null,
      "date": "2020-05-29",
      "transaction_datetime": null,
      "fees": 0,
      "investment_transaction_id": "oq99Pz97joHQem4BNjXECev1E4B6L6sRzwANW",
      "iso_currency_code": "USD",
      "name": "INCOME DIV DIVIDEND RECEIVED",
      "price": 0,
      "quantity": 0,
      "security_id": "eW4jmnjd6AtjxXVrjmj6SX1dNEdZp3Cy8RnRQ",
      "subtype": "dividend",
      "type": "cash",
      "unofficial_currency_code": null
    },
    {
      "account_id": "rz99ex9ZQotvnjXdgQLEsR81e3ArPgulVWjGj",
      "amount": -1289.01,
      "cancel_transaction_id": null,
      "date": "2020-05-28",
      "transaction_datetime": "2020-05-28T15:10:09Z",
      "fees": 7.99,
      "investment_transaction_id": "pK99jB9e7mtwjA435GpVuMvmWQKVbVFLWme57",
      "iso_currency_code": "USD",
      "name": "SELL Matthews Pacific Tiger Fund Insti Class",
      "price": 27.53,
      "quantity": -47.74104242992852,
      "security_id": "JDdP7XPMklt5vwPmDN45t3KAoWAPmjtpaW7DP",
      "subtype": "sell",
      "type": "sell",
      "unofficial_currency_code": null
    },
    {
      "account_id": "rz99ex9ZQotvnjXdgQLEsR81e3ArPgulVWjGj",
      "amount": 7.7,
      "cancel_transaction_id": null,
      "date": "2020-05-27",
      "transaction_datetime": "2020-05-27T17:23:22Z",
      "fees": 7.99,
      "investment_transaction_id": "LKoo1ko93wtreBwM7yQnuQ3P5DNKbKSPRzBNv",
      "iso_currency_code": "USD",
      "name": "BUY DoubleLine Total Return Bond Fund",
      "price": 10.42,
      "quantity": 0.7388014749727547,
      "security_id": "NDVQrXQoqzt5v3bAe8qRt4A7mK7wvZCLEBBJk",
      "subtype": "buy",
      "type": "buy",
      "unofficial_currency_code": null
    }
  ],
  "item": {
    "available_products": [
      "assets",
      "balance",
      "identity",
      "transactions"
    ],
    "billed_products": [
      "auth",
      "investments"
    ],
    "consent_expiration_time": null,
    "error": null,
    "institution_id": "ins_12",
    "item_id": "8Mqq5rqQ7Pcxq9MGDv3JULZ6yzZDLMCwoxGDq",
    "update_type": "background",
    "webhook": "https://www.genericwebhookurl.com/webhook"
  },
  "request_id": "iv4q3ZlytOOthkv",
  "securities": [
    {
      "close_price": 27,
      "close_price_as_of": null,
      "cusip": "577130834",
      "institution_id": null,
      "institution_security_id": null,
      "is_cash_equivalent": false,
      "isin": "US5771308344",
      "iso_currency_code": "USD",
      "name": "Matthews Pacific Tiger Fund Insti Class",
      "proxy_security_id": null,
      "security_id": "JDdP7XPMklt5vwPmDN45t3KAoWAPmjtpaW7DP",
      "sedol": null,
      "ticker_symbol": "MIPTX",
      "type": "mutual fund",
      "subtype": "mutual fund",
      "unofficial_currency_code": null,
      "update_datetime": null,
      "market_identifier_code": "XNAS",
      "sector": "Miscellaneous",
      "industry": "Investment Trusts or Mutual Funds",
      "cfi_code": "CIOGES",
      "figi": null,
      "option_contract": null,
      "fixed_income": null
    },
    {
      "close_price": 10.42,
      "close_price_as_of": null,
      "cusip": "258620103",
      "institution_id": null,
      "institution_security_id": null,
      "is_cash_equivalent": false,
      "isin": "US2586201038",
      "iso_currency_code": "USD",
      "name": "DoubleLine Total Return Bond Fund",
      "proxy_security_id": null,
      "security_id": "NDVQrXQoqzt5v3bAe8qRt4A7mK7wvZCLEBBJk",
      "sedol": null,
      "ticker_symbol": "DBLTX",
      "type": "mutual fund",
      "subtype": "mutual fund",
      "unofficial_currency_code": null,
      "update_datetime": null,
      "market_identifier_code": "XNAS",
      "sector": null,
      "industry": null,
      "cfi_code": "CIOIBS",
      "figi": null,
      "option_contract": null,
      "fixed_income": null
    },
    {
      "close_price": 34.73,
      "close_price_as_of": null,
      "cusip": "84470P109",
      "institution_id": null,
      "institution_security_id": null,
      "is_cash_equivalent": false,
      "isin": "US84470P1093",
      "iso_currency_code": "USD",
      "name": "Southside Bancshares Inc.",
      "proxy_security_id": null,
      "security_id": "eW4jmnjd6AtjxXVrjmj6SX1dNEdZp3Cy8RnRQ",
      "sedol": null,
      "ticker_symbol": "SBSI",
      "type": "equity",
      "subtype": "common stock",
      "unofficial_currency_code": null,
      "update_datetime": null,
      "market_identifier_code": "XNAS",
      "sector": "Finance",
      "industry": "Regional Banks",
      "cfi_code": "ESVUFR",
      "figi": null,
      "option_contract": null,
      "fixed_income": null
    }
  ],
  "total_investment_transactions": 3
}
```

\=\*=\*=\*=

#### /investments/refresh 

#### Refresh investment data 

[/investments/refresh](https://plaid.com/docs/api/products/investments/index.html.md#investmentsrefresh) is an optional endpoint for users of the Investments product. It initiates an on-demand extraction to fetch the newest investment holdings and transactions for an Item. This on-demand extraction takes place in addition to the periodic extractions that automatically occur one or more times per day for any Investments-enabled Item. If changes to investments are discovered after calling [/investments/refresh](https://plaid.com/docs/api/products/investments/index.html.md#investmentsrefresh) , Plaid will fire webhooks: [HOLDINGS: DEFAULT\_UPDATE](https://plaid.com/docs/api/products/investments/index.html.md#holdings-default_update) if any new holdings are detected, and [INVESTMENTS\_TRANSACTIONS: DEFAULT\_UPDATE](https://plaid.com/docs/api/products/investments/index.html.md#investments_transactions-default_update) if any new investment transactions are detected. This webhook will typically not fire in the Sandbox environment, due to the lack of dynamic investment transactions and holdings data. To test this webhook in Sandbox, call [/sandbox/item/fire\_webhook](https://plaid.com/docs/api/sandbox/index.html.md#sandboxitemfire_webhook) . Updated holdings and investment transactions can be fetched by calling [/investments/holdings/get](https://plaid.com/docs/api/products/investments/index.html.md#investmentsholdingsget) and [/investments/transactions/get](https://plaid.com/docs/api/products/investments/index.html.md#investmentstransactionsget) . Note that the [/investments/refresh](https://plaid.com/docs/api/products/investments/index.html.md#investmentsrefresh) endpoint is not supported by all institutions. If called on an Item from an institution that does not support this functionality, it will return a `PRODUCT_NOT_SUPPORTED` error.

As this endpoint triggers a synchronous request for fresh data, latency may be higher than for other Plaid endpoints (typically less than 10 seconds, but occasionally up to 30 seconds or more); if you encounter errors, you may find it necessary to adjust your timeout period when making requests.

[/investments/refresh](https://plaid.com/docs/api/products/investments/index.html.md#investmentsrefresh) is offered as an add-on to Investments and has a separate [fee model](https://plaid.com/docs/account/billing/index.html.md#per-request-flat-fee) . To request access to this endpoint, submit a [product access request](https://dashboard.plaid.com/team/products) or contact your Plaid account manager.

#### Request fields 

string

Your Plaid API `client_id`. The `client_id` is required and may be provided either in the `PLAID-CLIENT-ID` header or as part of a request body.

required, string

The access token associated with the Item for which data is being requested.

string

Your Plaid API `secret`. The `secret` is required and may be provided either in the `PLAID-SECRET` header or as part of a request body.

```bash
curl -X POST https://sandbox.plaid.com/investments/refresh \
 -H 'content-type: application/json' \
 -d '{
   "client_id": "${PLAID_CLIENT_ID}",
   "secret": "${PLAID_SECRET}",
   "access_token": String,
  }'

```

```node
const request: InvestmentsRefreshRequest = {
  access_token: accessToken,
};
try {
  await plaidClient.investmentsRefresh(request);
} catch (error) {
  // handle error
}

```

```ruby
request = Plaid::InvestmentsRefreshRequest.new({ access_token: access_token })
response = client.investments_refresh(request)

```

```java
InvestmentsRefreshRequest request = new InvestmentsRefreshRequest()
  .accessToken(accessToken);
Response response = client()
  .investmentsRefresh(request)
  .execute();

```

```python
request = InvestmentsRefreshRequest(access_token=access_token)
response = client.investments_refresh(request)

```

```go
request := plaid.NewInvestmentsRefreshRequest(accessToken)
response, _, err := client.PlaidApi.InvestmentsRefresh(ctx).InvestmentsRefreshRequest(*request).Execute()

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

### Webhooks 

Updates are sent to indicate that new holdings or investment transactions are available.

\=\*=\*=\*=

#### HOLDINGS: DEFAULT\_UPDATE 

Fired when new or updated holdings have been detected on an investment account. The webhook typically fires in response to any newly added holdings or price changes to existing holdings, most commonly after market close.

#### Properties 

string

`HOLDINGS`

string

`DEFAULT_UPDATE`

string

The `item_id` of the Item associated with this webhook, warning, or error

string

The Plaid `user_id` of the User associated with this webhook, warning, or error.

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

The number of new holdings reported since the last time this webhook was fired.

number

The number of updated holdings reported since the last time this webhook was fired.

string

The Plaid environment the webhook was sent from

Possible values: `sandbox`, `production`

API Object

```json
{
  "webhook_type": "HOLDINGS",
  "webhook_code": "DEFAULT_UPDATE",
  "item_id": "wz666MBjYWTp2PDzzggYhM6oWWmBb",
  "user_id": "usr_9nSp2KuZ2x4JDw",
  "error": null,
  "new_holdings": 19,
  "updated_holdings": 0,
  "environment": "production"
}
```

\=\*=\*=\*=

#### INVESTMENTS\_TRANSACTIONS: DEFAULT\_UPDATE 

Fired when new transactions have been detected on an investment account.

#### Properties 

string

`INVESTMENTS_TRANSACTIONS`

string

`DEFAULT_UPDATE`

string

The `item_id` of the Item associated with this webhook, warning, or error

string

The Plaid `user_id` of the User associated with this webhook, warning, or error.

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

The number of new transactions reported since the last time this webhook was fired.

number

The number of cancelled transactions reported since the last time this webhook was fired.

string

The Plaid environment the webhook was sent from

Possible values: `sandbox`, `production`

API Object

```json
{
  "webhook_type": "INVESTMENTS_TRANSACTIONS",
  "webhook_code": "DEFAULT_UPDATE",
  "item_id": "wz666MBjYWTp2PDzzggYhM6oWWmBb",
  "user_id": "usr_9nSp2KuZ2x4JDw",
  "error": null,
  "new_investments_transactions": 16,
  "cancelled_investments_transactions": 0,
  "environment": "production"
}
```

\=\*=\*=\*=

#### INVESTMENTS\_TRANSACTIONS: HISTORICAL\_UPDATE 

Fired after an asynchronous extraction on an investment account.

#### Properties 

string

`INVESTMENTS_TRANSACTIONS`

string

`HISTORICAL_UPDATE`

string

The `item_id` of the Item associated with this webhook, warning, or error

string

The Plaid `user_id` of the User associated with this webhook, warning, or error.

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

The number of new transactions reported since the last time this webhook was fired.

number

The number of cancelled transactions reported since the last time this webhook was fired.

string

The Plaid environment the webhook was sent from

Possible values: `sandbox`, `production`

API Object

```json
{
  "webhook_type": "INVESTMENTS_TRANSACTIONS",
  "webhook_code": "HISTORICAL_UPDATE",
  "item_id": "wz666MBjYWTp2PDzzggYhM6oWWmBb",
  "user_id": "usr_9nSp2KuZ2x4JDw",
  "error": null,
  "new_investments_transactions": 16,
  "cancelled_investments_transactions": 0,
  "environment": "production"
}
```