Run locally:  pip install -r requirements.txt  then  python app.py  (open http://127.0.0.1:5000)
Users are stored in users.db (SQLite, created automatically). Register first, then log in.
Deploy on Render: push to GitHub, new Web Service, build: pip install -r requirements.txt, start: gunicorn app:app
Set environment variable SECRET_KEY to a long random string on Render.
Note: Render's free disk is temporary, so users.db resets on redeploy. For permanent accounts use Render's free Postgres later.
Crop numbers are SAMPLE data. Weather is live from Open-Meteo (no key needed).
