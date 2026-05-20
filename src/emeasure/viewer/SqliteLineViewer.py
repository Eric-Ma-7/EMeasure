"""
SQLite + pyqtgraph experiment data viewer.

Expected database schema:
    experiments(
        ...,
        table_name TEXT,          -- Unique data-table name for each experiment
        experiment_name TEXT,     -- Experiment name, not necessarily unique
        meta TEXT                 -- JSON string containing experiment parameters
    )

Usage:
    python sqlite_pyqtgraph_viewer.py path/to/data.db
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


# ---------- SQLite helpers ----------


def quote_identifier(name: str) -> str:
    """Safely quote a SQLite table name or column name."""
    if not isinstance(name, str) or name == "":
        raise ValueError("SQLite identifier cannot be empty")
    return '"' + name.replace('"', '""') + '"'


def connect_readonly(db_path: str) -> sqlite3.Connection:
    """
    Open a SQLite database in read-only mode.

    This is suitable for reading committed data from a database that may also be
    written by a measurement program using WAL mode.
    """
    path = Path(db_path).expanduser().resolve()
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=2.0)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_experiments(db_path: str) -> list[dict[str, Any]]:
    sql = """
        SELECT rowid AS _rowid_, table_name, experiment_name, meta
        FROM experiments
        ORDER BY _rowid_ DESC
    """
    with closing(connect_readonly(db_path)) as conn:
        rows = conn.execute(sql).fetchall()
    return [dict(row) for row in rows]


def fetch_table_columns(db_path: str, table_name: str) -> list[str]:
    with closing(connect_readonly(db_path)) as conn:
        rows = conn.execute(f"PRAGMA table_info({quote_identifier(table_name)})").fetchall()
    return [row["name"] for row in rows]


def fetch_xy_data(
    db_path: str,
    table_name: str,
    x_key: str,
    y_key: str,
    max_points: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    q_table = quote_identifier(table_name)
    q_x = quote_identifier(x_key)
    q_y = quote_identifier(y_key)

    params: tuple[Any, ...] = ()
    if max_points is not None and max_points > 0:
        # First select the latest max_points rows, then restore ascending row order.
        sql = f"""
            SELECT {q_x} AS x, {q_y} AS y
            FROM (
                SELECT rowid, {q_x}, {q_y}
                FROM {q_table}
                ORDER BY rowid DESC
                LIMIT ?
            )
            ORDER BY rowid ASC
        """
        params = (int(max_points),)
    else:
        sql = f"SELECT {q_x} AS x, {q_y} AS y FROM {q_table} ORDER BY rowid ASC"

    with closing(connect_readonly(db_path)) as conn:
        rows = conn.execute(sql, params).fetchall()

    xs: list[float] = []
    ys: list[float] = []
    for row in rows:
        try:
            x = float(row["x"])
            y = float(row["y"])
        except (TypeError, ValueError):
            continue
        if np.isfinite(x) and np.isfinite(y):
            xs.append(x)
            ys.append(y)

    return np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)


def value_to_display(value: Any, max_len: int = 160) -> str:
    """Convert a scalar meta value to a compact display string."""
    if value is None:
        text = "None"
    elif isinstance(value, bool):
        text = "True" if value else "False"
    elif isinstance(value, (int, float)):
        text = str(value)
    else:
        text = str(value)

    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


# ---------- Curve style helpers ----------


LINE_STYLE_MAP = {
    "Solid": Qt.SolidLine,
    "Dash": Qt.DashLine,
    "Dot": Qt.DotLine,
    "Dash dot": Qt.DashDotLine,
    "Dash dot dot": Qt.DashDotDotLine,
    "No line": Qt.NoPen,
}

MARKER_SYMBOL_MAP = {
    "None": None,
    "Circle": "o",
    "Square": "s",
    "Triangle down": "t",
    "Triangle up": "t1",
    "Triangle right": "t2",
    "Triangle left": "t3",
    "Pentagon": "p",
    "Hexagon": "h",
    "Star": "star",
    "Plus": "+",
    "Cross": "x",
    "Diamond": "d",
}

DEFAULT_LINE_COLOR = "#1f77b4"
DEFAULT_MARKER_COLOR = "#1f77b4"


def make_curve_pen(color: str, width: int, style_name: str) -> Any:
    """Create a pyqtgraph pen from user-facing style settings."""
    qt_style = LINE_STYLE_MAP.get(style_name, Qt.SolidLine)
    if qt_style == Qt.NoPen:
        return None
    return pg.mkPen(color=color, width=width, style=qt_style)


def marker_symbol_from_name(marker_name: str) -> str | None:
    """Convert a user-facing marker name to a pyqtgraph symbol."""
    return MARKER_SYMBOL_MAP.get(marker_name)


# ---------- Plot state ----------


@dataclass
class PlotStyle:
    line_color: str = DEFAULT_LINE_COLOR
    line_style: str = "Solid"
    line_width: int = 2
    marker_name: str = "None"
    marker_size: int = 7
    marker_color: str = DEFAULT_MARKER_COLOR


@dataclass
class PlotConfig:
    table_name: str
    experiment_name: str
    x_key: str
    y_key: str
    row: int
    col: int
    widget: pg.PlotWidget
    curve: pg.PlotDataItem
    max_points: int | None = None
    style: PlotStyle | None = None


# ---------- Main window ----------


class SqliteLineViewer(QMainWindow):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__()
        self.setWindowTitle("SQLite Experiment Viewer - pyqtgraph")
        self.resize(1450, 900)

        pg.setConfigOptions(antialias=True)

        self.db_path: str | None = db_path
        self.experiments: list[dict[str, Any]] = []
        self.plots: dict[tuple[int, int], PlotConfig] = {}
        self.current_line_color = DEFAULT_LINE_COLOR
        self.current_marker_color = DEFAULT_MARKER_COLOR

        self._build_ui()
        self._connect_signals()
        self._update_color_button(self.line_color_btn, self.current_line_color)
        self._update_color_button(self.marker_color_btn, self.current_marker_color)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_all_plots)

        if self.db_path:
            self.db_path_edit.setText(self.db_path)
            self.load_experiments()

    # ----- UI -----

    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)
        self.setCentralWidget(central)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter)

        self.left_panel = QWidget()
        self.left_panel.setMinimumWidth(420)
        self.left_panel.setMaximumWidth(560)
        left_layout = QVBoxLayout(self.left_panel)

        db_group = QGroupBox("Database")
        db_layout = QVBoxLayout(db_group)
        path_layout = QHBoxLayout()
        self.db_path_edit = QLineEdit()
        self.db_path_edit.setPlaceholderText("Select or enter a SQLite database path")
        self.browse_btn = QPushButton("Browse")
        path_layout.addWidget(self.db_path_edit)
        path_layout.addWidget(self.browse_btn)
        db_layout.addLayout(path_layout)
        self.reload_exp_btn = QPushButton("Reload experiments")
        db_layout.addWidget(self.reload_exp_btn)
        left_layout.addWidget(db_group)

        exp_group = QGroupBox("Experiments")
        exp_layout = QVBoxLayout(exp_group)
        self.exp_list = QListWidget()
        self.exp_list.setMinimumHeight(95)
        self.exp_list.setMaximumHeight(145)
        exp_layout.addWidget(self.exp_list)
        left_layout.addWidget(exp_group)

        meta_group = QGroupBox("Meta")
        meta_layout = QVBoxLayout(meta_group)
        self.meta_tree = QTreeWidget()
        self.meta_tree.setColumnCount(2)
        self.meta_tree.setHeaderLabels(["Key", "Value"])
        self.meta_tree.setAlternatingRowColors(True)
        self.meta_tree.setMinimumHeight(120)
        self.meta_tree.setMaximumHeight(220)
        self.meta_tree.header().setStretchLastSection(True)
        meta_layout.addWidget(self.meta_tree)
        left_layout.addWidget(meta_group)

        axis_group = QGroupBox("Data keys")
        axis_form = QFormLayout(axis_group)
        self.x_combo = QComboBox()
        self.y_combo = QComboBox()
        axis_form.addRow("x key", self.x_combo)
        axis_form.addRow("y key", self.y_combo)
        left_layout.addWidget(axis_group)

        place_group = QGroupBox("Plot placement")
        place_form = QFormLayout(place_group)
        self.row_spin = QSpinBox()
        self.row_spin.setRange(0, 99)
        self.col_spin = QSpinBox()
        self.col_spin.setRange(0, 99)
        self.max_points_spin = QSpinBox()
        self.max_points_spin.setRange(0, 10_000_000)
        self.max_points_spin.setValue(0)
        self.max_points_spin.setSpecialValueText("All")
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Leave empty to use the default title")
        place_form.addRow("grid row", self.row_spin)
        place_form.addRow("grid col", self.col_spin)
        place_form.addRow("max points", self.max_points_spin)
        place_form.addRow("plot title", self.title_edit)
        left_layout.addWidget(place_group)

        style_group = QGroupBox("Curve style")
        style_form = QFormLayout(style_group)

        self.line_color_btn = QPushButton()
        self.line_color_btn.setMinimumHeight(28)
        self.line_style_combo = QComboBox()
        self.line_style_combo.addItems(list(LINE_STYLE_MAP.keys()))
        self.line_width_spin = QSpinBox()
        self.line_width_spin.setRange(1, 20)
        self.line_width_spin.setValue(2)

        self.marker_combo = QComboBox()
        self.marker_combo.addItems(list(MARKER_SYMBOL_MAP.keys()))
        self.marker_size_spin = QSpinBox()
        self.marker_size_spin.setRange(1, 50)
        self.marker_size_spin.setValue(7)
        self.marker_color_btn = QPushButton()
        self.marker_color_btn.setMinimumHeight(28)

        style_form.addRow("line color", self.line_color_btn)
        style_form.addRow("line style", self.line_style_combo)
        style_form.addRow("line width", self.line_width_spin)
        style_form.addRow("marker", self.marker_combo)
        style_form.addRow("marker size", self.marker_size_spin)
        style_form.addRow("marker color", self.marker_color_btn)
        left_layout.addWidget(style_group)

        ctrl_group = QGroupBox("Plot controls")
        ctrl_layout = QVBoxLayout(ctrl_group)
        self.add_plot_btn = QPushButton("Add / replace plot")
        self.apply_style_btn = QPushButton("Apply style to selected grid plot")
        self.refresh_once_btn = QPushButton("Refresh once")
        self.clear_plot_btn = QPushButton("Clear all plots")
        ctrl_layout.addWidget(self.add_plot_btn)
        ctrl_layout.addWidget(self.apply_style_btn)
        ctrl_layout.addWidget(self.refresh_once_btn)
        ctrl_layout.addWidget(self.clear_plot_btn)

        timer_layout = QHBoxLayout()
        self.auto_refresh_check = QCheckBox("Auto refresh")
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(100, 3_600_000)
        self.interval_spin.setSingleStep(100)
        self.interval_spin.setValue(1000)
        self.interval_spin.setSuffix(" ms")
        timer_layout.addWidget(self.auto_refresh_check)
        timer_layout.addWidget(self.interval_spin)
        ctrl_layout.addLayout(timer_layout)
        left_layout.addWidget(ctrl_group)
        left_layout.addStretch(1)

        splitter.addWidget(self.left_panel)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.plot_container = QWidget()
        self.plot_grid = QGridLayout(self.plot_container)
        self.plot_grid.setContentsMargins(8, 8, 8, 8)
        self.plot_grid.setSpacing(8)
        self.scroll.setWidget(self.plot_container)
        splitter.addWidget(self.scroll)
        splitter.setStretchFactor(1, 1)

    def _connect_signals(self) -> None:
        self.browse_btn.clicked.connect(self.browse_db)
        self.reload_exp_btn.clicked.connect(self.load_experiments)
        self.exp_list.currentItemChanged.connect(self.on_experiment_changed)
        self.line_color_btn.clicked.connect(self.choose_line_color)
        self.marker_color_btn.clicked.connect(self.choose_marker_color)
        self.add_plot_btn.clicked.connect(self.add_or_replace_plot)
        self.apply_style_btn.clicked.connect(self.apply_style_to_selected_grid_plot)
        self.refresh_once_btn.clicked.connect(self.refresh_all_plots)
        self.clear_plot_btn.clicked.connect(self.clear_all_plots)
        self.auto_refresh_check.toggled.connect(self.on_auto_refresh_toggled)
        self.interval_spin.valueChanged.connect(self.on_interval_changed)

    # ----- Meta tree -----

    def populate_meta_tree(self, meta_text: str | None) -> None:
        self.meta_tree.clear()

        if not meta_text:
            QTreeWidgetItem(self.meta_tree, ["<empty>", ""])
            return

        try:
            meta_obj = json.loads(meta_text)
        except Exception:
            QTreeWidgetItem(self.meta_tree, ["raw", value_to_display(meta_text, max_len=500)])
            self.meta_tree.resizeColumnToContents(0)
            return

        root = self.meta_tree.invisibleRootItem()
        if isinstance(meta_obj, dict):
            for key, value in meta_obj.items():
                self._add_meta_tree_item(root, str(key), value)
        elif isinstance(meta_obj, list):
            for index, value in enumerate(meta_obj):
                self._add_meta_tree_item(root, f"[{index}]", value)
        else:
            QTreeWidgetItem(self.meta_tree, ["value", value_to_display(meta_obj)])

        self.meta_tree.expandAll()
        self.meta_tree.resizeColumnToContents(0)

    def _add_meta_tree_item(self, parent: QTreeWidgetItem, key: str, value: Any) -> None:
        if isinstance(value, dict):
            item = QTreeWidgetItem(parent, [key, ""])
            for child_key, child_value in value.items():
                self._add_meta_tree_item(item, str(child_key), child_value)
        elif isinstance(value, list):
            item = QTreeWidgetItem(parent, [key, f"list[{len(value)}]"])
            for index, child_value in enumerate(value):
                self._add_meta_tree_item(item, f"[{index}]", child_value)
        else:
            QTreeWidgetItem(parent, [key, value_to_display(value)])

    # ----- Style selection -----

    def _update_color_button(self, button: QPushButton, color: str) -> None:
        button.setText(color)
        button.setStyleSheet(
            f"QPushButton {{ background-color: {color}; color: white; font-weight: bold; }}"
        )

    def choose_line_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.current_line_color), self, "Select line color")
        if color.isValid():
            self.current_line_color = color.name()
            self._update_color_button(self.line_color_btn, self.current_line_color)

    def choose_marker_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.current_marker_color), self, "Select marker color")
        if color.isValid():
            self.current_marker_color = color.name()
            self._update_color_button(self.marker_color_btn, self.current_marker_color)

    def current_plot_style(self) -> PlotStyle:
        return PlotStyle(
            line_color=self.current_line_color,
            line_style=self.line_style_combo.currentText(),
            line_width=self.line_width_spin.value(),
            marker_name=self.marker_combo.currentText(),
            marker_size=self.marker_size_spin.value(),
            marker_color=self.current_marker_color,
        )

    def apply_style_to_curve(self, curve: pg.PlotDataItem, style: PlotStyle) -> None:
        pen = make_curve_pen(style.line_color, style.line_width, style.line_style)
        symbol = marker_symbol_from_name(style.marker_name)

        curve.setPen(pen)
        curve.setSymbol(symbol)
        curve.setSymbolSize(style.marker_size)
        curve.setSymbolBrush(pg.mkBrush(style.marker_color))
        curve.setSymbolPen(pg.mkPen(style.marker_color))

    def apply_style_to_selected_grid_plot(self) -> None:
        row = self.row_spin.value()
        col = self.col_spin.value()
        config = self.plots.get((row, col))
        if config is None:
            self.statusBar().showMessage(f"No plot found at grid ({row}, {col})", 3000)
            return

        style = self.current_plot_style()
        config.style = style
        self.apply_style_to_curve(config.curve, style)
        self.statusBar().showMessage(f"Style applied to grid ({row}, {col})", 2000)

    # ----- Database and experiment selection -----

    def browse_db(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select SQLite database",
            "",
            "SQLite DB (*.db *.sqlite *.sqlite3);;All files (*)",
        )
        if path:
            self.db_path_edit.setText(path)
            self.load_experiments()

    def current_db_path(self) -> str:
        path = self.db_path_edit.text().strip()
        if not path:
            raise RuntimeError("Please select a SQLite database file first.")
        if not Path(path).exists():
            raise RuntimeError(f"Database file does not exist: {path}")
        return path

    def load_experiments(self) -> None:
        try:
            self.db_path = self.current_db_path()
            self.experiments = fetch_experiments(self.db_path)
        except Exception as exc:
            self.show_error("Failed to read experiments", exc)
            return

        self.exp_list.clear()
        self.meta_tree.clear()
        for exp in self.experiments:
            index = exp.get("_rowid_")
            name = exp.get("experiment_name") or "<unnamed>"
            table = exp.get("table_name") or "<no table>"
            text = f"{index} | {name} | {table}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, exp)
            self.exp_list.addItem(item)

        if self.exp_list.count() > 0:
            self.exp_list.setCurrentRow(0)
        else:
            self.x_combo.clear()
            self.y_combo.clear()
            QTreeWidgetItem(self.meta_tree, ["<empty>", ""])

    def on_experiment_changed(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        if current is None or self.db_path is None:
            return
        exp = current.data(Qt.UserRole)
        table_name = exp.get("table_name")
        self.populate_meta_tree(exp.get("meta"))
        self.title_edit.clear()

        try:
            columns = fetch_table_columns(self.db_path, table_name)
        except Exception as exc:
            self.show_error("Failed to read table columns", exc)
            return

        self.x_combo.clear()
        self.y_combo.clear()
        self.x_combo.addItems(columns)
        self.y_combo.addItems(columns)

        self._choose_default_axis(columns)
        self.update_existing_plots_for_experiment(exp, columns)

    def _choose_default_axis(self, columns: list[str]) -> None:
        lower_map = {c.lower(): c for c in columns}

        def choose(combo: QComboBox, candidates: list[str], fallback_index: int) -> None:
            for cand in candidates:
                for low, original in lower_map.items():
                    if cand in low:
                        combo.setCurrentText(original)
                        return
            if combo.count() > fallback_index:
                combo.setCurrentIndex(fallback_index)

        choose(self.x_combo, ["time", "timestamp", "index", "step", "xdc", "vdc", "bias"], 0)
        choose(self.y_combo, ["current", "idc", "iac", "voltage", "resistance", "y", "signal"], 1 if len(columns) > 1 else 0)

    def update_existing_plots_for_experiment(self, exp: dict[str, Any], columns: list[str]) -> None:
        """
        Reuse existing plot configurations when the selected experiment changes.

        The grid position, x/y keys, style, and max_points are preserved. Only the
        data source table and experiment name are replaced by the newly selected
        experiment. If the new table does not contain the required x/y keys, the
        corresponding plot is kept but cleared.
        """
        if not self.plots:
            return

        table_name = exp.get("table_name")
        experiment_name = exp.get("experiment_name") or "<unnamed>"
        if not table_name:
            return

        available_columns = set(columns)
        updated_count = 0
        skipped_count = 0

        for config in list(self.plots.values()):
            config.table_name = table_name
            config.experiment_name = experiment_name

            missing_keys = [key for key in (config.x_key, config.y_key) if key not in available_columns]
            if missing_keys:
                config.curve.setData([], [])
                config.widget.setTitle(
                    f"{experiment_name}: missing key(s): {', '.join(missing_keys)}"
                )
                skipped_count += 1
                continue

            config.widget.setLabel("bottom", config.x_key)
            config.widget.setLabel("left", config.y_key)
            self.refresh_plot(config)
            updated_count += 1

        if skipped_count:
            self.statusBar().showMessage(
                f"Updated {updated_count} plot(s); skipped {skipped_count} plot(s) due to missing keys.",
                5000,
            )
        else:
            self.statusBar().showMessage(
                f"Updated {updated_count} plot(s) for the selected experiment.",
                3000,
            )

    # ----- Plot management -----

    def add_or_replace_plot(self) -> None:
        try:
            item = self.exp_list.currentItem()
            if item is None:
                raise RuntimeError("Please select an experiment first.")
            exp = item.data(Qt.UserRole)
            table_name = exp.get("table_name")
            experiment_name = exp.get("experiment_name") or "<unnamed>"
            x_key = self.x_combo.currentText()
            y_key = self.y_combo.currentText()
            if not table_name or not x_key or not y_key:
                raise RuntimeError("table_name, x key, or y key is empty.")

            row = self.row_spin.value()
            col = self.col_spin.value()
            max_points = self.max_points_spin.value() or None
            style = self.current_plot_style()
        except Exception as exc:
            self.show_error("Failed to add plot", exc)
            return

        self.remove_plot(row, col)

        title = self.title_edit.text().strip() or f"{experiment_name}: {y_key} vs {x_key}"
        plot_widget = pg.PlotWidget(title=title)
        plot_widget.getViewBox().setMouseMode(pg.ViewBox.RectMode)
        plot_widget.setMinimumSize(420, 280)
        plot_widget.showGrid(x=True, y=True, alpha=0.25)
        plot_widget.setLabel("bottom", x_key)
        plot_widget.setLabel("left", y_key)

        curve = plot_widget.plot([], [])
        self.apply_style_to_curve(curve, style)

        config = PlotConfig(
            table_name=table_name,
            experiment_name=experiment_name,
            x_key=x_key,
            y_key=y_key,
            row=row,
            col=col,
            widget=plot_widget,
            curve=curve,
            max_points=max_points,
            style=style,
        )
        self.plots[(row, col)] = config
        self.plot_grid.addWidget(plot_widget, row, col)

        self.refresh_plot(config)

    def remove_plot(self, row: int, col: int) -> None:
        config = self.plots.pop((row, col), None)
        if config is not None:
            self.plot_grid.removeWidget(config.widget)
            config.widget.setParent(None)
            config.widget.deleteLater()

    def clear_all_plots(self) -> None:
        for row, col in list(self.plots.keys()):
            self.remove_plot(row, col)

    def refresh_all_plots(self) -> None:
        for config in list(self.plots.values()):
            self.refresh_plot(config)

    def refresh_plot(self, config: PlotConfig) -> None:
        if self.db_path is None:
            return
        try:
            x, y = fetch_xy_data(
                self.db_path,
                config.table_name,
                config.x_key,
                config.y_key,
                max_points=config.max_points,
            )
        except Exception as exc:
            self.statusBar().showMessage(f"Refresh failed: {exc}", 5000)
            return

        config.curve.setData(x, y)
        if config.style is not None:
            self.apply_style_to_curve(config.curve, config.style)
        config.widget.setTitle(
            f"{config.experiment_name}: {config.y_key} vs {config.x_key}    n={len(x)}"
        )
        self.statusBar().showMessage("Plots refreshed", 1500)

    # ----- Refresh timer -----

    def on_auto_refresh_toggled(self, checked: bool) -> None:
        if checked:
            self.refresh_timer.start(self.interval_spin.value())
        else:
            self.refresh_timer.stop()

    def on_interval_changed(self, value: int) -> None:
        if self.refresh_timer.isActive():
            self.refresh_timer.start(value)

    # ----- Window close -----

    def closeEvent(self, event) -> None:
        self.refresh_timer.stop()
        self.clear_all_plots()
        super().closeEvent(event)

    # ----- Error handling -----

    def show_error(self, title: str, exc: Exception) -> None:
        QMessageBox.critical(self, title, str(exc))
        self.statusBar().showMessage(f"{title}: {exc}", 5000)


# ---------- Entry point ----------


def main() -> int:
    app = pg.mkQApp("SQLite Experiment Viewer - pyqtgraph")
    db_path = sys.argv[1] if len(sys.argv) > 1 else None
    viewer = SqliteLineViewer(db_path=db_path)
    viewer.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
