from careiq.config import DB_PATH, FORECAST_METRICS_PATH, MANIFEST_PATH, MODEL_BUNDLE_PATH
from careiq.forecasting import train_forecast_model

print(train_forecast_model(DB_PATH, MODEL_BUNDLE_PATH, FORECAST_METRICS_PATH, 42, MANIFEST_PATH))
