"""
Intentionally vulnerable Flask app — SQL injection demo (educational use only).

The `/?id=<n>` route builds its SQL by string concatenation, so it is
deliberately injectable. Do NOT use this pattern in real applications.
"""
import os
import time
import unicodedata

from flask import Flask, request, render_template_string
import pymysql

app = Flask(__name__)


def connect(db=True):
    return pymysql.connect(
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", 3306)),
        user=os.environ.get("DB_USER", "app"),
        password=os.environ.get("DB_PASSWORD", "app"),
        database=os.environ.get("DB_NAME", "app") if db else None,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def wait_for_db(retries=30, delay=2):
    """Block until the database accepts connections (startup race with MySQL)."""
    for attempt in range(1, retries + 1):
        try:
            conn = connect()
            conn.close()
            print(f"[startup] database is up (attempt {attempt})", flush=True)
            return
        except Exception as exc:  # noqa: BLE001
            print(f"[startup] waiting for database ({attempt}/{retries}): {exc}", flush=True)
            time.sleep(delay)
    raise RuntimeError("database did not become available in time")


# Last column: is_private (0 = public/listed, 1 = private/hidden from the listing).
SAMPLE_EVENTS = [
    ("Synthwave Nights", "Neon Arena", "Bratislava", "2026-07-04", "Music", 39.00,
     "A retro-futuristic synth concert with laser visuals and special guests.", 0),
    ("Kafka & Coffee", "Old Town Library", "Vienna", "2026-07-11", "Talk", 0.00,
     "An open discussion about distributed systems over free espresso.", 0),
    ("Marathon of the Danube", "Riverside Park", "Budapest", "2026-08-02", "Sport", 25.00,
     "A scenic 42 km run along the Danube with live music at every checkpoint.", 0),
    ("Indie Game Expo", "Tech Pavilion", "Prague", "2026-08-15", "Tech", 18.50,
     "Hands-on demos from 40+ independent studios and a pitch competition.", 0),
    ("Street Food Festival", "Central Market", "Bratislava", "2026-08-23", "Food", 5.00,
     "Dozens of stalls serving world cuisine, craft beer and live cooking shows.", 0),
    ("Open Air Cinema: Classics", "Castle Hill", "Bratislava", "2026-09-01", "Film", 12.00,
     "Outdoor screenings of restored film classics under the stars.", 0),
    ("Jazz on the Square", "Main Square", "Kosice", "2026-09-12", "Music", 22.00,
     "An evening of smooth jazz with international quartets and a jam session.", 0),
    ("Startup Demo Day", "Innovation Hub", "Brno", "2026-09-20", "Tech", 0.00,
     "Fifteen early-stage startups present to investors and the public.", 0),
    # --- private events: hidden from the public listing, only leak via SQL injection ---
    ("VIP Investor Dinner", "Rooftop Suite", "Bratislava", "2026-09-25", "Private", 500.00,
     "Closed-door dinner with the board and lead investors. Guest list confidential.", 1),
    ("Internal Security Briefing", "HQ War Room", "Bratislava", "2026-10-02", "Private", 0.00,
     "Incident post-mortem and unreleased patch timeline. Staff with clearance only.", 1),
    ("Founders' Secret Afterparty", "Undisclosed Location", "Vienna", "2026-10-18", "Private", 0.00,
     "Address sent to invitees 1 hour before. Strictly no press.", 1),
]

FIRST_NAMES = ["Anna", "Boris", "Clara", "David", "Eva",
               "Filip", "Gabriela", "Henrich", "Iveta", "Jakub"]
LAST_NAMES = ["Novak", "Kovac", "Horvath", "Varga", "Tóth"]

EMAIL_DOMAINS = ["gmail.com", "zoznam.sk", "protonmail.com", "outlook.com",
                 "yahoo.com", "icloud.com", "azet.sk"]


def _ascii(text):
    """Fold accents to plain ASCII so emails contain no special characters."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


# Top 20 most-used passwords (classic breach-corpus ranking). Plaintext on
# purpose — the leak demo is far more striking when most creds are trivially weak.
COMMON_PASSWORDS = [
    "123456", "password", "123456789", "12345678", "12345",
    "qwerty", "1234567", "111111", "1234567890", "123123",
    "abc123", "1234", "password1", "iloveyou", "1q2w3e4r",
    "000000", "qwerty123", "zaq12wsx", "dragon", "sunshine",
]

# A couple of users practise good hygiene — strong, unique passwords.
STRONG_PASSWORDS = {7: "G7!vQ2$mZx9pLw#kR3n", 23: "x9#Kp2!mB6$qT4vL8wZ"}


def _build_users():
    """Deterministically generate 50 users (10 first names × 5 surnames)."""
    users = []
    i = 0
    for last in LAST_NAMES:
        for first in FIRST_NAMES:
            i += 1
            domain = EMAIL_DOMAINS[(i - 1) % len(EMAIL_DOMAINS)]
            email = f"{_ascii(first).lower()}{_ascii(last).lower()}{i}@{domain}"
            phone = f"+421 9{i:02d} {100 + i:03d} {200 + i:03d}"
            password = STRONG_PASSWORDS.get(i, COMMON_PASSWORDS[(i - 1) % len(COMMON_PASSWORDS)])
            users.append((first, last, email, phone, password))
    return users


SAMPLE_USERS = _build_users()


def _build_attendees(n_users, n_events):
    """Assign each user to 1–2 events (assumes fresh sequential ids 1..N)."""
    rows = []
    for user_id in range(1, n_users + 1):
        event_id = ((user_id - 1) % n_events) + 1
        rows.append((event_id, user_id))
        event_id2 = ((user_id * 3) % n_events) + 1
        if event_id2 != event_id:
            rows.append((event_id2, user_id))
    return rows


# --- data for the hidden tables (never shown in the UI, only reachable via SQLi) ---

def _build_credit_cards(n_cards=15):
    """Fake payment data for the first N users (test card numbers, not real)."""
    cards = []
    for user_id in range(1, n_cards + 1):
        first, last, *_ = SAMPLE_USERS[user_id - 1]
        cardholder = f"{first} {last}"
        card_number = f"4111 1111 1111 {1000 + user_id:04d}"
        cvv = f"{(user_id * 7) % 900 + 100:03d}"
        expiry = f"{(user_id % 12) + 1:02d}/27"
        cards.append((user_id, cardholder, card_number, cvv, expiry))
    return cards


SAMPLE_CARDS = _build_credit_cards()

SAMPLE_API_KEYS = [
    ("billing-service", "demo_live_4f9a2c7e8b1d6034a5e2", "read,write", "2026-01-15 09:00:00"),
    ("analytics-readonly", "demo_live_a1b2c3d4e5f6a7b8c9d0", "read", "2026-02-02 11:30:00"),
    ("ci-deploy-bot", "demo_live_deadbeef00112233445566", "deploy", "2026-03-10 14:20:00"),
    ("mobile-app", "demo_live_9988776655443322110aabbc", "read,write", "2026-03-22 08:05:00"),
    ("partner-webhook", "demo_live_0fae12bc34de56fa78901234", "webhook", "2026-04-01 16:45:00"),
    ("legacy-export", "demo_live_cafebabe99887766554433", "read,export", "2026-04-18 22:10:00"),
]


def _build_audit_log(n=30):
    actions = ["login", "logout", "view_event", "update_profile", "failed_login", "export_data"]
    agents = ["Mozilla/5.0 (Macintosh)", "Mozilla/5.0 (Windows NT 10.0)",
              "curl/8.4.0", "PostmanRuntime/7.36"]
    rows = []
    for k in range(1, n + 1):
        user_id = ((k - 1) % len(SAMPLE_USERS)) + 1
        action = actions[(k - 1) % len(actions)]
        ip = f"10.0.{k % 5}.{(k * 3) % 254 + 1}"
        ua = agents[(k - 1) % len(agents)]
        ts = f"2026-06-{(k % 28) + 1:02d} {(k % 24):02d}:{(k * 7) % 60:02d}:00"
        rows.append((user_id, action, ip, ua, ts))
    return rows


SAMPLE_AUDIT = _build_audit_log()


def _seed_once(cur, table, insert_sql, rows):
    """executemany the rows only if the table is currently empty (idempotent)."""
    cur.execute(f"SELECT COUNT(*) AS c FROM {table}")
    if cur.fetchone()["c"] == 0:
        cur.executemany(insert_sql, rows)
        print(f"[startup] seeded {len(rows)} {table}", flush=True)
    else:
        print(f"[startup] {table} already present, skipping seed", flush=True)


def init_db():
    """Create the events table and seed sample rows once (idempotent)."""
    conn = connect()
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id          INT AUTO_INCREMENT PRIMARY KEY,
                title       VARCHAR(200) NOT NULL,
                venue       VARCHAR(200) NOT NULL,
                city        VARCHAR(100) NOT NULL,
                event_date  DATE NOT NULL,
                category    VARCHAR(50)  NOT NULL,
                price       DECIMAL(8,2) NOT NULL DEFAULT 0,
                description TEXT,
                is_private  TINYINT(1)   NOT NULL DEFAULT 0
            )
            """
        )
        cur.execute("SELECT COUNT(*) AS c FROM events")
        if cur.fetchone()["c"] == 0:
            cur.executemany(
                """INSERT INTO events
                   (title, venue, city, event_date, category, price, description, is_private)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                SAMPLE_EVENTS,
            )
            print(f"[startup] seeded {len(SAMPLE_EVENTS)} events", flush=True)
        else:
            print("[startup] events already present, skipping seed", flush=True)

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id         INT AUTO_INCREMENT PRIMARY KEY,
                first_name VARCHAR(50)  NOT NULL,
                last_name  VARCHAR(50)  NOT NULL,
                email      VARCHAR(120) NOT NULL,
                phone      VARCHAR(40)  NOT NULL,
                password   VARCHAR(100) NOT NULL
            )
            """
        )
        cur.execute("SELECT COUNT(*) AS c FROM users")
        if cur.fetchone()["c"] == 0:
            cur.executemany(
                """INSERT INTO users (first_name, last_name, email, phone, password)
                   VALUES (%s, %s, %s, %s, %s)""",
                SAMPLE_USERS,
            )
            print(f"[startup] seeded {len(SAMPLE_USERS)} users", flush=True)
        else:
            print("[startup] users already present, skipping seed", flush=True)

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS attendees (
                event_id INT NOT NULL,
                user_id  INT NOT NULL,
                PRIMARY KEY (event_id, user_id)
            )
            """
        )
        cur.execute("SELECT COUNT(*) AS c FROM attendees")
        if cur.fetchone()["c"] == 0:
            attendees = _build_attendees(len(SAMPLE_USERS), len(SAMPLE_EVENTS))
            cur.executemany(
                "INSERT INTO attendees (event_id, user_id) VALUES (%s, %s)",
                attendees,
            )
            print(f"[startup] seeded {len(attendees)} attendee links", flush=True)
        else:
            print("[startup] attendees already present, skipping seed", flush=True)

        # --- hidden tables: never referenced by the UI, only reachable via SQLi ---
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS credit_cards (
                id              INT AUTO_INCREMENT PRIMARY KEY,
                user_id         INT NOT NULL,
                cardholder_name VARCHAR(100) NOT NULL,
                card_number     VARCHAR(25)  NOT NULL,
                cvv             VARCHAR(4)   NOT NULL,
                expiry          VARCHAR(7)   NOT NULL
            )
            """
        )
        _seed_once(
            cur, "credit_cards",
            """INSERT INTO credit_cards (user_id, cardholder_name, card_number, cvv, expiry)
               VALUES (%s, %s, %s, %s, %s)""",
            SAMPLE_CARDS,
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                id         INT AUTO_INCREMENT PRIMARY KEY,
                owner      VARCHAR(80)  NOT NULL,
                token      VARCHAR(120) NOT NULL,
                scope      VARCHAR(60)  NOT NULL,
                created_at DATETIME     NOT NULL
            )
            """
        )
        _seed_once(
            cur, "api_keys",
            "INSERT INTO api_keys (owner, token, scope, created_at) VALUES (%s, %s, %s, %s)",
            SAMPLE_API_KEYS,
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id         INT AUTO_INCREMENT PRIMARY KEY,
                user_id    INT NOT NULL,
                action     VARCHAR(40)  NOT NULL,
                ip_address VARCHAR(45)  NOT NULL,
                user_agent VARCHAR(200) NOT NULL,
                created_at DATETIME     NOT NULL
            )
            """
        )
        _seed_once(
            cur, "audit_log",
            """INSERT INTO audit_log (user_id, action, ip_address, user_agent, created_at)
               VALUES (%s, %s, %s, %s, %s)""",
            SAMPLE_AUDIT,
        )
    conn.close()


PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Events — SQLi demo</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
<nav class="navbar navbar-dark bg-dark">
  <div class="container">
    <a class="navbar-brand" href="/">🎟️ EventBoard</a>
    <span class="navbar-text text-warning small">SQL injection demo — intentionally vulnerable</span>
  </div>
</nav>

<div class="container py-4">

  <form class="row g-2 mb-4" method="get" action="/">
    <div class="col-auto">
      <label class="col-form-label">Look up event by id</label>
    </div>
    <div class="col-auto">
      <input type="text" name="id" class="form-control" value="{{ id if id is not none else '' }}" placeholder="e.g. 1">
    </div>
    <div class="col-auto">
      <button class="btn btn-primary" type="submit">View</button>
    </div>
    <div class="col-auto">
      <a class="btn btn-outline-secondary" href="/">Show all</a>
    </div>
  </form>

  {% if query %}
  <div class="card mb-4 border-warning">
    <div class="card-header bg-warning-subtle">Executed SQL</div>
    <div class="card-body"><code>{{ query }}</code></div>
  </div>
  {% endif %}

  {% if error %}
  <div class="alert alert-danger"><strong>SQL error:</strong> {{ error }}</div>
  {% endif %}

  {% if rows and detail %}
    {% for e in rows %}
    <div class="card shadow-sm mb-4 {{ 'border-danger border-2' if e.is_private else '' }}">
      {% if e.is_private %}
      <div class="card-header bg-danger text-white d-flex align-items-center gap-2">
        🔒 <strong>PRIVATE EVENT</strong>
        <span class="small ms-auto">hidden from the public listing — exposed via SQL injection</span>
      </div>
      {% endif %}
      <div class="card-body">
        <div class="d-flex justify-content-between align-items-start">
          <div>
            <span class="badge text-bg-info mb-2">{{ e.category }}</span>
            {% if e.is_private %}
            <span class="badge text-bg-danger mb-2">🔒 Private</span>
            {% else %}
            <span class="badge text-bg-success mb-2">🌐 Public</span>
            {% endif %}
            <h2 class="card-title mb-1">{{ e.title }}</h2>
            <h6 class="card-subtitle text-muted">{{ e.venue }}, {{ e.city }}</h6>
          </div>
          <span class="badge text-bg-success fs-6 align-self-center">
            {{ "Free" if e.price == 0 else "€%.2f"|format(e.price) }}
          </span>
        </div>
        <hr>
        <dl class="row mb-0">
          <dt class="col-sm-3">Event ID</dt><dd class="col-sm-9">{{ e.id }}</dd>
          <dt class="col-sm-3">Date</dt><dd class="col-sm-9">{{ e.event_date }}</dd>
          <dt class="col-sm-3">Category</dt><dd class="col-sm-9">{{ e.category }}</dd>
          <dt class="col-sm-3">Description</dt><dd class="col-sm-9">{{ e.description }}</dd>
        </dl>
        {% if e.attendees %}
        <hr>
        <h6 class="text-muted">Attendees ({{ e.attendees|length }})</h6>
        <table class="table table-sm table-striped table-bordered align-middle mb-1">
          <thead class="table-light">
            <tr><th style="width:3rem">#</th><th>Attendee</th></tr>
          </thead>
          <tbody>
            {% for a in e.attendees %}
            <tr>
              <td class="text-muted">{{ loop.index }}</td>
              <td>{{ a.first_name }} {{ a.last_name[0] }}.</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
        <p class="form-text">Only first name + last initial are shown to the public.</p>
        {% endif %}
      </div>
    </div>
    {% endfor %}
    <a class="btn btn-outline-secondary" href="/">&larr; Back to all events</a>
  {% elif rows %}
  <div class="row row-cols-1 row-cols-md-2 row-cols-lg-3 g-4">
    {% for e in rows %}
    <div class="col">
      <div class="card h-100 shadow-sm">
        <div class="card-body">
          <span class="badge text-bg-info mb-2">{{ e.category }}</span>
          <span class="badge text-bg-success mb-2">🌐 Public</span>
          <h5 class="card-title">{{ e.title }}</h5>
          <h6 class="card-subtitle mb-2 text-muted">{{ e.venue }}, {{ e.city }}</h6>
          <p class="card-text">{{ e.description }}</p>
        </div>
        <div class="card-footer d-flex justify-content-between align-items-center">
          <small class="text-muted">{{ e.event_date }}</small>
          <span class="fw-bold">{{ "Free" if e.price == 0 else "€%.2f"|format(e.price) }}</span>
          <a class="btn btn-sm btn-outline-primary" href="/?id={{ e.id }}">Details</a>
        </div>
      </div>
    </div>
    {% endfor %}
  </div>
  {% elif not error %}
  <div class="alert alert-secondary">No events found.</div>
  {% endif %}

