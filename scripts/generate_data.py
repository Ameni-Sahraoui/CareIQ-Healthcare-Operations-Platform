from careiq.config import DB_PATH, DEMO_CONFIG, MANIFEST_PATH, ensure_directories
from careiq.database import initialize_database
from careiq.synthetic import generate_synthetic_data

ensure_directories()
initialize_database(DB_PATH, reset=True)
generate_synthetic_data(DB_PATH, DEMO_CONFIG, MANIFEST_PATH)
print(DB_PATH)
