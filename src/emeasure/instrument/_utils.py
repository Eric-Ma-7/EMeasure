"""
Utility helpers for instrument drivers.

This module intentionally stays separate from ``_core.py``:

- ``_core.py`` contains the minimal VISA-backed BaseInstrument.
- ``_exceptions.py`` contains the exception hierarchy.
- ``_utils.py`` contains reusable helper functions for validation, batch
  connection/disconnection, and simple ramp driving.

The functions here are driver-level helpers. They do not depend on
BaseInstrument directly; instead, they use duck typing so that any object with
``connect()`` / ``disconnect()`` can be used.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable, Iterable
from typing import Any

import numpy as np

from ._exceptions import (
    InstrumentConnectionError,
    InstrumentParameterError,
)

__all__ = [
    "validate_enum_attr",
    "connect_all",
    "disconnect_all",
    "generate_ramp_list",
    "ramp_drive",
    "aramp_drive",
]


def validate_enum_attr(
    var: str,
    valid_set: Iterable[str],
    var_name: str,
) -> str:
    """Validate and normalize a string enum-like input.

    Parameters
    ----------
    var:
        User input string.

    valid_set:
        Allowed string tokens. Tokens are compared after ``strip().upper()``.

    var_name:
        Human-readable parameter name used in the error message.

    Returns
    -------
    str
        Normalized token in uppercase.

    Raises
    ------
    InstrumentParameterError
        If ``var`` is not a string or does not belong to ``valid_set``.
    """
    if not isinstance(var, str):
        raise InstrumentParameterError(
            f"Invalid type for {var_name}: expected str, got {type(var).__name__}."
        )

    valid_tokens = {str(item).strip().upper() for item in valid_set}
    token = var.strip().upper()

    if not token:
        raise InstrumentParameterError(
            f"Invalid empty input for {var_name}. "
            f"Valid inputs are {sorted(valid_tokens)}."
        )

    if token not in valid_tokens:
        raise InstrumentParameterError(
            f"Invalid input {var!r} for {var_name}. "
            f"Valid inputs are {sorted(valid_tokens)}."
        )

    return token


def connect_all(*args: Any, **kwargs: Any) -> None:
    """Connect multiple instruments.

    Instruments may be passed either positionally or as keyword values.

    If connecting one instrument fails, this function will try to disconnect
    the instruments that were successfully connected earlier, then re-raise
    the original exception.
    """
    connected: list[Any] = []

    try:
        for instr in _iter_instruments(args, kwargs):
            instr.connect()
            connected.append(instr)
    except Exception:
        for instr in reversed(connected):
            try:
                instr.disconnect()
            except Exception:
                pass
        raise


def disconnect_all(*args: Any, **kwargs: Any) -> None:
    """Disconnect multiple instruments.

    This function attempts to disconnect all instruments even if one of them
    fails. If any disconnection fails, an InstrumentConnectionError is raised
    after all disconnection attempts have been made.
    """
    errors: list[BaseException] = []

    for instr in _iter_instruments(args, kwargs):
        try:
            instr.disconnect()
        except Exception as e:
            errors.append(e)

    if errors:
        raise InstrumentConnectionError(
            "Failed to disconnect one or more instruments: "
            + "; ".join(str(e) for e in errors)
        ) from errors[0]


def generate_ramp_list(
    start: float,
    target: float,
    step: float,
    *,
    with_start: bool = True,
    with_target: bool = True,
) -> np.ndarray:
    """Generate a monotonic ramp array from ``start`` to ``target``.

    Parameters
    ----------
    start, target:
        Start and target values.

    step:
        Positive or negative step size. Only its absolute value is used.
        The ramp direction is determined by ``start`` and ``target``.

    with_start:
        Include ``start`` in the returned array.

    with_target:
        Append ``target`` to the returned array.

    Returns
    -------
    numpy.ndarray
        One-dimensional array of ramp values.

    Notes
    -----
    This helper is designed for instrument ramping. Therefore, when
    ``with_target=True``, the exact target value is appended to avoid small
    floating-point endpoint errors from ``np.arange``.
    """
    start = _as_finite_float(start, "start")
    target = _as_finite_float(target, "target")
    step = _as_finite_float(step, "step")

    if step == 0:
        raise InstrumentParameterError("step must be non-zero.")

    abs_step = abs(step)

    if start == target:
        if with_start or with_target:
            return np.asarray([target], dtype=float)
        return np.asarray([], dtype=float)

    direction = 1.0 if target > start else -1.0
    signed_step = direction * abs_step

    ramp = np.arange(start, target, signed_step, dtype=float)

    if not with_start and ramp.size > 0:
        ramp = ramp[1:]

    if with_target:
        if ramp.size == 0 or not np.isclose(ramp[-1], target):
            ramp = np.append(ramp, target)

    return ramp


def ramp_drive(
    set_value: Callable[[float], Any],
    value_start: float,
    value_target: float,
    dv: float,
    dt: float,
) -> None:
    """Drive a scalar setpoint from ``value_start`` to ``value_target``.

    The intermediate values are generated by :func:`generate_ramp_list`.
    ``value_target`` is always applied at the end.
    """
    dt = _as_nonnegative_float(dt, "dt")

    ramp = generate_ramp_list(
        value_start,
        value_target,
        dv,
        with_start=False,
        with_target=False,
    )

    for value in ramp:
        set_value(float(value))
        time.sleep(dt)

    set_value(float(value_target))


async def aramp_drive(
    set_value: Callable[[float], Any],
    value_start: float,
    value_target: float,
    dv: float,
    dt: float,
) -> None:
    """Asynchronously drive a scalar setpoint.

    ``set_value`` may be either a normal function or an async function.
    """
    dt = _as_nonnegative_float(dt, "dt")

    ramp = generate_ramp_list(
        value_start,
        value_target,
        dv,
        with_start=False,
        with_target=False,
    )

    for value in ramp:
        ret = set_value(float(value))
        if inspect.isawaitable(ret):
            await ret
        await asyncio.sleep(dt)

    ret = set_value(float(value_target))
    if inspect.isawaitable(ret):
        await ret


def _iter_instruments(args: tuple[Any, ...], kwargs: dict[str, Any]):
    """Yield instruments from positional arguments and keyword values."""
    yield from args
    yield from kwargs.values()


def _as_finite_float(value: float, name: str) -> float:
    """Convert a value to finite float or raise InstrumentParameterError."""
    try:
        out = float(value)
    except (TypeError, ValueError) as e:
        raise InstrumentParameterError(
            f"{name} must be a finite number, got {value!r}."
        ) from e

    if not np.isfinite(out):
        raise InstrumentParameterError(
            f"{name} must be a finite number, got {value!r}."
        )

    return out


def _as_nonnegative_float(value: float, name: str) -> float:
    """Convert a value to a finite non-negative float."""
    out = _as_finite_float(value, name)

    if out < 0:
        raise InstrumentParameterError(f"{name} must be non-negative, got {value!r}.")

    return out


