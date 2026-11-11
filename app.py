"""Crop Decision Advisor - SAMPLE version (demo data, replace with real DES/APY CSV later)."""
import math, os, random, re, sqlite3, json
from functools import wraps
from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")   # set SECRET_KEY on Render
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
DB = os.environ.get("DB_PATH", "users.db")

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB); g.db.row_factory = sqlite3.Row
        g.db.executescript("""CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, pw TEXT);
        CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, user_id INTEGER, state TEXT, soil TEXT, water TEXT,
        best TEXT, score INTEGER, created TEXT DEFAULT CURRENT_TIMESTAMP);""")
    return g.db

@app.teardown_appcontext
def close_db(_):
    d = g.pop("db", None)
    if d: d.close()

def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if "uid" not in session:
            if request.path.startswith("/api/"): return jsonify(error="login required"), 401
            return redirect(url_for("login"))
        return f(*a, **k)
    return w

@app.route("/register", methods=["GET", "POST"])
def register():
    err = ""
    if request.method == "POST":
        n, e, p = request.form["name"].strip(), request.form["email"].strip().lower(), request.form["password"]
        if not n or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", e): err = "Enter your name and a valid email."
        elif len(p) < 8: err = "Password must be at least 8 characters."
        elif db().execute("SELECT 1 FROM users WHERE email=?", (e,)).fetchone(): err = "This email is already registered. Log in instead."
        else:
            cur = db().execute("INSERT INTO users(name,email,pw) VALUES(?,?,?)", (n, e, generate_password_hash(p))); db().commit()
            session.clear(); session["uid"], session["name"] = cur.lastrowid, n
            return redirect(url_for("home"))
    return render_template("auth.html", mode="register", err=err)

@app.route("/login", methods=["GET", "POST"])
def login():
    err = ""
    if request.method == "POST":
        u = db().execute("SELECT * FROM users WHERE email=?", (request.form["email"].strip().lower(),)).fetchone()
        if u and check_password_hash(u["pw"], request.form["password"]):
            session.clear(); session["uid"], session["name"] = u["id"], u["name"]
            return redirect(url_for("home"))
        err = "Email or password is incorrect."
    return render_template("auth.html", mode="login", err=err)

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("login"))

@app.route("/api/history")
@login_required
def history_api():
    rows = db().execute("SELECT state,soil,water,best,score,created FROM history WHERE user_id=? ORDER BY id DESC LIMIT 20", (session["uid"],)).fetchall()
    return jsonify([dict(r) for r in rows])
YEARS = list(range(2019, 2025))

# ---- SAMPLE DATA (not real). Real version: load district-wise APY CSV with pandas ----
STATES = {  # name: (lat, lng)
 "Punjab": (30.9, 75.8), "Uttar Pradesh": (26.8, 80.9), "Maharashtra": (19.7, 75.7),
 "Karnataka": (15.3, 75.7), "West Bengal": (23.0, 87.9), "Gujarat": (22.3, 71.8),
 "Tamil Nadu": (11.1, 78.7), "Rajasthan": (27.0, 74.2)}
# crop: season, base yield t/ha, water need, soils, N-P-K removal kg/ha, legume?
CROPS = {
 "Rice": ("Kharif", 2.7, "high", ["Clay", "Loam"], (80, 30, 40), False),
 "Wheat": ("Rabi", 3.2, "medium", ["Loam", "Clay"], (90, 40, 40), False),
 "Maize": ("Kharif", 3.0, "medium", ["Loam", "Sandy"], (100, 40, 50), False),
 "Cotton": ("Kharif", 0.5, "medium", ["Black", "Loam"], (90, 30, 50), False),
 "Soybean": ("Kharif", 1.1, "medium", ["Black", "Loam"], (30, 25, 30), True),
 "Chickpea": ("Rabi", 1.0, "low", ["Sandy", "Loam", "Black"], (20, 20, 20), True),
 "Mustard": ("Rabi", 1.4, "low", ["Sandy", "Loam"], (60, 25, 30), False),
 "Bajra": ("Kharif", 1.3, "low", ["Sandy"], (50, 20, 25), False),
 "Groundnut": ("Kharif", 1.6, "low", ["Sandy", "Loam"], (25, 20, 35), True),
 "Moong": ("Zaid", 0.8, "low", ["Sandy", "Loam"], (20, 20, 20), True),
}
STATE_CROPS = {s: random.Random(s).sample(list(CROPS), 7) for s in STATES}
INTER = {"Maize": ["Soybean", "Moong"], "Cotton": ["Moong", "Groundnut"], "Wheat": ["Mustard", "Chickpea"],
         "Rice": ["Moong"], "Soybean": ["Maize"], "Chickpea": ["Mustard", "Wheat"],
         "Mustard": ["Chickpea"], "Bajra": ["Moong"], "Groundnut": ["Bajra"], "Moong": ["Maize", "Bajra"]}

