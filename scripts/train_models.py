from careiq.config import DB_PATH, MANIFEST_PATH, METRICS_PATH, MODEL_BUNDLE_PATH
from careiq.modeling import train_models

print(train_models(DB_PATH, MODEL_BUNDLE_PATH, METRICS_PATH, 42, MANIFEST_PATH))
