import time

from typing import Callable, Optional, Sequence
from dataclasses import dataclass

@dataclass
class Sweep1D:
    name: str
    values: Sequence[float]
    setter: Callable[[float], None]
    index_name: Optional[str] = None
    settle_time: float = 0.1
    before_run_hook: Optional[Callable[[], None]] = None
    after_run_hook: Optional[Callable[[], None]] = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("name must be a non-empty string.")

        if self.index_name is None:
            self.index_name = f"index_{self.name}"
        elif not isinstance(self.index_name, str) or not self.index_name:
            raise ValueError("index_name must be a non-empty string or None.")

        if not hasattr(self.values, "__len__") or not hasattr(self.values, "__getitem__"):
            raise TypeError("values must be a sequence.")

        if len(self.values) == 0:
            raise ValueError("values must not be empty.")

        if not callable(self.setter):
            raise TypeError("setter must be callable.")

        if self.settle_time <= 0:
            raise ValueError("settle_time must be > 0.")

        if self.before_run_hook is not None and not callable(self.before_run_hook):
            raise TypeError("before_run_hook must be callable or None.")

        if self.after_run_hook is not None and not callable(self.after_run_hook):
            raise TypeError("after_run_hook must be callable or None.")

    def __len__(self) -> int:
        return len(self.values)

    def __iter__(self):
        if self.before_run_hook is not None:
            self.before_run_hook()

        try:
            for index, value in enumerate(self.values):
                yield self.apply_value(value, index=index, wait=True)
        finally:
            if self.after_run_hook is not None:
                self.after_run_hook()

    def get_value(self, index: int) -> float:
        try:
            return self.values[index]
        except IndexError as e:
            raise IndexError(
                f"Scan index {index} is out of range for sweep {self.name!r} "
                f"with length {len(self)}."
            ) from e

    def apply_value(
        self,
        value: float,
        *,
        index: int | None = None,
        wait: bool = True,
    ) -> dict[str, float | int]:
        self.setter(value)
        if wait:
            time.sleep(self.settle_time)

        out: dict[str, float | int] = {self.name: value}
        if index is not None:
            assert self.index_name is not None
            out[self.index_name] = index
        return out

    def apply_index(self, index: int, *, wait: bool = True) -> dict[str, float | int]:
        value = self.get_value(index)
        return self.apply_value(value, index=index, wait=wait)


