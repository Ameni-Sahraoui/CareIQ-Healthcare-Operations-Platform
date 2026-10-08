from careiq.config import DB_PATH, MANIFEST_PATH
from careiq.feature_store import build_feature_store

print(build_feature_store(DB_PATH, MANIFEST_PATH))
