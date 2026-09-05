from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter


@dataclass
class Budgets:
    max_iterations: int = 6
    max_tokens: int = 20_000
    max_cost_usd: float = 0.05
    max_wall_clock_seconds: float = 60.0


class BudgetExceeded(Exception):
    def __init__(self, which: str, detail: str):
        self.which = which
        self.detail = detail
        super().__init__(f"budget exceeded: {which} ({detail})")


@dataclass
class BudgetTracker:
    budgets: Budgets
    iterations: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    _started_at: float = field(default=0.0, repr=False)

    def start(self) -> None:
        self._started_at = perf_counter()

    def record_call(self, tokens: int, cost_usd: float) -> None:
        self.iterations += 1
        self.total_tokens += tokens
        self.total_cost_usd += cost_usd

    @property
    def elapsed_seconds(self) -> float:
        return perf_counter() - self._started_at

    def check(self) -> None:
        b = self.budgets
        if self.iterations > b.max_iterations:
            raise BudgetExceeded("max_iterations", f"{self.iterations} > {b.max_iterations}")
        if self.total_tokens > b.max_tokens:
            raise BudgetExceeded("max_tokens", f"{self.total_tokens} > {b.max_tokens}")
        if self.total_cost_usd > b.max_cost_usd:
            raise BudgetExceeded("max_cost_usd", f"{self.total_cost_usd:.4f} > {b.max_cost_usd:.4f}")
        if self.elapsed_seconds > b.max_wall_clock_seconds:
            raise BudgetExceeded(
                "max_wall_clock_seconds", f"{self.elapsed_seconds:.1f}s > {b.max_wall_clock_seconds}s"
            )
