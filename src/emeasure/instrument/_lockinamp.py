from __future__ import annotations

from ._core import BaseInstrument
from ._utils import validate_enum_attr, ramp_drive, aramp_drive
from ._exceptions import (
    InstrumentCommandError,
    InstrumentModeError,
    InstrumentParameterError,
    InstrumentParseError,
    InstrumentResponseError,
)

from collections import OrderedDict
from typing import Any, Iterator, Sequence
import time
import asyncio
import numpy as np

__all__ = ["NF5650", "NF5650Array"]


class NF5650(BaseInstrument):
    """NF LI5650 lock-in amplifier driver.

    Notes
    -----
    This class is intended for LI5650 only. It does not try to detect or
    support LI5645. The driver assumes ASCII data transfer for ``:FETCh?`` and
    measurement-buffer related reads.
    """

    _DET_MODE = {"SING", "DUAL1", "DUAL2", "CASC", "SINGLE", "CASCADE"}
    _REF_SRC = {"RINP", "IOSC", "SINP"}
    _REF_TYPE = {"SIN", "TPOS", "TNEG"}
    _SIG_COUP = {"DC", "AC"}
    _SIG_GND = {"FLO", "GRO", "FLOAT", "GROUND"}
    _SIG_IV_GAIN = {"IE6", "IE8"}
    _SIG_CONN = {"I", "A", "AB"}
    _PSD = {"PRI", "SEC"}
    _SENSE_DR = {"HIGH", "MED", "LOW"}
    _SENSE_FILTER_SLOPE = {"6", "12", "18", "24"}
    _SENSE_FILTER_TYPE = {"MOV", "EXP"}
    _SRC_IOSC = {"PRI", "SEC", "PRIMARY", "SECONDARY"}
    _DATA_FORMAT = {"ASC", "ASCII"}

    _OPER_AUTO_MEASURE = 4

    _CALC_FORM = {
        1: {
            "SING": {"REAL", "MLIN", "NOIS", "AUX1"},
            "DUAL1": {"REAL", "MLIN", "IMAG", "PHAS", "NOIS", "AUX1", "REAL2", "MLIN2"},
            "DUAL2": {"REAL", "MLIN", "IMAG", "PHAS", "NOIS", "AUX1", "REAL2", "MLIN2"},
            "CASC": {"REAL", "MLIN", "IMAG", "PHAS", "NOIS", "AUX1", "REAL2", "MLIN2"},
        },
        2: {
            "SING": {"IMAG", "PHAS", "AUX1", "AUX2"},
            "DUAL1": {"IMAG", "PHAS", "AUX1", "AUX2", "REAL2", "MLIN2", "IMAG2", "PHAS2"},
            "DUAL2": {"IMAG", "PHAS", "AUX1", "AUX2", "REAL2", "MLIN2", "IMAG2", "PHAS2"},
            "CASC": {"IMAG", "PHAS", "AUX1", "AUX2", "REAL2", "MLIN2", "IMAG2", "PHAS2"},
        },
        3: {
            "SING": {"REAL", "MLIN"},
            "DUAL1": {"REAL", "MLIN", "IMAG", "PHAS", "REAL2", "MLIN2"},
            "DUAL2": {"REAL", "MLIN", "IMAG", "PHAS", "REAL2", "MLIN2"},
            "CASC": {"REAL", "MLIN", "IMAG", "PHAS", "REAL2", "MLIN2"},
        },
        4: {
            "SING": {"IMAG", "PHAS"},
            "DUAL1": {"IMAG", "PHAS", "REAL2", "MLIN2", "IMAG2", "PHAS2"},
            "DUAL2": {"IMAG", "PHAS", "REAL2", "MLIN2", "IMAG2", "PHAS2"},
            "CASC": {"IMAG", "PHAS", "REAL2", "MLIN2", "IMAG2", "PHAS2"},
        },
    }

    _SENSE_DATA = {
        "STAT": 1,
        "STATUS": 1,
        "DATA1": 2,
        "DATA2": 4,
        "DATA3": 8,
        "DATA4": 16,
        "FREQ": 32,
    }
    _SENSE_DATA_CANONICAL = {
        "STAT": "STATUS",
        "STATUS": "STATUS",
        "DATA1": "DATA1",
        "DATA2": "DATA2",
        "DATA3": "DATA3",
        "DATA4": "DATA4",
        "FREQ": "FREQ",
    }
    _SENSE_DATA_ORDER = ("STATUS", "DATA1", "DATA2", "DATA3", "DATA4", "FREQ")

    def __init__(self, visa_address: str, rm=None) -> None:
        super().__init__(visa_address, rm)

    def connect(self) -> None:
        """Connect to the instrument and force ASCII data transfer.

        The NF5650 driver only supports ASCII parsing for ``:FETCh?``. Binary
        ``REAL`` and ``INT`` transfer formats are intentionally not supported by
        this class.
        """
        super().connect()
        res = self._require_session()
        res.read_termination = "\n"
        res.write_termination = "\n"
        self.set_data_format("ASC")

    # ---------------- Common / status helpers ----------------
    def clear_status(self) -> None:
        """Clear status registers, event registers, error queue, and panel error display."""
        self.write("*CLS")

    def get_error(self) -> tuple[int, str]:
        """Read one item from the instrument error queue."""
        resp = self.query(":SYST:ERR?").strip()
        try:
            code_str, msg = resp.split(",", 1)
            code = int(code_str.strip())
            msg = msg.strip().strip('"').strip("'")
        except Exception as e:
            raise InstrumentParseError(
                f"Failed to parse :SYST:ERR? response: {resp!r}"
            ) from e
        return code, msg

    def check_error(self, *, max_errors: int = 16) -> None:
        """Drain the error queue and raise if any instrument command error exists."""
        errors: list[tuple[int, str]] = []
        for _ in range(max_errors):
            code, msg = self.get_error()
            if code == 0:
                break
            errors.append((code, msg))

        if errors:
            text = "; ".join(f"{code}: {msg}" for code, msg in errors)
            raise InstrumentCommandError(f"NF5650 error queue is not empty: {text}")

    def get_operation_condition(self) -> int:
        return self._query_int(":STAT:OPER:COND?")

    # ---------------- Data format ----------------
    def set_data_format(self, fmt: str = "ASC") -> None:
        """Set data transfer format.

        Only ASCII format is supported by this driver.
        """
        token = validate_enum_attr(fmt, self._DATA_FORMAT, "DATA_FORMAT")
        if token == "ASCII":
            token = "ASC"
        self.write(":FORM ASC")

    def get_data_format(self) -> str:
        return self.query(":FORM?").strip().upper()

    # ---------------- :DET ----------------
    def set_detect_mode(self, mode: str) -> None:
        token = validate_enum_attr(mode, self._DET_MODE, "DET_MODE")
        self.write(f":DET {token}")

    def get_detect_mode(self) -> str:
        return self._normalize_detect_mode(self.query(":DET?").strip().upper())

    # ---------------- :FREQ1:HARM ----------------
    def set_priPSD_harmonics_on(self, is_on: bool = True) -> None:
        self.write(f":FREQ:HARM {'ON' if is_on else 'OFF'}")

    def get_priPSD_harmonics_on(self) -> bool:
        return self._parse_bool_response(self.query(":FREQ:HARM?"), ":FREQ:HARM?")

    def set_priPSD_harmonics(self, numerator: int, denominator: int = 1) -> None:
        numerator = self._as_int(numerator, "primary harmonic numerator")
        denominator = self._as_int(denominator, "primary harmonic denominator")
        self._validate_int_range(numerator, 1, 63, "primary harmonic numerator")
        self._validate_int_range(denominator, 1, 63, "primary harmonic denominator")
        self.write(f":FREQ:MULT {numerator}")
        self.write(f":FREQ:SMUL {denominator}")

    def get_priPSD_harmonics(self) -> tuple[int, int]:
        numerator = self._query_int(":FREQ:MULT?")
        denominator = self._query_int(":FREQ:SMUL?")
        return numerator, denominator

    # ---------------- :FREQ2:HARM ----------------
    def set_secPSD_harmonics_on(self, is_on: bool = True) -> None:
        if is_on and self.get_detect_mode() != "DUAL1":
            raise InstrumentModeError(
                "Secondary PSD harmonics can be enabled only in DUAL1 mode."
            )
        self.write(f":FREQ2:HARM {'ON' if is_on else 'OFF'}")

    def get_secPSD_harmonics_on(self) -> bool:
        return self._parse_bool_response(self.query(":FREQ2:HARM?"), ":FREQ2:HARM?")

    def set_secPSD_harmonics(self, numerator: int) -> None:
        if self.get_detect_mode() != "DUAL1":
            raise InstrumentModeError(
                "Secondary PSD harmonic order is valid only in DUAL1 mode."
            )
        numerator = self._as_int(numerator, "secondary harmonic numerator")
        self._validate_int_range(numerator, 1, 63, "secondary harmonic numerator")
        self.write(f":FREQ2:MULT {numerator}")

    def get_secPSD_harmonics(self) -> int:
        return self._query_int(":FREQ2:MULT?")

    # ---------------- Reference Signal ----------------
    def set_ref_src(self, ref_src: str) -> None:
        token = validate_enum_attr(ref_src, self._REF_SRC, "REF_SRC")
        self.write(f":ROUT2 {token}")

    def get_ref_src(self) -> str:
        return self.query(":ROUT2?").strip().upper()

    def set_ref_type(self, ref_type: str) -> None:
        token = validate_enum_attr(ref_type, self._REF_TYPE, "REF_TYPE")
        self.write(f":INP2:TYPE {token}")

    def get_ref_type(self) -> str:
        return self.query(":INP2:TYPE?").strip().upper()

    # ---------------- Input Signal ----------------
    def set_sig_coupling(self, coupling: str) -> None:
        token = validate_enum_attr(coupling, self._SIG_COUP, "SIG_COUP")
        self.write(f":INP:COUP {token}")

    def get_sig_coupling(self) -> str:
        return self.query(":INP:COUP?").strip().upper()

    def set_sig_notch(self, harm1: bool, harm2: bool) -> None:
        self.write(f":INP:FILT:NOTC1 {int(harm1)};:INP:FILT:NOTC2 {int(harm2)}")

    def get_sig_notch(self) -> tuple[bool, bool]:
        harm1 = self._parse_bool_response(self.query(":INP:FILT:NOTC1?"), ":INP:FILT:NOTC1?")
        harm2 = self._parse_bool_response(self.query(":INP:FILT:NOTC2?"), ":INP:FILT:NOTC2?")
        return harm1, harm2

    def set_sig_gnd(self, gnd: str) -> None:
        token = validate_enum_attr(gnd, self._SIG_GND, "SIG_GND")
        self.write(f":INP:LOW {token}")

    def get_sig_gnd(self) -> str:
        return self.query(":INP:LOW?").strip().upper()

    def set_sig_IV_gain(self, gain: str) -> None:
        token = validate_enum_attr(gain, self._SIG_IV_GAIN, "SIG_IV_GAIN")
        self.write(f":INP:GAIN {token}")

    def get_sig_IV_gain(self) -> str:
        return self.query(":INP:GAIN?").strip().upper()

    def set_sig_connector(self, conn: str) -> None:
        token = validate_enum_attr(conn, self._SIG_CONN, "SIG_CONN")
        self.write(f":ROUT {token}")

    def get_sig_connector(self) -> str:
        return self.query(":ROUT?").strip().upper()

    # ---------------- Sense of Input Signal ----------------
    def set_DR(self, sense_DR: str) -> None:
        token = validate_enum_attr(sense_DR, self._SENSE_DR, "SENSE_DR")
        self.write(f":DRES {token}")

    def get_DR(self) -> str:
        return self.query(":DRES?").strip().upper()

    def set_priPSD_filter_slope(self, slope: int | str) -> None:
        token = self._validate_filter_slope(slope, "primary PSD filter slope")
        self.write(f":FILT:SLOP {token}")

    def get_priPSD_filter_slope(self) -> str:
        return self.query(":FILT:SLOP?").strip()

    def set_secPSD_filter_slope(self, slope: int | str) -> None:
        token = self._validate_filter_slope(slope, "secondary PSD filter slope")
        self.write(f":FILT2:SLOP {token}")

    def get_secPSD_filter_slope(self) -> str:
        return self.query(":FILT2:SLOP?").strip()

    def set_priPSD_filter_type(self, filter_type: str) -> None:
        token = validate_enum_attr(filter_type, self._SENSE_FILTER_TYPE, "SENSE_FILTER_TYPE")
        self.write(f":FILT:TYPE {token}")

    def get_priPSD_filter_type(self) -> str:
        return self.query(":FILT:TYPE?").strip().upper()

    def set_secPSD_filter_type(self, filter_type: str) -> None:
        token = validate_enum_attr(filter_type, self._SENSE_FILTER_TYPE, "SENSE_FILTER_TYPE")
        self.write(f":FILT2:TYPE {token}")

    def get_secPSD_filter_type(self) -> str:
        return self.query(":FILT2:TYPE?").strip().upper()

    def set_priPSD_filter_Tc(self, Tc: float) -> None:
        Tc = self._validate_float_range(Tc, 5e-6, 50e3, "primary PSD time constant")
        self.write(f":FILT:TCON {Tc}")

    def get_priPSD_filter_Tc(self) -> float:
        return self._query_float(":FILT:TCON?")

    def set_secPSD_filter_Tc(self, Tc: float) -> None:
        Tc = self._validate_float_range(Tc, 5e-6, 50e3, "secondary PSD time constant")
        self.write(f":FILT2:TCON {Tc}")

    def get_secPSD_filter_Tc(self) -> float:
        return self._query_float(":FILT2:TCON?")

    def set_priPSD_phase(self, phase: float) -> None:
        phase = self._validate_float_range(phase, -720.0, 720.0, "primary PSD phase")
        self.write(f":PHAS {phase}")

    def get_priPSD_phase(self) -> float:
        return self._query_float(":PHAS?")

    def set_secPSD_phase(self, phase: float) -> None:
        phase = self._validate_float_range(phase, -720.0, 720.0, "secondary PSD phase")
        self.write(f":PHAS2 {phase}")

    def get_secPSD_phase(self) -> float:
        return self._query_float(":PHAS2?")

    def set_priPSD_curr_range(self, curr_range: float) -> None:
        curr_range = self._validate_current_range(curr_range)
        self.write(f":CURR:AC:RANGE {curr_range:g}")

    def get_priPSD_curr_range(self) -> float:
        return self._query_float(":CURR:AC:RANGE?")

    def set_secPSD_curr_range(self, curr_range: float) -> None:
        curr_range = self._validate_current_range(curr_range)
        if self.get_detect_mode() in {"DUAL1", "DUAL2"}:
            pri_range = self.get_priPSD_curr_range()
            if curr_range > pri_range:
                raise InstrumentParameterError(
                    "Current range of secondary PSD must be no larger than primary PSD in DUAL mode."
                )
        self.write(f":CURR2:AC:RANGE {curr_range:g}")

    def get_secPSD_curr_range(self) -> float:
        return self._query_float(":CURR2:AC:RANGE?")

    def set_priPSD_volt_range(self, volt_range: float) -> None:
        volt_range = self._validate_float_range(volt_range, 10e-9, 1.0, "primary PSD voltage range")
        self.write(f":VOLT:AC:RANGE {volt_range}")

    def get_priPSD_volt_range(self) -> float:
        return self._query_float(":VOLT:AC:RANGE?")

    def set_secPSD_volt_range(self, volt_range: float) -> None:
        volt_range = self._validate_float_range(volt_range, 10e-9, 1.0, "secondary PSD voltage range")
        if self.get_detect_mode() in {"DUAL1", "DUAL2"}:
            pri_range = self.get_priPSD_volt_range()
            if volt_range > pri_range:
                raise InstrumentParameterError(
                    "Voltage range of secondary PSD must be no larger than primary PSD in DUAL mode."
                )
        self.write(f":VOLT2:AC:RANGE {volt_range}")

    def get_secPSD_volt_range(self) -> float:
        return self._query_float(":VOLT2:AC:RANGE?")

    # ---------------- CALCn:FORM ----------------
    def set_calc_form(self, form: str, ch: int) -> None:
        self._validate_int_range(self._as_int(ch, "CALC channel"), 1, 4, "CALC channel")
        mode = self.get_detect_mode()
        token = validate_enum_attr(form, self._CALC_FORM[ch][mode], f"CALC{ch}_FORM_{mode}")
        self.write(f":CALC{ch}:FORM {token}")

    def get_calc_form(self, ch: int) -> str:
        self._validate_int_range(self._as_int(ch, "CALC channel"), 1, 4, "CALC channel")
        return self.query(f":CALC{ch}:FORM?").strip().upper()

    # ---------------- Snapshot / Recover ----------------
    def snapshot(self) -> dict[str, Any]:
        """Return a recoverable configuration snapshot.

        The returned dictionary is intentionally flat so that it is easy to
        serialize into JSON or TOML-compatible structures.
        """
        sig_connector = self.get_sig_connector()

        config: dict[str, Any] = {
            "SNAPSHOT_VERSION": 2,
            "DATA_FORMAT": self.get_data_format(),
            "SENSE_DATA": self.get_sense_data(),

            "DETECT_MODE": self.get_detect_mode(),
            "REF_SRC": self.get_ref_src(),
            "REF_TYPE": self.get_ref_type(),

            "SIG_COUPLING": self.get_sig_coupling(),
            "SIG_NOTCH": self.get_sig_notch(),
            "SIG_GND": self.get_sig_gnd(),
            "SIG_CONNECTOR": sig_connector,
            "SIG_IV_GAIN": self.get_sig_IV_gain(),

            "DR": self.get_DR(),
            "SENSE_PRI_FILTER_SLOPE": self.get_priPSD_filter_slope(),
            "SENSE_SEC_FILTER_SLOPE": self.get_secPSD_filter_slope(),
            "SENSE_PRI_FILTER_TYPE": self.get_priPSD_filter_type(),
            "SENSE_SEC_FILTER_TYPE": self.get_secPSD_filter_type(),
            "SENSE_PRI_FILTER_TC": self.get_priPSD_filter_Tc(),
            "SENSE_SEC_FILTER_TC": self.get_secPSD_filter_Tc(),
            "SENSE_PRI_PHASE": self.get_priPSD_phase(),
            "SENSE_SEC_PHASE": self.get_secPSD_phase(),

            "PRI_HARM_ON": self.get_priPSD_harmonics_on(),
            "PRI_HARM": self.get_priPSD_harmonics(),
            "SEC_HARM_ON": self.get_secPSD_harmonics_on(),
            "SEC_HARM": self.get_secPSD_harmonics(),

            "CALC1_FORM": self.get_calc_form(1),
            "CALC2_FORM": self.get_calc_form(2),
            "CALC3_FORM": self.get_calc_form(3),
            "CALC4_FORM": self.get_calc_form(4),

            "SOURCE_PRI_OSC_FREQ": self.get_priPSD_osc_freq(),
            "SOURCE_SEC_OSC_FREQ": self.get_secPSD_osc_freq(),
            "OSC_OUTPUT_PSD": self.get_osc_output_PSD(),
            "OSC_VOLT": self.get_osc_volt(),
            "OSC_RANGE": self.get_osc_range(),
            "AUXOUT1_VOLT": self.get_auxout1_volt(),
            "AUXOUT2_VOLT": self.get_auxout2_volt(),
        }

        if sig_connector == "I":
            config["SENSE_PRI_CURR_RANGE"] = self.get_priPSD_curr_range()
            config["SENSE_SEC_CURR_RANGE"] = self.get_secPSD_curr_range()
            config["SENSE_PRI_VOLT_RANGE"] = None
            config["SENSE_SEC_VOLT_RANGE"] = None
        else:
            config["SENSE_PRI_CURR_RANGE"] = None
            config["SENSE_SEC_CURR_RANGE"] = None
            config["SENSE_PRI_VOLT_RANGE"] = self.get_priPSD_volt_range()
            config["SENSE_SEC_VOLT_RANGE"] = self.get_secPSD_volt_range()

        return config

    def recover(self, config: dict[str, Any], *, check_errors: bool = False) -> None:
        """Recover instrument settings from a snapshot dictionary."""
        self.set_data_format(config.get("DATA_FORMAT", "ASC"))

        if "DETECT_MODE" in config:
            self.set_detect_mode(config["DETECT_MODE"])

        if "REF_SRC" in config:
            self.set_ref_src(config["REF_SRC"])
        if "REF_TYPE" in config:
            self.set_ref_type(config["REF_TYPE"])

        if "SIG_COUPLING" in config:
            self.set_sig_coupling(config["SIG_COUPLING"])
        if "SIG_NOTCH" in config:
            self.set_sig_notch(*tuple(config["SIG_NOTCH"]))
        if "SIG_GND" in config:
            self.set_sig_gnd(config["SIG_GND"])
        if "SIG_IV_GAIN" in config:
            self.set_sig_IV_gain(config["SIG_IV_GAIN"])
        if "SIG_CONNECTOR" in config:
            self.set_sig_connector(config["SIG_CONNECTOR"])

        if "DR" in config:
            self.set_DR(config["DR"])
        if "SENSE_PRI_FILTER_SLOPE" in config:
            self.set_priPSD_filter_slope(config["SENSE_PRI_FILTER_SLOPE"])
        if "SENSE_SEC_FILTER_SLOPE" in config:
            self.set_secPSD_filter_slope(config["SENSE_SEC_FILTER_SLOPE"])
        if "SENSE_PRI_FILTER_TYPE" in config:
            self.set_priPSD_filter_type(config["SENSE_PRI_FILTER_TYPE"])
        if "SENSE_SEC_FILTER_TYPE" in config:
            self.set_secPSD_filter_type(config["SENSE_SEC_FILTER_TYPE"])
        if "SENSE_PRI_FILTER_TC" in config:
            self.set_priPSD_filter_Tc(config["SENSE_PRI_FILTER_TC"])
        if "SENSE_SEC_FILTER_TC" in config:
            self.set_secPSD_filter_Tc(config["SENSE_SEC_FILTER_TC"])
        if "SENSE_PRI_PHASE" in config:
            self.set_priPSD_phase(config["SENSE_PRI_PHASE"])
        if "SENSE_SEC_PHASE" in config:
            self.set_secPSD_phase(config["SENSE_SEC_PHASE"])

        if "PRI_HARM_ON" in config:
            self.set_priPSD_harmonics_on(config["PRI_HARM_ON"])
        if "PRI_HARM" in config:
            self.set_priPSD_harmonics(*tuple(config["PRI_HARM"]))

        if config.get("SEC_HARM_ON", False):
            self.set_secPSD_harmonics_on(True)
            if "SEC_HARM" in config:
                self.set_secPSD_harmonics(config["SEC_HARM"])
        elif "SEC_HARM_ON" in config:
            self.set_secPSD_harmonics_on(False)

        sig_connector = config.get("SIG_CONNECTOR", self.get_sig_connector())
        if sig_connector == "I":
            if config.get("SENSE_PRI_CURR_RANGE") is not None:
                self.set_priPSD_curr_range(config["SENSE_PRI_CURR_RANGE"])
            if config.get("SENSE_SEC_CURR_RANGE") is not None:
                self.set_secPSD_curr_range(config["SENSE_SEC_CURR_RANGE"])
        else:
            if config.get("SENSE_PRI_VOLT_RANGE") is not None:
                self.set_priPSD_volt_range(config["SENSE_PRI_VOLT_RANGE"])
            if config.get("SENSE_SEC_VOLT_RANGE") is not None:
                self.set_secPSD_volt_range(config["SENSE_SEC_VOLT_RANGE"])

        if "SOURCE_PRI_OSC_FREQ" in config:
            self.set_priPSD_osc_freq(config["SOURCE_PRI_OSC_FREQ"])
        if "SOURCE_SEC_OSC_FREQ" in config:
            self.set_secPSD_osc_freq(config["SOURCE_SEC_OSC_FREQ"])
        if "OSC_OUTPUT_PSD" in config:
            self.set_osc_output_PSD(config["OSC_OUTPUT_PSD"])
        if "OSC_RANGE" in config:
            self.set_osc_range(config["OSC_RANGE"])
        if "OSC_VOLT" in config:
            self.set_osc_volt(config["OSC_VOLT"])
        if "AUXOUT1_VOLT" in config:
            self.set_auxout1_volt(config["AUXOUT1_VOLT"])
        if "AUXOUT2_VOLT" in config:
            self.set_auxout2_volt(config["AUXOUT2_VOLT"])

        if "CALC1_FORM" in config:
            self.set_calc_form(config["CALC1_FORM"], 1)
        if "CALC2_FORM" in config:
            self.set_calc_form(config["CALC2_FORM"], 2)
        if "CALC3_FORM" in config:
            self.set_calc_form(config["CALC3_FORM"], 3)
        if "CALC4_FORM" in config:
            self.set_calc_form(config["CALC4_FORM"], 4)

        if "SENSE_DATA" in config:
            self.set_sense_data(config["SENSE_DATA"])

        # Always return to ASCII format, because this driver only supports ASCII reads.
        self.set_data_format("ASC")

        if check_errors:
            self.check_error()

    # ---------------- Fetch Data ----------------
    def set_sense_data(self, measurement_data: Sequence[str]) -> None:
        token = 0
        seen: set[str] = set()

        for md in measurement_data:
            if not isinstance(md, str):
                raise InstrumentParameterError(
                    f"Measurement data item must be str, got {type(md).__name__}."
                )
            key = md.strip().upper()
            if key not in self._SENSE_DATA:
                raise InstrumentParameterError(
                    f"Invalid measurement data item {md!r}. "
                    f"Valid inputs are {sorted(self._SENSE_DATA)}."
                )
            canonical = self._SENSE_DATA_CANONICAL[key]
            if canonical in seen:
                raise InstrumentParameterError(
                    f"Duplicated measurement data item {md!r}."
                )
            seen.add(canonical)
            token |= self._SENSE_DATA[key]

        self.write(f":DATA {int(token)}")

    def get_sense_data_token(self) -> int:
        return self._query_int(":DATA?")

    def get_sense_data(self) -> list[str]:
        token = self.get_sense_data_token()
        if token < 0 or token > 63:
            raise InstrumentResponseError(f"Unexpected :DATA? token: {token}")
        return [name for name in self._SENSE_DATA_ORDER if token & self._SENSE_DATA[name]]

    def _fetch_once(self) -> tuple[float, ...]:
        resp = self.query(":FETCH?").strip()
        return self._parse_float_tuple(resp, ":FETCH?")

    def fetch(self) -> tuple[float, ...]:
        """Fetch latest measurement values.

        The returned tuple keeps STATUS as a numeric value if STATUS is included
        in the selected ``:DATA`` mask. No status-bit decoding is performed here
        so that the result can be saved directly.
        """
        return self._fetch_once()

    async def afetch(self) -> tuple[float, ...]:
        resp = await self.aquery(":FETCH?")
        return self._parse_float_tuple(resp.strip(), ":FETCH?")

    # ---------------- Auto Tuning ----------------
    def wait_for_auto_measure(self, polling_cycle: float = 0.5) -> None:
        polling_cycle = self._validate_float_range(
            polling_cycle, 0.0, float("inf"), "polling_cycle"
        )
        while (self.get_operation_condition() & self._OPER_AUTO_MEASURE) != 0:
            time.sleep(polling_cycle)

    async def await_for_auto_measure(self, polling_cycle: float = 0.5) -> None:
        polling_cycle = self._validate_float_range(
            polling_cycle, 0.0, float("inf"), "polling_cycle"
        )
        while (self._parse_int(await self.aquery(":STAT:OPER:COND?"), ":STAT:OPER:COND?") & self._OPER_AUTO_MEASURE) != 0:
            await asyncio.sleep(polling_cycle)

    def auto_once_volt_range(self) -> None:
        self.write(":VOLT:AC:RANG:AUTO:ONCE")

    def auto_once_curr_range(self) -> None:
        self.write(":CURR:AC:RANGE:AUTO:ONCE")

    # ---------------- Source Subsystem ----------------
    def get_priPSD_osc_freq(self) -> float:
        return self._query_float(":SOUR:FREQ?")

    def set_priPSD_osc_freq(self, freq: float) -> None:
        freq = self._validate_float_range(freq, 5e-4, 2.6e5, "primary oscillator frequency")
        self.write(f":SOUR:FREQ {freq}")

    def get_secPSD_osc_freq(self) -> float:
        return self._query_float(":SOUR:FREQ2?")

    def set_secPSD_osc_freq(self, freq: float) -> None:
        freq = self._validate_float_range(freq, 5e-4, 2.6e5, "secondary oscillator frequency")
        self.write(f":SOUR:FREQ2 {freq}")

    def get_osc_output_PSD(self) -> str:
        return self.query(":SOUR:IOSC?").strip().upper()

    def set_osc_output_PSD(self, psd: str) -> None:
        token = validate_enum_attr(psd, self._SRC_IOSC, "SRC_IOSC")
        self.write(f":SOUR:IOSC {token}")

    def get_osc_volt(self) -> float:
        return self._query_float(":SOUR:VOLT?")

    def set_osc_volt(self, Vrms: float) -> None:
        Vrms = self._validate_float_range(Vrms, 0.0, 1.0, "OSC OUT voltage")
        self.write(f":SOUR:VOLT {Vrms}")

    def get_osc_range(self) -> float:
        return self._query_float(":SOUR:VOLT:RANG?")

    def set_osc_range(self, osc_range: float) -> None:
        osc_range = self._validate_float_range(osc_range, 10e-3, 1.0, "OSC OUT range")
        self.write(f":SOUR:VOLT:RANG {osc_range}")

    # ---------------- Source5/6 (AUX OUT) Subsystem ----------------
    def set_auxout1_volt(self, volt: float) -> None:
        volt = self._validate_float_range(volt, -10.5, 10.5, "AUX OUT 1 voltage")
        self.write(f":SOUR5:VOLT:OFFS {volt:.3f}")

    def set_auxout2_volt(self, volt: float) -> None:
        volt = self._validate_float_range(volt, -10.5, 10.5, "AUX OUT 2 voltage")
        self.write(f":SOUR6:VOLT:OFFS {volt:.3f}")

    def get_auxout1_volt(self) -> float:
        return self._query_float(":SOUR5:VOLT:OFFS?")

    def get_auxout2_volt(self) -> float:
        return self._query_float(":SOUR6:VOLT:OFFS?")

    def set_auxout1_volt_ramp(self, volt: float, dV: float, dt: float) -> None:
        self._validate_aux_ramp_step(dV)
        V_start = self.get_auxout1_volt()
        ramp_drive(self.set_auxout1_volt, V_start, volt, dV, dt)

    def set_auxout2_volt_ramp(self, volt: float, dV: float, dt: float) -> None:
        self._validate_aux_ramp_step(dV)
        V_start = self.get_auxout2_volt()
        ramp_drive(self.set_auxout2_volt, V_start, volt, dV, dt)

    async def aset_auxout1_volt_ramp(self, volt: float, dV: float, dt: float) -> None:
        self._validate_aux_ramp_step(dV)
        V_start = self.get_auxout1_volt()
        await aramp_drive(self.set_auxout1_volt, V_start, volt, dV, dt)

    async def aset_auxout2_volt_ramp(self, volt: float, dV: float, dt: float) -> None:
        self._validate_aux_ramp_step(dV)
        V_start = self.get_auxout2_volt()
        await aramp_drive(self.set_auxout2_volt, V_start, volt, dV, dt)

    # ---------------- Internal parsing / validation helpers ----------------
    @staticmethod
    def _normalize_detect_mode(mode: str) -> str:
        mode = mode.strip().upper()
        if mode == "SINGLE":
            return "SING"
        if mode == "CASCADE":
            return "CASC"
        return mode

    @staticmethod
    def _parse_bool_response(resp: str, cmd: str) -> bool:
        token = resp.strip().upper()
        if token in {"1", "ON"}:
            return True
        if token in {"0", "OFF"}:
            return False
        raise InstrumentResponseError(f"Unexpected response for {cmd}: {resp!r}")

    def _query_float(self, cmd: str) -> float:
        return self._parse_float(self.query(cmd), cmd)

    def _query_int(self, cmd: str) -> int:
        return self._parse_int(self.query(cmd), cmd)

    @staticmethod
    def _parse_float(resp: str, cmd: str) -> float:
        try:
            return float(resp.strip())
        except Exception as e:
            raise InstrumentParseError(
                f"Failed to parse {cmd} response as float: {resp!r}"
            ) from e

    @staticmethod
    def _parse_int(resp: str, cmd: str) -> int:
        try:
            return int(float(resp.strip()))
        except Exception as e:
            raise InstrumentParseError(
                f"Failed to parse {cmd} response as int: {resp!r}"
            ) from e

    @staticmethod
    def _parse_float_tuple(resp: str, cmd: str) -> tuple[float, ...]:
        try:
            if not resp.strip():
                return tuple()
            return tuple(float(d) for d in resp.split(","))
        except Exception as e:
            raise InstrumentParseError(
                f"Failed to parse {cmd} response as float tuple: {resp!r}"
            ) from e

    @staticmethod
    def _as_int(value: Any, name: str) -> int:
        try:
            out = int(value)
        except Exception as e:
            raise InstrumentParameterError(f"{name} must be an integer, got {value!r}.") from e
        return out

    @staticmethod
    def _as_float(value: Any, name: str) -> float:
        try:
            out = float(value)
        except Exception as e:
            raise InstrumentParameterError(f"{name} must be a finite number, got {value!r}.") from e
        if not np.isfinite(out):
            raise InstrumentParameterError(f"{name} must be a finite number, got {value!r}.")
        return out

    def _validate_float_range(self, value: Any, lower: float, upper: float, name: str) -> float:
        out = self._as_float(value, name)
        if out < lower or out > upper:
            raise InstrumentParameterError(
                f"{name} must be in [{lower}, {upper}], got {value!r}."
            )
        return out

    @staticmethod
    def _validate_int_range(value: int, lower: int, upper: int, name: str) -> None:
        if value < lower or value > upper:
            raise InstrumentParameterError(
                f"{name} must be an integer in [{lower}, {upper}], got {value!r}."
            )

    def _validate_filter_slope(self, slope: int | str, name: str) -> str:
        try:
            token = str(int(slope))
        except Exception as e:
            raise InstrumentParameterError(f"{name} must be one of {sorted(self._SENSE_FILTER_SLOPE)}.") from e
        return validate_enum_attr(token, self._SENSE_FILTER_SLOPE, name)

    def _validate_current_range(self, curr_range: float) -> float:
        curr_range = self._as_float(curr_range, "current range")
        gain = self.get_sig_IV_gain()
        if gain == "IE6":
            low, high = 100e-15, 1e-6
        elif gain == "IE8":
            low, high = 10e-15, 10e-9
        else:
            raise InstrumentResponseError(f"Unexpected IV gain response: {gain!r}")

        if curr_range < low or curr_range > high:
            raise InstrumentParameterError(
                f"Current range must be in [{low:g}, {high:g}] when IV_GAIN = {gain}, "
                f"got {curr_range:g}."
            )
        return curr_range

    def _validate_aux_ramp_step(self, dV: float) -> None:
        dV = self._as_float(dV, "AUX OUT ramp step")
        if abs(dV) < 0.001:
            raise InstrumentParameterError("AUX OUT ramp step must be at least 0.001 V.")


