# API-Банки research

Source: [official API-Банки documentation](https://analizbankov.ru/api_help.php), based on a rendered snapshot and a supplied shorter overview (both no longer available). Findings are documentation analysis, not runtime observations. No live API requests, credentials, or personal data were used.

## Scope and common behavior

The official documentation lists nine methods at `https://analizbankov.ru/api/...`. Each supports GET or POST and returns a JSON string. Registration and a plan are described as prerequisites. Every method lists a string `key`; GET examples put it in the query. POST parameter/key placement and body encoding are unspecified. Each documented POST is retained in its path's `x-post-contract` research metadata with `sdk-ready: false`, not as an executable OpenAPI operation; the nested illustrative parameters mirror GET and do not establish POST placement or encoding. The query-key security scheme applies to GET operations only. Standard SDK generators therefore cannot mistake the assumptions for an implemented POST contract. There is no documented response text or file format beyond the JSON string; no invented text or file response is specified.

Inputs are not consistently marked required. Parameters are modeled as not required because enforcement is unknown; explicitly optional inputs are identified. The documentation says `pokid` or `pokname`, but does not say what happens if both or neither are sent. Dates are illustrated as `YYYY-MM-DD` without formally specifying accepted format. The BIC request is modeled as a string to preserve example leading zeroes despite the integer declaration. Other numeric/string alternatives reflect declared types versus examples, not verified server behavior; no response properties are asserted required.

No pagination parameters or response metadata are documented; this does not establish complete or unbounded results. Methods are described as retrieval or statistics, not modification; usage is tracked and limited, but whether each request, including failures and `stat`, consumes quota is unknown. HTTP success status codes, errors, rate-limit protocol, authentication failures, nullability and POST content type are unspecified. The `2XX` response is a modeling convention for generally documented success, not a documented status; no JSON error contract is asserted.

## Inventory

All methods also accept `key`. Response types below are documentation declarations; the specification annotates illustrated conflicts. See the [official method sections](https://analizbankov.ru/api_help.php) and snapshot lines cited below.

| Method | Inputs besides key | Response |
|---|---|---|
| `/api/bankdata` | `bankregn`, `pokid` or `pokname`, `date` | `Сумма` double (54–97) |
| `/api/bankinfo` | `bankregn` | Bank registration, name, legal, address, license and registration fields (216–249) |
| `/api/bankaraits` | `bankregn`, `date` | `items` array of rating name, agency, type, value (99–155) |
| `/api/bankbic` | `bankbic` | BIC, participant, account and optional date-code fields (157–190) |
| `/api/bankotch` | `bankregn`, `poktype`, `date` | `items` array of indicator IDs, names, values and parents (268–337) |
| `/api/banksrait` | `pokid` or `pokname`, `date`, optional `cond` | `items` array of bank registration, name and value (338–400) |
| `/api/listdata` | `groupid`, `pokid` or `pokname`, `date`, optional `type`, `cond` | `Сумма` double; `type` is `sum` (default), `avg`, or `count` (401–442) |
| `/api/pokinfo` | `pokid` or `pokname`, optional `date` | Indicator ID, name, unit, group, date, parent and formula (444–498) |
| `/api/stat` | none | Period and `Методы` usage information (500–558) |

## Discrepancies and unresolved questions

- **Swapped examples:** `bankbic` and `bankinfo` examples call the opposite methods. Their addresses and tables support the paths above. The BIC table example misnames its input `bankregn`; a matching example uses `bankbic` with leading zeroes (157–193, 216–267).
- **Ratings example:** The `bankaraits` address is `/api/bankaraits`, but its example uses `/api/bankdata` with `bankaraits%3Fdate` embedded in the query. Its name and agency are declared integers and value double, but illustrated as strings (99–155).
- **Type/shape conflicts:** Examples quote `Сумма`, IDs and registration numbers declared numeric. `pokname` is declared integer in `bankotch` and `pokinfo` but described and illustrated as a string. `bankbic.СчетСтатус` is declared an array but illustrated as a string. `stat.Методы` is declared an array but illustrated as an object keyed by method with string `Лимит` and `Истрачено` (76–97, 175–190, 235–267, 289–337, 362–400, 429–442, 464–493, 500–558). Array element types not documented are left broad.
- **Ordering and extra input:** The [detailed `banksrait` documentation](https://analizbankov.ru/api_help.php) says unsorted, whereas the [shorter overview](https://damia.ru/apibanki) says ascending. Its example includes `bankregn`, absent from the input table; its effect is unknown (338–400; shorter snapshot line 42). Neither ordering nor the extra parameter is asserted.
- **Negative filter:** `listdata` prints `sum>0` for both positive and negative conditions. The correct negative expression is unknown (419–425). List inclusion/exclusion forms are documented as `in list (n1,n2,...)` and `not in list (n1,n2,...)`.
- **Statistics coverage:** The table lists `sbankdata,bankinfo,...`, while the example uses `bankdata` and only six method keys, omitting `bankaraits`, `bankbic`, and `stat`; actual coverage and metering are unknown (500–558).
- **Other example fidelity:** `parent_pokid` is symbolic in `bankotch` and numeric-looking text in `pokinfo`; treat as opaque. Unit text differs between Cyrillic `Т` and example Latin `T`. The displayed multiline formula contains raw newlines within a JSON string, and some examples contain ellipses; they are not verbatim JSON fixtures (289–337, 464–498).

## Residual risk

Actual wire types, validation and requiredness, selector handling, POST encoding, errors, ordering, result completeness, negative-filter syntax and quota effects require provider confirmation or separately authorized non-production testing. Keep keys out of logs; query-key exposure is an operational risk. No runtime interoperability is claimed.
