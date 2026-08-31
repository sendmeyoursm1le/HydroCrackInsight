REPORT_TYPES = (
    "shift",
    "daily",
    "emergency",
    "resources",
)

from app.reports.report_service import ReportGenerationResult, ReportService

__all__ = [
    "REPORT_TYPES",
    "ReportGenerationResult",
    "ReportService",
]
