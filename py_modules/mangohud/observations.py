from dataclasses import dataclass


@dataclass(frozen=True)
class TimedValue:
    value: object
    observed_at: float
    confirmed: bool


def fresh_value(sample, now, max_age_s):
    if sample is None or not sample.confirmed:
        return None
    age = now - sample.observed_at
    if age < 0 or age > max_age_s:
        return None
    return sample.value
