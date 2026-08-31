from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class ResourceLimit:
    code: str
    name: str
    measurement_unit: str
    shift_limit: float
    daily_limit: float


@dataclass(frozen=True)
class ResourceUsageSample:
    timestamp: datetime
    resource_code: str
    resource_name: str
    value: float
    measurement_unit: str
    mode: str


@dataclass(frozen=True)
class ResourceSummary:
    resource_code: str
    resource_name: str
    measurement_unit: str
    shift_total: float
    shift_limit: float
    shift_status: str
    daily_total: float
    daily_limit: float
    daily_status: str


DATETIME_FORMAT = "%d.%m.%Y %H:%M:%S"

RESOURCE_LIMITS = {
    "hydrogen": ResourceLimit(
        code="hydrogen",
        name="Водород",
        measurement_unit="нм³",
        shift_limit=36_000.0,
        daily_limit=72_000.0,
    ),
    "energy": ResourceLimit(
        code="energy",
        name="Электроэнергия",
        measurement_unit="кВт⋅ч",
        shift_limit=12_000.0,
        daily_limit=24_000.0,
    ),
    "cooling_water": ResourceLimit(
        code="cooling_water",
        name="Охлаждающая вода",
        measurement_unit="м³",
        shift_limit=450.0,
        daily_limit=900.0,
    ),
    "catalyst": ResourceLimit(
        code="catalyst",
        name="Катализатор",
        measurement_unit="кг",
        shift_limit=20.0,
        daily_limit=40.0,
    ),
}


def parse_resource_timestamp(timestamp: str) -> datetime | None:
    try:
        return datetime.strptime(timestamp, DATETIME_FORMAT)
    except ValueError:
        return None


def classify_resource_status(total: float, limit: float) -> str:
    if total > limit * 1.15:
        return "критический перерасход"

    if total > limit:
        return "перерасход"

    return "норма"


def build_resource_summary(
    samples: tuple[ResourceUsageSample, ...],
    current_time: datetime | None = None,
    shift_hours: int = 12,
) -> tuple[ResourceSummary, ...]:
    now = current_time or datetime.now()
    shift_start = now - timedelta(hours=shift_hours)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    totals = {
        code: {"shift": 0.0, "day": 0.0}
        for code in RESOURCE_LIMITS
    }
    samples_by_resource: dict[str, list[ResourceUsageSample]] = {
        code: [] for code in RESOURCE_LIMITS
    }

    for sample in samples:
        if sample.resource_code in samples_by_resource:
            samples_by_resource[sample.resource_code].append(sample)

    for resource_code, resource_samples in samples_by_resource.items():
        ordered_samples = sorted(resource_samples, key=lambda item: item.timestamp)

        for index, sample in enumerate(ordered_samples):
            next_timestamp = (
                ordered_samples[index + 1].timestamp
                if index + 1 < len(ordered_samples)
                else sample.timestamp + timedelta(minutes=1)
            )
            interval_hours = _bounded_interval_hours(sample.timestamp, next_timestamp)
            contribution = sample.value * interval_hours

            if sample.timestamp >= shift_start:
                totals[resource_code]["shift"] += contribution

            if sample.timestamp >= day_start:
                totals[resource_code]["day"] += contribution

    return tuple(
        ResourceSummary(
            resource_code=limit.code,
            resource_name=limit.name,
            measurement_unit=limit.measurement_unit,
            shift_total=totals[limit.code]["shift"],
            shift_limit=limit.shift_limit,
            shift_status=classify_resource_status(
                totals[limit.code]["shift"],
                limit.shift_limit,
            ),
            daily_total=totals[limit.code]["day"],
            daily_limit=limit.daily_limit,
            daily_status=classify_resource_status(
                totals[limit.code]["day"],
                limit.daily_limit,
            ),
        )
        for limit in RESOURCE_LIMITS.values()
    )


def _bounded_interval_hours(start: datetime, end: datetime) -> float:
    interval_seconds = max(0.0, (end - start).total_seconds())
    capped_seconds = min(interval_seconds, 3600.0)
    return capped_seconds / 3600.0
