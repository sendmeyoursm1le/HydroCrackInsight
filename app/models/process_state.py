from dataclasses import dataclass


@dataclass
class ProcessState:
    temperature: float = 390.0
    pressure: float = 150.0
    feed_flow: float = 80.0
    hydrogen_flow: float = 3000.0
    energy: float = 900.0
    water_consumption: float = 35.0
    catalyst_consumption: float = 1.5
    product_yield: float = 82.0
    mode: str = "ожидание"
    status: str = "норма"