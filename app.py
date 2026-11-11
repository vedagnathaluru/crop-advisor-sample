"""Crop Decision Advisor - SAMPLE version (demo data, replace with real DES/APY CSV later)."""
import math, os, random, re, sqlite3, json, urllib.request
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


# ---- User-chosen intercropping and rotation checks (rule-based, SAMPLE agronomy rules) ----
FAMILY = {"Rice": "cereal", "Wheat": "cereal", "Maize": "cereal", "Bajra": "cereal", "Soybean": "legume",
          "Chickpea": "legume", "Groundnut": "legume", "Moong": "legume", "Mustard": "oilseed", "Cotton": "fibre"}
N_FIXED = 40   # kg N/ha a legume adds to the soil (sample value)

@app.route("/api/crops")
@login_required
def crops_api():
    return jsonify({c: dict(season=v[0], family=FAMILY[c]) for c, v in CROPS.items()})

def pair_rule(a, b):
    if a == b: return "Poor", "Same crop twice: competes for the same nutrients and shares pests."
    if b in INTER.get(a, []) or a in INTER.get(b, []):
        return "Good", "A proven combination: different root depth and little competition."
    fa, fb = FAMILY[a], FAMILY[b]
    if fa == "legume" and fb != "legume":
        return "Good", f"{a} adds nitrogen that {b} can use."
    if fb == "legume" and fa != "legume":
        return "Good", f"{b} adds nitrogen that {a} can use."
    if fa == fb:
        return "Poor", f"Both are {fa} crops: they compete for the same nutrients and share diseases."
    if CROPS[a][4][0] >= 80 and CROPS[b][4][0] >= 80:
        return "Poor", "Both take a lot of nitrogen, so each will starve the other."
    if CROPS[a][2] != CROPS[b][2]:
        return "Fair", "Different water needs: possible, but irrigation must suit both."
    return "Fair", "No strong benefit or conflict. Works with good spacing."

@app.route("/api/check-intercrop", methods=["POST"])
@login_required
def check_intercrop():
    chosen = [c for c in dict.fromkeys((request.get_json(force=True).get("crops") or [])) if c in CROPS][:4]
    if len(chosen) < 2: return jsonify(error="Pick at least 2 crops"), 400
    pairs, pts = [], {"Good": 2, "Fair": 1, "Poor": 0}
    for i in range(len(chosen)):
        for j in range(i + 1, len(chosen)):
            r, why = pair_rule(chosen[i], chosen[j]); pairs.append(dict(a=chosen[i], b=chosen[j], rating=r, reason=why))
    pct = round(100 * sum(pts[x["rating"]] for x in pairs) / (2 * len(pairs)))
    verdict = "Works well together" if pct >= 70 else "Workable with care" if pct >= 40 else "Not recommended"
    seasons = {CROPS[c][0] for c in chosen}
    note = "" if len(seasons) == 1 else "These crops belong to different seasons, so they will not be in the field at the same time. Check the overlap."
    return jsonify(pairs=pairs, score=pct, verdict=verdict, note=note,
                   tip="Add a legume such as Moong or Soybean to improve this mix." if not any(FAMILY[c] == "legume" for c in chosen) else "")

@app.route("/api/check-rotation", methods=["POST"])
@login_required
def check_rotation():
    d = request.get_json(force=True)
    seq = [(sl, d.get(sl.lower())) for sl in ("Kharif", "Rabi", "Zaid") if d.get(sl.lower()) in CROPS]
    if not seq: return jsonify(error="Pick at least one crop"), 400
    steps, n_balance, score = [], 0, 70
    order = ([("Before", d["previous"])] if d.get("previous") in CROPS else []) + seq
    for k, (slot, c) in enumerate(order):
        season, _, _, _, rem, legume = CROPS[c]; notes = []
        if slot != "Before" and season != slot:
            notes.append(f"{c} is normally a {season} crop, not {slot}."); score -= 10
        if k and FAMILY[c] == FAMILY[order[k - 1][1]] and FAMILY[c] != "legume":
            notes.append(f"Follows another {FAMILY[c]} crop: nutrients drop and pests build up."); score -= 15
        if k and c == order[k - 1][1]:
            notes.append("Same crop two seasons in a row."); score -= 10
        if slot != "Before":
            n_balance += rem[0] - (N_FIXED if legume else 0)
        if legume: notes.append(f"Fixes about {N_FIXED} kg N/ha for the next crop."); score += 8
        steps.append(dict(slot=slot, crop=c, notes=notes or ["Fits well here."]))
    score = max(5, min(98, score))
    verdict = "Healthy rotation" if score >= 70 else "Acceptable" if score >= 50 else "Weak rotation"
    legs = any(FAMILY[c] == "legume" for _, c in seq)
    tips = []
    if not legs: tips.append("Add a legume (Moong, Chickpea, Soybean or Groundnut) to rebuild nitrogen.")
    if n_balance > 120: tips.append("Soil nitrogen will fall a lot: add compost or farmyard manure.")
    return jsonify(steps=steps, score=score, verdict=verdict, tips=tips,
                   nitrogen=dict(removed=sum(CROPS[c][4][0] for _, c in seq), net=n_balance))

@app.route("/api/weather")
@login_required
def weather_api():
    try:
        lat, lng = float(request.args["lat"]), float(request.args["lng"])
        url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&current=temperature_2m,relative_humidity_2m,wind_speed_10m"
               "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max&timezone=auto&forecast_days=7") % (lat, lng)
        with urllib.request.urlopen(url, timeout=8) as r:
            w = json.loads(r.read())
        rain = round(sum(x or 0 for x in w["daily"]["precipitation_sum"]), 1)
        tip = ("Good rain expected this week: delay irrigation and watch for waterlogging." if rain > 30 else
               "Dry week ahead: plan irrigation before sowing." if rain < 5 else
               "Light rain expected: keep irrigation moderate.")
        return jsonify(current=w["current"], daily=w["daily"], rain_total=rain, tip=tip)
    except Exception:
        return jsonify(error="weather unavailable"), 502

if __name__ == "__main__":
    app.run(debug=True)
