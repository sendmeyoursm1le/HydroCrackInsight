FORECAST_INPUT_CODES = (
    "temperature",
    "pressure",
    "feed_flow",
    "hydrogen_flow",
)

from app.forecasting.process_forecaster import (
    FORECAST_SCENARIOS,
    ForecastResult,
    ForecastScenario,
    ProcessForecastService,
)

__all__ = [
    "FORECAST_INPUT_CODES",
    "FORECAST_SCENARIOS",
    "ForecastResult",
    "ForecastScenario",
    "ProcessForecastService",
]