</div>
</body>
</html>
"""


@app.route("/")
def index():
    event_id = request.args.get("id")
    conn = connect()
    rows, error, query = [], None, None
    try:
        with conn.cursor() as cur:
            if event_id is not None:
                # ⚠️ INTENTIONALLY VULNERABLE: user input concatenated into SQL.
                query = "SELECT * FROM events WHERE id = " + event_id
                cur.execute(query)
            else:
                # Public listing hides private events. The detail query above does
                # NOT apply this filter — that is what the injection exploits.
                cur.execute("SELECT * FROM events WHERE is_private = 0 ORDER BY event_date")
            rows = cur.fetchall()

            if event_id is not None:
                # Intended UI: show only first name + last initial of attendees.
                # (Parameterised — the only vulnerable query is the events lookup above.)
                for r in rows:
                    if r.get("id") is None:
                        continue
                    cur.execute(
                        """SELECT first_name, last_name
                           FROM users u JOIN attendees a ON a.user_id = u.id
                           WHERE a.event_id = %s ORDER BY first_name""",
                        (r["id"],),
                    )
                    r["attendees"] = cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
    finally:
        conn.close()
    return render_template_string(
        PAGE, rows=rows, id=event_id, error=error, query=query,
        detail=event_id is not None,
    )


@app.route("/health")
def health():
    try:
        conn = connect()
        conn.close()
        return {"status": "ok", "db": "up"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "ok", "db": "down", "error": str(exc)}, 503


if __name__ == "__main__":
    wait_for_db()
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=True)
