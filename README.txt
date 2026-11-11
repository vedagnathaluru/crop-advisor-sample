Run locally:  pip install -r requirements.txt  then  python app.py  (open http://127.0.0.1:5000)
Deploy: push to GitHub, create a Render Web Service, build: pip install -r requirements.txt, start: gunicorn app:app
This is a SAMPLE using demo data. Real DES/APY data replaces history() in app.py.
