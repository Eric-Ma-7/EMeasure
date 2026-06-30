"""
Instrument exception hierarchy.

This module defines project-wide exceptions for instrument control.

Design principles
-----------------
1. Keep exception classes lightweight.
   Exceptions should describe failure categories, not implement logic.

2. Separate low-level communication errors from high-level device semantics.
   - BaseInstrument should mostly raise connection and I/O errors.
   - Device subclasses should raise protocol, state, parameter, compliance,
     and safety errors.

3. Preserve the original exception with ``raise ... from e``.
   This is especially useful when wrapping PyVISA errors.

Suggested usage
---------------
from ._exceptions import InstrumentOpenError, InstrumentQueryError

try:
    ...
except VisaIOError as e:
    raise InstrumentQueryError("query failed") from e
"""

from __future__ import annotations


__all__ = [
    # Base
    "InstrumentError",

    # Connection layer
    "InstrumentConnectionError",
    "InstrumentOpenError",
    "InstrumentCloseError",
    "InstrumentNotConnected",
    "InstrumentResourceManagerError",

    # Low-level I/O layer
    "InstrumentIOError",
    "InstrumentWriteError",
    "InstrumentReadError",
    "InstrumentQueryError",
    "InstrumentTimeoutError",

    # Protocol / response layer
    "InstrumentProtocolError",
    "InstrumentResponseError",
    "InstrumentParseError",
    "InstrumentIDNError",
    "InstrumentCommandError",
    "InstrumentUnsupportedCommandError",

    # Parameter / compliance layer
    "InstrumentParameterError",
    "InstrumentComplianceError",

    # Device state / operation layer
    "InstrumentStateError",
    "InstrumentBusyError",
    "InstrumentOperationTimeout",
    "InstrumentModeError",

    # Safety layer
    "InstrumentSafetyError",
    "InstrumentInterlockError",
]


# ============================================================
# Base exception
# ============================================================

class InstrumentError(Exception):
    """
    Base class for all instrument-related errors.

    Catch this exception when the caller wants to handle any error raised by
    the instrument-control layer.

    Example
    -------
    try:
        inst.query("*IDN?")
    except InstrumentError as e:
        logger.error("Instrument operation failed: %s", e)
    """


# ============================================================
# Connection layer
# ============================================================

class InstrumentConnectionError(InstrumentError):
    """
    Base class for connection-related errors.

    This includes opening, closing, or managing a VISA resource.
    """


class InstrumentOpenError(InstrumentConnectionError):
    """
    Raised when opening an instrument resource fails.

    Typical causes:
    - Invalid VISA address.
    - Device is powered off.
    - Network or USB connection is unavailable.
    - VISA backend is not installed or not configured.
    """


class InstrumentCloseError(InstrumentConnectionError):
    """
    Raised when closing an instrument resource fails.

    In many applications, this error can be logged instead of propagated,
    because cleanup should usually continue even if one close operation fails.
    """


class InstrumentNotConnected(InstrumentConnectionError):
    """
    Raised when I/O is attempted without an active instrument session.

    This usually means ``connect()`` was not called, or the session was already
    closed by ``disconnect()``.
    """


class InstrumentResourceManagerError(InstrumentConnectionError):
    """
    Raised when creating or using the VISA ResourceManager fails.

    Typical causes:
    - NI-VISA / pyvisa-py backend is unavailable.
    - Backend selection is invalid.
    - ResourceManager has already been closed.
    """


# ============================================================
# Low-level I/O layer
# ============================================================

class InstrumentIOError(InstrumentError):
    """
    Base class for low-level instrument I/O errors.

    These errors usually wrap PyVISA read/write/query failures.
    """


class InstrumentWriteError(InstrumentIOError):
    """
    Raised when writing a command to the instrument fails.

    This is a transport-level failure, not necessarily a device-level command
    error. For SCPI error queue failures, use InstrumentCommandError instead.
    """


class InstrumentReadError(InstrumentIOError):
    """
    Raised when reading a response from the instrument fails.
    """


class InstrumentQueryError(InstrumentIOError):
    """
    Raised when a query operation fails.

    A query usually means write followed by read. This error is useful when the
    caller does not need to distinguish whether the write part or the read part
    failed.
    """


class InstrumentTimeoutError(InstrumentIOError):
    """
    Raised when the instrument does not respond before the configured timeout.

    This can be raised directly by your code after inspecting a PyVISA timeout
    error, or by a higher-level wait loop.
    """


# ============================================================
# Protocol / response layer
# ============================================================

