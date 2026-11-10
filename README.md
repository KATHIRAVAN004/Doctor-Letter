# Doctor Letters (Flask, local storage)

    python -m venv venv
    venv\Scripts\activate        # Windows   (Linux/Mac: source venv/bin/activate)
    pip install -r requirements.txt
    set SECRET_KEY=some-long-random      # Linux/Mac: export SECRET_KEY=...
    flask --app app add-doctor           # register a doctor's mobile + letterhead
    flask --app app run                  # open http://127.0.0.1:5000

Files are saved in the ./data folder (override with DATA_DIR). Back it up regularly.
Add letter types in letter_templates.py.
