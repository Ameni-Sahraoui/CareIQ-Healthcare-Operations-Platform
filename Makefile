.PHONY: install run demo full test export audit clean

install:
	python -m pip install -r requirements.txt

run:
	python -m streamlit run app.py

demo:
	python -m careiq.bootstrap --mode demo

full:
	python -m careiq.bootstrap --mode full

test:
	pytest -q

export:
	python scripts/export_powerbi.py

audit:
	python scripts/run_audit.py

clean:
	rm -f data/careiq.sqlite data/careiq.sqlite-wal data/careiq.sqlite-shm
	rm -f artifacts/*.joblib artifacts/*.json exports/*.csv
