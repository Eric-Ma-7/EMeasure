from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable, Iterator, Mapping
from threading import RLock
from typing import Any, TypeVar

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table


T = TypeVar("T")


class CliDisplay:
    """
    Rich-based command-line display.

    Layout
    ------
    1. Info panel:
       key-value information updated by a dictionary.

    2. Log panel:
       one log string updated independently from the info dictionary.

    3. Progress area:
       multiple progress bars.

    Example
    -------
    with CliDisplay(title="Demo") as display:
        for x in display.track(xs, "x_sweep", description="X sweep"):
            display.update_info({
                "x": f"{x:.4f}",
                "status": "running",
            })
            display.update_log(f"Current x = {x:.4f}")
    """

    def __init__(
        self,
        *,
        refresh_per_second: float = 10,
        transient: bool = False,
        enabled: bool = True,
        title: str = "Experiment Status",
        log_title: str = "Log",
    ) -> None:
        self.enabled = enabled
        self.title = title
        self.log_title = log_title
        self.refresh_per_second = refresh_per_second
        self.transient = transient

        self.console = Console()

        self.progress = Progress(
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed:.4g}/{task.total:.4g}"),
            TextColumn("{task.percentage:>5.1f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=self.console,
        )

        self._info: OrderedDict[str, Any] = OrderedDict()
        self._log_text: str = "initialized"
        self._tasks: dict[str, TaskID] = {}

        self._live: Live | None = None
        self._lock = RLock()

    # ------------------------------------------------------------------
    # context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> CliDisplay:
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc is not None:
            self.update_info({"status": "[red]error[/red]"})
            self.update_log(f"[red]Stopped because of error: {exc}[/red]")
        else:
            self.update_info({"status": "[green]finished[/green]"})
            self.update_log("[green]Finished.[/green]")

        self.stop()

    # ------------------------------------------------------------------
    # live control
    # ------------------------------------------------------------------

    def start(self) -> None:
        if not self.enabled:
            return

        with self._lock:
            if self._live is not None:
                return

            self._live = Live(
                self._render(),
                console=self.console,
                refresh_per_second=self.refresh_per_second,
                transient=self.transient,
            )
            self._live.start()

    def stop(self) -> None:
        if not self.enabled:
            return

        with self._lock:
            if self._live is None:
                return

            self._live.update(self._render())
            self._live.stop()
            self._live = None

    def refresh(self) -> None:
        if not self.enabled:
            return

        with self._lock:
            if self._live is not None:
                self._live.update(self._render())

    # ------------------------------------------------------------------
    # info panel
    # ------------------------------------------------------------------

    def update_info(
        self,
        data: Mapping[str, Any] | None = None,
        *,
        clear: bool = False,
        **kwargs: Any,
    ) -> None:
        """
        Update key-value information panel.

        Parameters
        ----------
        data:
            A dictionary-like object for key-value information.
        clear:
            If True, clear old information before updating.
        kwargs:
            Additional key-value information.

        Example
        -------
        display.update_info({
            "temperature": "4.2 K",
            "field": "1.0 T",
        })

        or

        display.update_info(
            temperature="4.2 K",
            field="1.0 T",
        )
        """
        if not self.enabled:
            return

        with self._lock:
            if clear:
                self._info.clear()

            if data is not None:
                for key, value in data.items():
                    self._info[str(key)] = value

            for key, value in kwargs.items():
                self._info[str(key)] = value

            self.refresh()

    def clear_info(self) -> None:
        if not self.enabled:
            return

        with self._lock:
            self._info.clear()
            self.refresh()

    def remove_info(self, *keys: str) -> None:
        if not self.enabled:
            return

        with self._lock:
            for key in keys:
                self._info.pop(key, None)
            self.refresh()

    # ------------------------------------------------------------------
    # log panel
    # ------------------------------------------------------------------

    def update_log(self, message: str) -> None:
        """
        Update log panel with a single string.

        This does not append new terminal lines.
        It refreshes the log area in-place.

        Example
        -------
        display.update_log("Waiting for magnetic field to reach target.")
        """
        if not self.enabled:
            return

        with self._lock:
            self._log_text = str(message)
            self.refresh()

    def clear_log(self) -> None:
        if not self.enabled:
            return

        with self._lock:
            self._log_text = ""
            self.refresh()

    def log(self, message: str) -> None:
        """
        Alias of update_log().

        This method updates the log panel instead of printing a new line.
        """
        self.update_log(message)

    # ------------------------------------------------------------------
    # progress bars
    # ------------------------------------------------------------------

    def add_bar(
        self,
        name: str,
        *,
        total: int | float,
        description: str | None = None,
    ) -> None:
        if not self.enabled:
            return

        with self._lock:
            if name in self._tasks:
                raise ValueError(f"Progress bar {name!r} already exists.")

            task_id = self.progress.add_task(
                description or name,
                total=total,
            )
            self._tasks[name] = task_id
            self.refresh()

    def update_bar(
        self,
        name: str,
        *,
        advance: int | float | None = None,
        completed: int | float | None = None,
        total: int | float | None = None,
        description: str | None = None,
        visible: bool | None = None,
    ) -> None:
        if not self.enabled:
            return

        with self._lock:
            task_id = self._get_task_id(name)

            kwargs: dict[str, Any] = {}

            if advance is not None:
                kwargs["advance"] = advance
            if completed is not None:
                kwargs["completed"] = completed
            if total is not None:
                kwargs["total"] = total
            if description is not None:
                kwargs["description"] = description
            if visible is not None:
                kwargs["visible"] = visible

            self.progress.update(task_id, **kwargs)
            self.refresh()

    def advance(self, name: str, step: int | float = 1) -> None:
        self.update_bar(name, advance=step)

    def reset_bar(
        self,
        name: str,
        *,
        total: int | float | None = None,
        description: str | None = None,
    ) -> None:
        if not self.enabled:
            return

        with self._lock:
            task_id = self._get_task_id(name)

            kwargs: dict[str, Any] = {
                "completed": 0,
                "visible": True,
            }

            if total is not None:
                kwargs["total"] = total
            if description is not None:
                kwargs["description"] = description

            self.progress.reset(task_id, **kwargs)
            self.refresh()

    def hide_bar(self, name: str) -> None:
        self.update_bar(name, visible=False)

    def show_bar(self, name: str) -> None:
        self.update_bar(name, visible=True)

    # ------------------------------------------------------------------
    # track interface
    # ------------------------------------------------------------------

    def track(
        self,
        iterable: Iterable[T],
        name: str,
        *,
        total: int | float | None = None,
        description: str | None = None,
        reset: bool = True,
    ) -> Iterator[T]:
        """
        Bind a progress bar to an iterable.

        Example
        -------
        for x in display.track(xs, "x_sweep", description="X sweep"):
            ...

        The progress bar advances by 1 after each iteration.
        """
        if not self.enabled:
            yield from iterable
            return

        if total is None:
            try:
                total = len(iterable)  # type: ignore[arg-type]
            except TypeError as exc:
                raise TypeError(
                    "total must be given when iterable has no len()."
                ) from exc

        if name in self._tasks:
            if reset:
                self.reset_bar(
                    name,
                    total=total,
                    description=description or name,
                )
            else:
                self.update_bar(
                    name,
                    total=total,
                    description=description or name,
                )
        else:
            self.add_bar(
                name,
                total=total,
                description=description or name,
            )

        for item in iterable:
            yield item
            self.advance(name)

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _get_task_id(self, name: str) -> TaskID:
        try:
            return self._tasks[name]
        except KeyError as exc:
            raise KeyError(f"Progress bar {name!r} does not exist.") from exc

    def _render_info_panel(self) -> Panel:
        table = Table.grid(padding=(0, 2))
        table.add_column(justify="right", style="bold")
        table.add_column()

        if not self._info:
            table.add_row("status", "initialized")
        else:
            for key, value in self._info.items():
                table.add_row(str(key), str(value))

        return Panel(
            table,
            title=self.title,
            border_style="cyan",
        )

    def _render_log_panel(self) -> Panel:
        return Panel(
            self._log_text,
            title=self.log_title,
            border_style="yellow",
        )

    def _render(self) -> Group:
        return Group(
            self._render_info_panel(),
            self._render_log_panel(),
            self.progress,
        )