class InstrumentProtocolError(InstrumentError):
    """
    Base class for protocol-level errors.

    These errors indicate that communication succeeded, but the response or
    device behavior did not match the expected protocol.
    """


class InstrumentResponseError(InstrumentProtocolError):
    """
    Raised when the instrument response is empty, incomplete, or unexpected.

    Examples:
    - Expected "1", got "".
    - Expected three comma-separated fields, got one field.
    - Expected a response ending with a known terminator, but got a truncated response.
    """


class InstrumentParseError(InstrumentProtocolError):
    """
    Raised when an instrument response cannot be parsed.

    Examples:
    - Expected a float, got "OVLD".
    - Expected an integer status code, got "ERROR".
    - Expected a comma-separated numeric list, got malformed text.
    """


class InstrumentIDNError(InstrumentProtocolError):
    """
    Raised when the instrument identity does not match the expected model.

    Example:
    - The driver expects a Keithley 2612B.
    - ``*IDN?`` returns a different instrument model.
    """


class InstrumentCommandError(InstrumentProtocolError):
    """
    Raised when the instrument reports a command or execution error.

    This is usually based on the device error queue, status byte, or error
    register, rather than a PyVISA transport failure.
    """


class InstrumentUnsupportedCommandError(InstrumentProtocolError):
    """
    Raised when a command is not supported by the current instrument or firmware.

    This is useful when different models share a common driver but not all
    features are available on every model.
    """


# ============================================================
# Parameter / compliance layer
# ============================================================

class InstrumentParameterError(InstrumentError, ValueError):
    """
    Raised when a user-supplied parameter is invalid.

    This error should usually be raised before sending a command to the
    instrument, when the driver can determine that the input is not valid.

    Examples:
    - Invalid channel number.
    - Invalid enum value.
    - Negative averaging count.
    - Voltage/current/field value outside the driver-defined allowed range.
    - Invalid source mode.
    - Invalid trigger configuration.
    """


class InstrumentComplianceError(InstrumentError):
    """
    Raised when an instrument enters compliance or protection state.

    This error is usually detected after an operation has started, or after
    querying the instrument status.

    Examples:
    - An SMU enters voltage compliance while sourcing current.
    - An SMU enters current compliance while sourcing voltage.
    - A power supply enters current limit or protection mode.
    - An output is automatically disabled by the instrument protection logic.
    """


# ============================================================
# Device state / operation layer
# ============================================================

class InstrumentStateError(InstrumentError):
    """
    Raised when the current device state does not allow the requested operation.

    Examples:
    - Trying to start a sweep while another sweep is running.
    - Trying to change source mode while output is enabled.
    - Trying to read data before the measurement is configured.
    """


class InstrumentBusyError(InstrumentStateError):
    """
    Raised when the instrument is busy and cannot accept the requested operation.

    Examples:
    - Device is performing auto-zero.
    - Device is ramping field or temperature.
    - Device is still processing a previous command.
    """


class InstrumentOperationTimeout(InstrumentStateError):
    """
    Raised when waiting for a high-level device operation times out.

    This is different from InstrumentTimeoutError:
    - InstrumentTimeoutError: low-level read/query timeout.
    - InstrumentOperationTimeout: high-level operation did not finish in time.

    Examples:
    - Waiting for magnet ramp completion timed out.
    - Waiting for temperature stabilization timed out.
    - Waiting for sweep completion timed out.
    """


class InstrumentModeError(InstrumentStateError):
    """
    Raised when the requested operation is incompatible with the current mode.

    Examples:
    - Setting current while the channel is in voltage-source mode.
    - Reading demodulated data while the lock-in is not configured.
    - Starting a field ramp while the magnet power supply is in an incompatible mode.
    """


# ============================================================
# Safety layer
# ============================================================

class InstrumentSafetyError(InstrumentError):
    """
    Raised when a potentially dangerous operation is refused by software.

    This should be used for checks that protect equipment, samples, magnets,
    cryostats, or users.

    Examples:
    - Refuse to turn on a magnet heater if PSU field and magnet field differ.
    - Refuse to enable SMU output if voltage/current limits are unsafe.
    - Refuse to start a ramp if the requested rate is unsafe for the experiment.
    """


class InstrumentInterlockError(InstrumentSafetyError):
    """
    Raised when a hardware or software interlock prevents an operation.

    Examples:
    - Cryostat interlock is open.
    - Temperature is outside the safe range.
    - Required cooling water, vacuum, or heater condition is not satisfied.
    """