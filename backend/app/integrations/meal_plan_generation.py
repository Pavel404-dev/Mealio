from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


class MealPlanProviderTimeout(Exception):
    pass


class MealPlanProviderUnavailable(Exception):
    pass


class MealPlanProviderInvalidOutput(Exception):
    pass


@dataclass(frozen=True)
class MealPlanProviderResult:
    selection: object
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: Decimal | None = None


class MealPlanGenerationProvider(Protocol):
    @property
    def model(self) -> str: ...

    async def select_meals(self, *, context_json: str) -> MealPlanProviderResult: ...