def history(state, crop):
    r = random.Random(state + crop)
    base = CROPS[crop][1] * r.uniform(0.85, 1.15)
    return [round(base * (1 + 0.02 * i + r.uniform(-0.06, 0.06)), 2) for i in range(len(YEARS))]

def forecast(ys, n=3):
    xs = list(range(len(ys))); mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    a = my - b * mx
    resid = [y - (a + b * x) for x, y in zip(xs, ys)]
    sd = math.sqrt(sum(e * e for e in resid) / max(1, len(ys) - 2))
    return [round(a + b * (len(ys) + i), 2) for i in range(n)], round(sd, 2), b / my

def nearest_state(lat, lng):
    return min(STATES, key=lambda s: (STATES[s][0] - lat) ** 2 + (STATES[s][1] - lng) ** 2)

@app.route("/")
@login_required
def home():
    return render_template("index.html", user=session["name"])

@app.route("/api/states")
@login_required
@login_required
@login_required
def states():
    return jsonify({s: {"lat": v[0], "lng": v[1], "crops": STATE_CROPS[s]} for s, v in STATES.items()})

@app.route("/api/recommend", methods=["POST"])
@login_required
@login_required
@login_required
def recommend():
    d = request.get_json(force=True)
    state = nearest_state(float(d["lat"]), float(d["lng"]))
    soil, water, prev = d.get("soil", "Loam"), d.get("water", "medium"), d.get("previous", "")
    size = float(d.get("size") or 1)
    npk = d.get("npk", {"N": "Medium", "P": "Medium", "K": "Medium"})
    cards = []
    for c in STATE_CROPS[state]:
        season, _, need, soils, rem, legume = CROPS[c]
        ys = history(state, c); fc, sd, trend = forecast(ys)
        cv = sd / (sum(ys) / len(ys))
        score = 50 + trend * 300 - cv * 120
        score += 18 if soil in soils else -10
        score += {0: 12, 1: 4, 2: -12}[abs(["low", "medium", "high"].index(need) - ["low", "medium", "high"].index(water))]
        if prev == c: score -= 15          # avoid repeating the same crop
        if prev and legume and prev not in INTER.get(c, []) and CROPS.get(prev, (0,)*6)[5] is False: score += 5
        score = max(5, min(98, round(score)))
        tag = "Highly suitable" if score >= 70 else "Moderate" if score >= 50 else "Risky"
        cards.append(dict(crop=c, season=season, score=score, tag=tag, history=ys, forecast=fc, error=sd,
                          expected=round(fc[0] * size, 2), inter=INTER.get(c, []), removal=rem, legume=legume))
    cards.sort(key=lambda x: -x["score"])
    best = cards[0]
    plan = []
    for season, pool in (("Kharif", [c for c in cards if c["season"] == "Kharif"]),
                         ("Rabi", [c for c in cards if c["season"] == "Rabi"]),
                         ("Zaid", [c for c in cards if c["season"] == "Zaid"])):
        if pool: plan.append(dict(season=season, crop=pool[0]["crop"]))
    # simple rotation rule: put a legume where the previous crop was a cereal/oilseed
    legs = [c["crop"] for c in cards if c["legume"]]
    if prev and legs and not CROPS.get(prev, (0,)*6)[5]:
        plan.append(dict(season="Next break", crop=legs[0] + " (restores nitrogen)"))
    level = {"Low": 0, "Medium": 1, "High": 2}
    advice = []
    for k, name, org in (("N", "Nitrogen", "legume cover crop or farmyard manure"),
                         ("P", "Phosphorus", "compost or bone meal"), ("K", "Potassium", "wood ash or crop residue")):
        if level.get(npk.get(k), 1) == 0: advice.append(f"{name} is low: add {org}.")
    if best["legume"]: advice.append(f"{best['crop']} fixes nitrogen, so the next cereal needs less fertiliser.")
    if not advice: advice.append("Soil nutrients look balanced: maintain with compost and residue mulching.")
    db().execute("INSERT INTO history(user_id,state,soil,water,best,score) VALUES(?,?,?,?,?,?)",
                 (session["uid"], state, soil, water, best["crop"], best["score"])); db().commit()
    return jsonify(state=state, cards=cards, rotation=plan, advice=advice, years=YEARS,
                   nutrient=dict(crop=best["crop"], removal=dict(zip("NPK", best["removal"]))))

if __name__ == "__main__":
    app.run(debug=True)