class NF5650Array:
    """A lightweight container for multiple NF5650 lock-in amplifiers.

    The main purpose of this class is to make getter functions simple::

        def getter():
            return nfarr.fetch()

    ``fetch()`` returns a flat dictionary whose keys are the user-provided
    variable names. Empty strings and ``None`` entries in ``vnames`` are ignored.
    """

    _FETCH_FIELDS = ("status", "data1", "data2", "data3", "data4")

    def __init__(
        self,
        lockin_list: list[tuple[str, str, Sequence[str | None]]],
        *,
        rm=None,
    ) -> None:
        """
        Parameters
        ----------
        lockin_list:
            List of ``(alias, address, variable_names)``.

            ``variable_names`` are mapped positionally to::

                status, data1, data2, data3, data4

            Use ``None`` or ``""`` to skip a field.

        Example
        -------
        nf_arr = NF5650Array([
            ("li1", "nf_addr1", ["V_status", "V_X", "V_Y", "V_R", "V_TH"]),
            ("li2", "nf_addr2", ["I_status", "I_Xpn", "I_Ypn", "I_Xsn", "I_Ysn"]),
        ])
        """
        self._instr: OrderedDict[str, NF5650] = OrderedDict()
        self._vname: OrderedDict[str, list[str]] = OrderedDict()
        self._sense_data: OrderedDict[str, list[str]] = OrderedDict()

        seen_aliases: set[str] = set()
        seen_vnames: dict[str, str] = {}

        for alias, addr, vnames in lockin_list:
            alias = self._validate_alias(alias)
            if alias in seen_aliases:
                raise InstrumentParameterError(f"Duplicated NF5650 alias: {alias!r}.")
            seen_aliases.add(alias)

            if len(vnames) > len(self._FETCH_FIELDS):
                raise InstrumentParameterError(
                    f"NF5650 {alias!r} received {len(vnames)} variable names, "
                    f"but at most {len(self._FETCH_FIELDS)} are supported by NF5650Array "
                    f"({', '.join(self._FETCH_FIELDS)})."
                )

            instr_vn: list[str] = []
            instr_sd: list[str] = []

            for vn, sd in zip(vnames, self._FETCH_FIELDS):
                if vn is None or vn == "":
                    continue
                if not isinstance(vn, str):
                    raise InstrumentParameterError(
                        f"Variable name for NF5650 {alias!r} field {sd!r} must be str, "
                        f"None, or an empty string, got {type(vn).__name__}."
                    )

                if vn in seen_vnames:
                    raise InstrumentParameterError(
                        f"Duplicated NF5650 variable name {vn!r}: "
                        f"already used by alias {seen_vnames[vn]!r}, "
                        f"and reused by alias {alias!r}."
                    )

                seen_vnames[vn] = alias
                instr_vn.append(vn)
                instr_sd.append(sd)

            self._instr[alias] = NF5650(addr, rm=rm)
            self._vname[alias] = instr_vn
            self._sense_data[alias] = instr_sd

    # -------------------- Container --------------------
    def __getitem__(self, alias: str) -> NF5650:
        if alias not in self._instr:
            raise KeyError(f"NF5650 with alias [{alias}] is not in this array.")
        return self._instr[alias]

    def __contains__(self, alias: object) -> bool:
        return alias in self._instr

    def __len__(self) -> int:
        return len(self._instr)

    def items(self) -> Iterator[tuple[str, NF5650]]:
        yield from self._instr.items()

    def keys(self):
        return self._instr.keys()

    def values(self):
        return self._instr.values()

    @property
    def aliases(self) -> tuple[str, ...]:
        return tuple(self._instr.keys())

    @property
    def data_keys(self) -> tuple[str, ...]:
        """Return the flat dictionary keys produced by ``fetch()``.

        This property does not communicate with the instruments, so it can be
        used before a measurement loop to validate the expected getter output.
        """
        return tuple(vn for names in self._vname.values() for vn in names)

    def expected_keys(self) -> tuple[str, ...]:
        """Alias of ``data_keys`` for measurement-framework preflight checks."""
        return self.data_keys

    def sense_data(self, alias: str | None = None) -> dict[str, tuple[str, ...]] | tuple[str, ...]:
        """Return configured NF5650 ``:DATA`` fields.

        Parameters
        ----------
        alias:
            If provided, return only the sense-data fields for that lock-in.
            Otherwise return a dictionary for all lock-ins.
        """
        if alias is not None:
            if alias not in self._sense_data:
                raise KeyError(f"NF5650 with alias [{alias}] is not in this array.")
            return tuple(self._sense_data[alias])
        return {key: tuple(value) for key, value in self._sense_data.items()}

    # -------------------- I/O --------------------
    def connect(self) -> None:
        connected: list[NF5650] = []
        try:
            for alias, instr in self.items():
                instr.connect()
                instr.set_sense_data(self._sense_data[alias])
                connected.append(instr)
        except Exception:
            for instr in reversed(connected):
                try:
                    instr.disconnect()
                except Exception:
                    pass
            raise

    def disconnect(self) -> None:
        errors: list[BaseException] = []
        for _, instr in self.items():
            try:
                instr.disconnect()
            except Exception as e:
                errors.append(e)
        if errors:
            raise errors[0]

    def __enter__(self) -> "NF5650Array":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.disconnect()

    # -------------------- Snapshot / Recover --------------------
    def snapshot(self) -> dict[str, dict[str, Any]]:
        """Return configuration snapshots for all lock-ins, keyed by alias."""
        return {alias: instr.snapshot() for alias, instr in self.items()}

    def recover(
        self,
        config: dict[str, dict[str, Any]],
        *,
        check_errors: bool = False,
        strict: bool = True,
    ) -> None:
        """Recover all lock-ins from an array snapshot.

        Parameters
        ----------
        config:
            Dictionary returned by ``NF5650Array.snapshot()``.
        check_errors:
            Forwarded to each ``NF5650.recover()`` call.
        strict:
            If True, require every configured alias to exist in ``config`` and
            reject unknown aliases in ``config``. If False, recover only aliases
            that exist in both this array and ``config``.
        """
        if strict:
            missing = set(self._instr) - set(config)
            extra = set(config) - set(self._instr)
            if missing or extra:
                raise InstrumentParameterError(
                    "NF5650Array recover config alias mismatch. "
                    f"Missing aliases: {sorted(missing)}; extra aliases: {sorted(extra)}."
                )

        for alias, instr in self.items():
            if alias not in config:
                continue
            instr.recover(config[alias], check_errors=check_errors)
            instr.set_sense_data(self._sense_data[alias])

    # -------------------- fetch --------------------
    def fetch_raw(self) -> dict[str, tuple[float, ...]]:
        """Fetch raw tuples from all lock-ins, keyed by alias."""
        raw_data: dict[str, tuple[float, ...]] = {}
        for alias, instr in self.items():
            raw = instr.fetch()
            self._validate_fetch_length(alias, raw)
            raw_data[alias] = raw
        return raw_data

    def fetch(self) -> dict[str, float]:
        """Fetch all configured lock-ins and return a flat data dictionary."""
        all_data: dict[str, float] = {}
        for alias, raw in self.fetch_raw().items():
            all_data.update(dict(zip(self._vname[alias], raw)))
        return all_data

    # -------------------- Internal helpers --------------------
    @staticmethod
    def _validate_alias(alias: str) -> str:
        if not isinstance(alias, str):
            raise InstrumentParameterError(
                f"NF5650 alias must be a string, got {type(alias).__name__}."
            )
        alias = alias.strip()
        if not alias:
            raise InstrumentParameterError("NF5650 alias must not be empty.")
        return alias

    def _validate_fetch_length(self, alias: str, raw: Sequence[float]) -> None:
        expected = len(self._vname[alias])
        actual = len(raw)
        if actual != expected:
            raise InstrumentResponseError(
                f"NF5650 {alias!r} returned {actual} values from fetch(), "
                f"but {expected} values are expected from configured sense_data "
                f"{self._sense_data[alias]!r} and variable names {self._vname[alias]!r}."
            )
