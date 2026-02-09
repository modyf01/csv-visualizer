import sys
import math
import pandas as pd

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtGui import QAction, QShortcut
from PySide6.QtCore import Qt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.colors as mcolors
from matplotlib.patches import Patch
from matplotlib.widgets import SpanSelector


def generate_palette(n: int):
    if n <= 0:
        return []
    colors = []
    for i in range(n):
        h = i / n
        rgb = mcolors.hsv_to_rgb((h, 0.6, 1.0))
        colors.append(mcolors.to_hex(rgb))
    return colors


class PlotCanvas(FigureCanvas):
    def __init__(self, parent=None, toggle_compact_callback=None, selection_callback=None):
        self.fig = Figure(figsize=(6, 4))
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)
        self.toggle_compact_callback = toggle_compact_callback
        self.selection_callback = selection_callback
        self._press_event = None
        self._span_selector = None
        self.mpl_connect("scroll_event", self.on_scroll)
        self.mpl_connect("button_press_event", self.on_button_press)
        self.mpl_connect("button_release_event", self.on_button_release)
        self.mpl_connect("motion_notify_event", self.on_mouse_move)

    def plot_data_with_background(
        self,
        df: pd.DataFrame,
        value_cols,
        cat_col,
        no_bg_value,
        point_col,
        point_value,
        bg_color_map=None,
        show_bg_legend=False,
        show_series_legend=True,
    ):
        self.ax.clear()
        x = df.index.values

        if cat_col is not None and cat_col in df.columns and bg_color_map:
            cat_vals = df[cat_col].astype(str).values
            self._draw_category_background(cat_vals, no_bg_value, bg_color_map)

        for col in value_cols:
            if col in df.columns:
                y = df[col].values
                self.ax.plot(x, y, linewidth=1.15, label=col)

        if point_col is not None and point_col in df.columns and point_value is not None:
            point_vals = df[point_col].astype(str).values
            self._draw_point_markers(point_vals, point_value)

        leg1 = None
        if show_series_legend and value_cols:
            leg1 = self.ax.legend(loc="upper right", fontsize=8, frameon=True)
            leg1.get_frame().set_alpha(0.85)

        if show_bg_legend and bg_color_map:
            patches = []
            for name, color in bg_color_map.items():
                patches.append(Patch(facecolor=color, edgecolor="none", alpha=0.4, label=name))
            leg2 = self.ax.legend(
                handles=patches,
                loc="upper left",
                fontsize=8,
                frameon=True,
                bbox_to_anchor=(0.0, 1.0),
                borderaxespad=1.0,
            )
            if leg1 is not None:
                self.ax.add_artist(leg1)

        self.ax.set_xlabel("index")
        self.ax.grid(True, linestyle="--", alpha=0.3)
        self.fig.tight_layout()
        self.draw()

    def _draw_category_background(self, cat_vals, no_bg_value, color_map: dict):
        n = len(cat_vals)
        if n == 0:
            return
        current_val = cat_vals[0]
        start_idx = 0
        for i in range(1, n + 1):
            end_of_run = (i == n) or (cat_vals[i] != current_val)
            if end_of_run:
                if not (no_bg_value is not None and current_val == no_bg_value):
                    if current_val in color_map:
                        color = color_map[current_val]
                        self.ax.axvspan(start_idx - 0.5, i - 0.5, facecolor=color, alpha=0.13, zorder=0)
                if i < n:
                    current_val = cat_vals[i]
                    start_idx = i

    def _draw_point_markers(self, point_vals, target_value: str):
        for idx, v in enumerate(point_vals):
            if v == target_value:
                self.ax.axvline(idx, color="#d63031", linewidth=1.0, alpha=0.9, zorder=5)

    def on_scroll(self, event):
        ctrl_pressed = False
        if event.guiEvent is not None:
            modifiers = event.guiEvent.modifiers()
            ctrl_pressed = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        ax = self.ax
        if ctrl_pressed:
            cur_ylim = ax.get_ylim()
            ydata = event.ydata if event.ydata is not None else (cur_ylim[0] + cur_ylim[1]) / 2
            scale = 1.1 if event.button == "up" else 1 / 1.1
            new_ylim = self._zoom_limits(cur_ylim, ydata, scale)
            ax.set_ylim(new_ylim)
        else:
            cur_xlim = ax.get_xlim()
            xdata = event.xdata if event.xdata is not None else (cur_xlim[0] + cur_xlim[1]) / 2
            scale = 1.1 if event.button == "up" else 1 / 1.1
            new_xlim = self._zoom_limits(cur_xlim, xdata, scale)
            ax.set_xlim(new_xlim)
        self.draw_idle()

    @staticmethod
    def _zoom_limits(lims, center, scale):
        left, right = lims
        new_left = center - (center - left) / scale
        new_right = center + (right - center) / scale
        return new_left, new_right

    def on_button_press(self, event):
        if getattr(event, "dblclick", False) and callable(self.toggle_compact_callback):
            self.toggle_compact_callback()
            return
        if event.button in [1, 2]:
            self._press_event = event

    def on_button_release(self, event):
        self._press_event = None

    def on_mouse_move(self, event):
        if self._press_event is None:
            return
        if event.xdata is None or event.ydata is None:
            return
        dx = event.xdata - self._press_event.xdata
        dy = event.ydata - self._press_event.ydata
        ax = self.ax
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        ax.set_xlim(xlim[0] - dx, xlim[1] - dx)
        ax.set_ylim(ylim[0] - dy, ylim[1] - dy)
        self.draw_idle()

    def enable_selection_mode(self, enabled: bool):
        if enabled and self._span_selector is None:
            self._span_selector = SpanSelector(
                self.ax,
                self._on_select,
                'horizontal',
                useblit=True,
                props=dict(alpha=0.3, facecolor='red'),
                interactive=True,
                drag_from_anywhere=True,
                button=3
            )
        elif not enabled and self._span_selector is not None:
            self._span_selector.set_active(False)
            self._span_selector = None
            self.draw_idle()

    def _on_select(self, xmin, xmax):
        if self.selection_callback:
            start_idx = int(round(xmin))
            end_idx = int(round(xmax))
            self.selection_callback(start_idx, end_idx)
    
    def clear_selection(self):
        if self._span_selector is not None:
            self._span_selector.set_active(False)
            self._span_selector = None
            self._span_selector = SpanSelector(
                self.ax,
                self._on_select,
                'horizontal',
                useblit=True,
                props=dict(alpha=0.3, facecolor='red'),
                interactive=True,
                drag_from_anywhere=True,
                button=3
            )
            self.draw_idle()


class PandasModel(QtCore.QAbstractTableModel):
    def __init__(self, df: pd.DataFrame):
        super().__init__()
        self._df = df

    def rowCount(self, parent=None):
        return len(self._df.index)

    def columnCount(self, parent=None):
        return len(self._df.columns)

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            value = self._df.iat[index.row(), index.column()]
            return str(value)
        return None

    def headerData(self, section, orientation, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            if orientation == QtCore.Qt.Orientation.Horizontal:
                return self._df.columns[section]
            else:
                return str(self._df.index[section])
        return None


class MainWindow(QtWidgets.QMainWindow):
    MAX_ROWS_BEFORE_CHUNK = 90_000
    CHUNK_SIZE = 45_000

    def __init__(self):
        super().__init__()

        self.setWindowTitle("CSV Visualizer – continuous • categorical • markers")
        self.resize(1400, 820)

        self._compact = False

        QtWidgets.QApplication.setStyle("Fusion")
        self._apply_light_palette()
        self._apply_stylesheet()

        self.df: pd.DataFrame | None = None
        self.current_csv_path: str | None = None
        self.has_unsaved_changes = False
        self.total_chunks = 1
        self.current_chunk = 0
        self.col_unique_cache: dict[str, list[str] | None] = {}
        self._show_series_legend = True
        self._show_bg_legend = True

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_v = QtWidgets.QVBoxLayout(central)
        main_v.setContentsMargins(10, 8, 10, 8)
        main_v.setSpacing(8)

        toolbar = QtWidgets.QToolBar("Tools")
        toolbar.setIconSize(QtCore.QSize(18, 18))
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        open_action = QAction(QtGui.QIcon.fromTheme("document-open"), "Open CSV…", self)
        open_action.triggered.connect(self.open_csv)
        toolbar.addAction(open_action)

        self.save_action = QAction(QtGui.QIcon.fromTheme("document-save"), "Save", self)
        self.save_action.setShortcut(QtGui.QKeySequence.Save)
        self.save_action.triggered.connect(self.save_csv)
        self.save_action.setEnabled(False)
        toolbar.addAction(self.save_action)

        self.save_as_action = QAction(QtGui.QIcon.fromTheme("document-save-as"), "Save As…", self)
        self.save_as_action.setShortcut(QtGui.QKeySequence.SaveAs)
        self.save_as_action.triggered.connect(self.save_csv_as)
        self.save_as_action.setEnabled(False)
        toolbar.addAction(self.save_as_action)

        toolbar.addSeparator()

        self.toggle_compact_action = QAction(QtGui.QIcon.fromTheme("view-fullscreen"), "Plot only (Esc)", self)
        self.toggle_compact_action.setCheckable(True)
        self.toggle_compact_action.triggered.connect(self.toggle_compact_mode)
        toolbar.addAction(self.toggle_compact_action)

        self.control_frame = QtWidgets.QFrame()
        control_h = QtWidgets.QHBoxLayout(self.control_frame)
        control_h.setContentsMargins(8, 8, 8, 8)
        control_h.setSpacing(12)

        grp_series = QtWidgets.QGroupBox("Series (continuous)")
        form_series = QtWidgets.QFormLayout(grp_series)
        form_series.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.value_cols_list = QtWidgets.QListWidget()
        self.value_cols_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        self.value_cols_list.setMinimumHeight(90)
        form_series.addRow("Columns:", self.value_cols_list)

        grp_bg = QtWidgets.QGroupBox("Background (categorical)")
        form_bg = QtWidgets.QFormLayout(grp_bg)
        form_bg.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.cat_col_combo = QtWidgets.QComboBox()
        self.cat_col_combo.currentTextChanged.connect(self.on_cat_column_changed)
        self.no_bg_combo = QtWidgets.QComboBox()
        self.no_bg_edit = QtWidgets.QLineEdit()
        self.no_bg_edit.setPlaceholderText("Enter no-background value…")
        self.no_bg_edit.hide()
        form_bg.addRow("Column:", self.cat_col_combo)
        form_bg.addRow("No background:", self.no_bg_combo)
        form_bg.addRow("", self.no_bg_edit)
        
        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.HLine)
        separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        form_bg.addRow("", separator)
        
        edit_hint = QtWidgets.QLabel("Right-click + drag on plot to select range")
        edit_hint.setStyleSheet("color: #666; font-size: 10px; font-style: italic;")
        edit_hint.setWordWrap(True)
        form_bg.addRow("", edit_hint)
        
        self.edit_value_combo = QtWidgets.QComboBox()
        self.edit_value_combo.setEditable(True)
        self.edit_value_combo.setPlaceholderText("Select or enter new value…")
        self.edit_value_combo.setEnabled(False)
        form_bg.addRow("Assign value:", self.edit_value_combo)
        
        self.apply_edit_btn = QtWidgets.QPushButton("Apply to selection")
        self.apply_edit_btn.setEnabled(False)
        self.apply_edit_btn.clicked.connect(self.apply_edit_to_selection)
        form_bg.addRow("", self.apply_edit_btn)
        
        self.selection_label = QtWidgets.QLabel("No selection")
        self.selection_label.setStyleSheet("color: #666; font-size: 11px;")
        form_bg.addRow("", self.selection_label)
        
        self.selected_range = None

        grp_pts = QtWidgets.QGroupBox("Markers (vertical)")
        form_pts = QtWidgets.QFormLayout(grp_pts)
        form_pts.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.point_col_combo = QtWidgets.QComboBox()
        self.point_col_combo.currentTextChanged.connect(self.on_point_column_changed)
        self.point_value_combo = QtWidgets.QComboBox()
        self.point_value_edit = QtWidgets.QLineEdit()
        self.point_value_edit.setPlaceholderText("Enter value…")
        self.point_value_edit.hide()
        form_pts.addRow("Column:", self.point_col_combo)
        form_pts.addRow("Value:", self.point_value_combo)
        form_pts.addRow("", self.point_value_edit)

        grp_seg = QtWidgets.QGroupBox("Segment")
        seg_layout = QtWidgets.QGridLayout(grp_seg)
        self.prev_seg_btn = QtWidgets.QPushButton("◀")
        self.next_seg_btn = QtWidgets.QPushButton("▶")
        self.seg_label = QtWidgets.QLabel("1 / 1")
        self.seg_spin = QtWidgets.QSpinBox()
        self.seg_spin.setMinimum(1)
        self.seg_spin.setMaximum(1)
        self.seg_spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.prev_seg_btn.clicked.connect(self.prev_segment)
        self.next_seg_btn.clicked.connect(self.next_segment)
        self.seg_spin.valueChanged.connect(self.on_segment_spin_changed)
        seg_layout.addWidget(self.prev_seg_btn, 0, 0)
        seg_layout.addWidget(self.seg_label, 0, 1)
        seg_layout.addWidget(self.next_seg_btn, 0, 2)
        seg_layout.addWidget(QtWidgets.QLabel("Go to:"), 1, 0, 1, 1)
        seg_layout.addWidget(self.seg_spin, 1, 1, 1, 2)

        self.plot_btn = QtWidgets.QPushButton("Plot")
        self.plot_btn.setMinimumHeight(34)
        self.plot_btn.clicked.connect(self.redraw_plot)

        control_h.addWidget(grp_series, 2)
        control_h.addWidget(grp_bg, 2)
        control_h.addWidget(grp_pts, 2)
        control_h.addWidget(grp_seg, 0)
        control_h.addWidget(self.plot_btn, 0, Qt.AlignBottom)

        main_v.addWidget(self.control_frame)

        self.splitter = QtWidgets.QSplitter()
        self.splitter.setOrientation(QtCore.Qt.Orientation.Horizontal)
        main_v.addWidget(self.splitter, 1)

        self.table_view = QtWidgets.QTableView()
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSortingEnabled(False)
        self.splitter.addWidget(self.table_view)

        self.canvas = PlotCanvas(self, toggle_compact_callback=self.toggle_compact_mode, selection_callback=self.on_range_selected)
        self.splitter.addWidget(self.canvas)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)

        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        file_menu.addAction(open_action)
        file_menu.addAction(self.save_action)
        file_menu.addAction(self.save_as_action)

        settings_menu = menubar.addMenu("&Settings")
        self.series_legend_action = QAction("Show series legend", self)
        self.series_legend_action.setCheckable(True)
        self.series_legend_action.setChecked(self._show_series_legend)
        self.series_legend_action.triggered.connect(self._on_toggle_series_legend)
        settings_menu.addAction(self.series_legend_action)

        self.bg_legend_action = QAction("Show background legend", self)
        self.bg_legend_action.setCheckable(True)
        self.bg_legend_action.setChecked(self._show_bg_legend)
        self.bg_legend_action.triggered.connect(self._on_toggle_bg_legend)
        settings_menu.addAction(self.bg_legend_action)

        view_menu = menubar.addMenu("&View")
        view_menu.addAction(self.toggle_compact_action)

        self.statusBar().showMessage("Open a CSV → select columns → Plot.")

        QShortcut(Qt.Key_Escape, self, activated=self.toggle_compact_mode)

    def _apply_light_palette(self):
        pal = QtGui.QPalette()
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor(244, 246, 249))
        pal.setColor(QtGui.QPalette.WindowText, Qt.black)
        pal.setColor(QtGui.QPalette.Base, Qt.white)
        pal.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(241, 243, 247))
        pal.setColor(QtGui.QPalette.ToolTipBase, Qt.white)
        pal.setColor(QtGui.QPalette.ToolTipText, Qt.black)
        pal.setColor(QtGui.QPalette.Text, Qt.black)
        pal.setColor(QtGui.QPalette.Button, Qt.white)
        pal.setColor(QtGui.QPalette.ButtonText, Qt.black)
        pal.setColor(QtGui.QPalette.BrightText, Qt.red)
        pal.setColor(QtGui.QPalette.Highlight, QtGui.QColor(207, 227, 255))
        pal.setColor(QtGui.QPalette.HighlightedText, Qt.black)
        pal.setColor(QtGui.QPalette.Inactive, QtGui.QPalette.Highlight, QtGui.QColor(207, 227, 255))
        pal.setColor(QtGui.QPalette.Inactive, QtGui.QPalette.HighlightedText, Qt.black)
        self.setPalette(pal)

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow {
                background: #f4f6f9;
            }
            QGroupBox {
                font-weight: 600;
                border: 1px solid #e0e3e7;
                border-radius: 10px;
                margin-top: 8px;
                padding: 8px;
                background: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QPushButton {
                padding: 6px 12px;
                border: 1px solid #cccccc;
                border-radius: 6px;
                background: #ffffff;
            }
            QPushButton:hover {
                background: #edf3ff;
            }
            QComboBox, QLineEdit, QListWidget, QSpinBox {
                border: 1px solid #cccccc;
                border-radius: 6px;
                padding: 4px;
                background: #ffffff;
            }
            QListWidget::item:selected {
                background: #cfe3ff;
                color: #000000;
            }
            QListWidget::item:hover {
                background: #e4efff;
                color: #000000;
            }
            QTableView::item:selected {
                background: #cfe3ff;
                color: #000000;
            }
            QTableView::item:hover {
                background: #e4efff;
                color: #000000;
            }
            QComboBox QAbstractItemView::item:selected {
                background: #cfe3ff;
                color: #000000;
            }
            QComboBox QAbstractItemView::item:hover {
                background: #e4efff;
                color: #000000;
            }
            QToolBar {
                padding: 4px;
                border: 0px;
                background: #ffffff;
            }
        """)

    def _calc_unique_values_up_to_30(self, series: pd.Series) -> list[str] | None:
        n = len(series)
        if n == 0:
            return []
        head_n = min(100, n)
        head_vals = series.iloc[:head_n].astype(str)
        head_uniques = head_vals.unique().tolist()
        if len(head_uniques) > 30:
            return None
        sample_size = min(10_000, n)
        if sample_size > head_n:
            sample_vals = series.sample(sample_size, random_state=0).astype(str)
        else:
            sample_vals = head_vals
        sample_uniques = sample_vals.unique().tolist()
        if len(sample_uniques) > 30:
            return None
        full_uniques = series.astype(str).unique().tolist()
        if len(full_uniques) > 30:
            return None
        return full_uniques

    def open_csv(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open CSV", "", "CSV files (*.csv);;All files (*)"
        )
        if not path:
            return
        self.load_csv_file(path)

    def load_csv_file(self, path: str):
        try:
            self.df = pd.read_csv(path)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to load CSV:\n{e}")
            return

        self.current_csv_path = path
        self.has_unsaved_changes = False
        self._update_window_title()
        self.save_action.setEnabled(True)
        self.save_as_action.setEnabled(True)

        self.col_unique_cache = {}
        for col in self.df.columns:
            uniqs = self._calc_unique_values_up_to_30(self.df[col])
            self.col_unique_cache[col] = uniqs

        model = PandasModel(self.df)
        self.table_view.setModel(model)
        self.table_view.resizeColumnsToContents()

        self.value_cols_list.clear()
        for col in self.df.columns:
            self.value_cols_list.addItem(col)

        self.cat_col_combo.clear()
        self.cat_col_combo.addItem("— none —")
        self.cat_col_combo.addItems(list(self.df.columns))

        self.no_bg_combo.clear()
        self.no_bg_combo.addItem("— none —")
        self.no_bg_combo.show()
        self.no_bg_edit.hide()

        self.point_col_combo.clear()
        self.point_col_combo.addItem("— none —")
        self.point_col_combo.addItems(list(self.df.columns))

        self.point_value_combo.clear()
        self.point_value_combo.addItem("— none —")
        self.point_value_combo.show()
        self.point_value_edit.hide()

        n_rows = len(self.df)
        if n_rows > self.MAX_ROWS_BEFORE_CHUNK:
            self.total_chunks = math.ceil(n_rows / self.CHUNK_SIZE)
        else:
            self.total_chunks = 1
        self.current_chunk = 0
        self._update_segment_label()

        self.statusBar().showMessage(f"Loaded: {path} ({n_rows} rows, segments: {self.total_chunks})")
        self.redraw_plot()

    def save_csv(self):
        if self.df is None:
            return
        
        if self.current_csv_path is None:
            self.save_csv_as()
            return
        
        try:
            self.df.to_csv(self.current_csv_path, index=False)
            self.has_unsaved_changes = False
            self._update_window_title()
            self.statusBar().showMessage(f"Saved: {self.current_csv_path}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to save CSV:\n{e}")

    def save_csv_as(self):
        if self.df is None:
            return
        
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save CSV As", self.current_csv_path or "", "CSV files (*.csv);;All files (*)"
        )
        if not path:
            return
        
        try:
            self.df.to_csv(path, index=False)
            self.current_csv_path = path
            self.has_unsaved_changes = False
            self._update_window_title()
            self.statusBar().showMessage(f"Saved: {path}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to save CSV:\n{e}")

    def _update_window_title(self):
        if self.current_csv_path:
            filename = self.current_csv_path.split("/")[-1].split("\\")[-1]
            modified = " *" if self.has_unsaved_changes else ""
            self.setWindowTitle(f"{filename}{modified} – CSV Visualizer")
        else:
            self.setWindowTitle("CSV Visualizer – continuous • categorical • markers")

    def _mark_as_modified(self):
        if not self.has_unsaved_changes:
            self.has_unsaved_changes = True
            self._update_window_title()

    def _get_current_df_slice(self) -> pd.DataFrame:
        if self.df is None:
            return pd.DataFrame()
        if self.total_chunks == 1:
            return self.df.reset_index(drop=True)
        start = self.current_chunk * self.CHUNK_SIZE
        end = min((self.current_chunk + 1) * self.CHUNK_SIZE, len(self.df))
        return self.df.iloc[start:end].reset_index(drop=True)

    def _update_segment_label(self):
        self.seg_label.setText(f"{self.current_chunk + 1} / {self.total_chunks}")
        self.seg_spin.blockSignals(True)
        self.seg_spin.setMaximum(self.total_chunks)
        self.seg_spin.setValue(self.current_chunk + 1)
        self.seg_spin.blockSignals(False)
        self.prev_seg_btn.setEnabled(self.current_chunk > 0)
        self.next_seg_btn.setEnabled(self.current_chunk < self.total_chunks - 1)

    def prev_segment(self):
        if self.current_chunk > 0:
            self.current_chunk -= 1
            self._update_segment_label()
            self.redraw_plot()
            self._clear_selection()

    def next_segment(self):
        if self.current_chunk < self.total_chunks - 1:
            self.current_chunk += 1
            self._update_segment_label()
            self.redraw_plot()
            self._clear_selection()

    def on_segment_spin_changed(self, value: int):
        new_chunk = max(1, min(value, self.total_chunks)) - 1
        if new_chunk != self.current_chunk:
            self.current_chunk = new_chunk
            self._update_segment_label()
            self.redraw_plot()
            self._clear_selection()
    
    def _clear_selection(self):
        self.selected_range = None
        self.selection_label.setText("No selection")
        self.apply_edit_btn.setEnabled(False)
        self.canvas.clear_selection()

    def on_cat_column_changed(self, col_name: str):
        if self.df is None or col_name == "— none —":
            self.no_bg_combo.clear()
            self.no_bg_combo.addItem("— none —")
            self.no_bg_combo.show()
            self.no_bg_edit.hide()
        else:
            uniqs = self.col_unique_cache.get(col_name)
            if uniqs is None:
                self.no_bg_combo.hide()
                self.no_bg_edit.show()
                self.no_bg_edit.clear()
            else:
                self.no_bg_combo.clear()
                self.no_bg_combo.addItem("— none —")
                for v in sorted(uniqs):
                    self.no_bg_combo.addItem(v)
                self.no_bg_combo.show()
                self.no_bg_edit.hide()
        
        self._update_edit_mode()

    def on_point_column_changed(self, col_name: str):
        if self.df is None or col_name == "— none —":
            self.point_value_combo.clear()
            self.point_value_combo.addItem("— none —")
            self.point_value_combo.show()
            self.point_value_edit.hide()
            return
        uniqs = self.col_unique_cache.get(col_name)
        if uniqs is None:
            self.point_value_combo.hide()
            self.point_value_edit.show()
            self.point_value_edit.clear()
        else:
            self.point_value_combo.clear()
            self.point_value_combo.addItem("— none —")
            for v in sorted(uniqs):
                self.point_value_combo.addItem(v)
            self.point_value_combo.show()
            self.point_value_edit.hide()

    def redraw_plot(self):
        if self.df is None or self.df.empty:
            return

        df_slice = self._get_current_df_slice()

        selected_items = self.value_cols_list.selectedItems()
        value_cols = [it.text() for it in selected_items]
        if not value_cols:
            value_cols = [self.df.columns[0]]

        cat_col = self.cat_col_combo.currentText()
        if cat_col == "— none —":
            cat_col = None

        if self.no_bg_combo.isVisible():
            no_bg_val = self.no_bg_combo.currentText()
            if no_bg_val == "— none —":
                no_bg_val = None
        else:
            no_bg_val = self.no_bg_edit.text().strip()
            if no_bg_val == "":
                no_bg_val = None

        point_col = self.point_col_combo.currentText()
        if point_col == "— none —":
            point_col = None
            point_val = None
        else:
            if self.point_value_combo.isVisible():
                point_val = self.point_value_combo.currentText()
                if point_val == "— none —":
                    point_val = None
            else:
                point_val = self.point_value_edit.text().strip()
                if point_val == "":
                    point_val = None

        bg_color_map = None
        if cat_col is not None:
            uniqs = self.col_unique_cache.get(cat_col)
            if uniqs is not None:
                filtered = [u for u in uniqs if (no_bg_val is None or u != no_bg_val)]
                palette = generate_palette(len(filtered))
                bg_color_map = {v: palette[i] for i, v in enumerate(filtered)}

        self.canvas.plot_data_with_background(
            df_slice,
            value_cols=value_cols,
            cat_col=cat_col,
            no_bg_value=no_bg_val,
            point_col=point_col,
            point_value=point_val,
            bg_color_map=bg_color_map,
            show_bg_legend=self._show_bg_legend,
            show_series_legend=self._show_series_legend,
        )

    def _update_edit_mode(self):
        cat_col = self.cat_col_combo.currentText()
        has_cat_col = (cat_col != "— none —" and self.df is not None and cat_col in self.df.columns)
        
        self.canvas.enable_selection_mode(has_cat_col)
        
        if has_cat_col:
            uniqs = self.col_unique_cache.get(cat_col)
            if uniqs is not None:
                self.edit_value_combo.clear()
                self.edit_value_combo.addItems(sorted(uniqs))
        else:
            self.selected_range = None
            self.selection_label.setText("No selection")
            self.apply_edit_btn.setEnabled(False)
            self.edit_value_combo.setEnabled(False)

    def on_range_selected(self, start_idx: int, end_idx: int):
        if start_idx > end_idx:
            start_idx, end_idx = end_idx, start_idx
        
        df_slice = self._get_current_df_slice()
        if start_idx < 0:
            start_idx = 0
        if end_idx >= len(df_slice):
            end_idx = len(df_slice) - 1
        
        if self.total_chunks == 1:
            actual_start = start_idx
            actual_end = end_idx
        else:
            chunk_offset = self.current_chunk * self.CHUNK_SIZE
            actual_start = chunk_offset + start_idx
            actual_end = chunk_offset + end_idx
        
        self.selected_range = (actual_start, actual_end)
        self.selection_label.setText(f"Selected: rows {actual_start} to {actual_end} ({actual_end - actual_start + 1} rows)")
        self.apply_edit_btn.setEnabled(True)
        self.edit_value_combo.setEnabled(True)

    def apply_edit_to_selection(self):
        if self.df is None or self.selected_range is None:
            return
        
        cat_col = self.cat_col_combo.currentText()
        if cat_col == "— none —" or cat_col not in self.df.columns:
            QtWidgets.QMessageBox.warning(self, "No Category Column", "Please select a category column first.")
            return
        
        new_value = self.edit_value_combo.currentText().strip()
        if not new_value:
            QtWidgets.QMessageBox.warning(self, "No Value", "Please enter or select a value to assign.")
            return
        
        start_idx, end_idx = self.selected_range
        
        self.df.loc[start_idx:end_idx, cat_col] = new_value
        
        self._mark_as_modified()
        
        uniqs = self._calc_unique_values_up_to_30(self.df[cat_col])
        self.col_unique_cache[cat_col] = uniqs
        
        if uniqs is not None:
            current_text = self.edit_value_combo.currentText()
            self.edit_value_combo.clear()
            self.edit_value_combo.addItems(sorted(uniqs))
            idx = self.edit_value_combo.findText(current_text)
            if idx >= 0:
                self.edit_value_combo.setCurrentIndex(idx)
        
        model = PandasModel(self.df)
        self.table_view.setModel(model)
        self.table_view.resizeColumnsToContents()
        
        xlim = self.canvas.ax.get_xlim()
        ylim = self.canvas.ax.get_ylim()
        
        self.redraw_plot()
        
        self.canvas.ax.set_xlim(xlim)
        self.canvas.ax.set_ylim(ylim)
        self.canvas.draw_idle()
        
        self._clear_selection()
        
        self.statusBar().showMessage(f"Updated rows {start_idx} to {end_idx} with value '{new_value}'")

    def _on_toggle_series_legend(self, checked: bool):
        self._show_series_legend = checked
        self.redraw_plot()

    def _on_toggle_bg_legend(self, checked: bool):
        self._show_bg_legend = checked
        self.redraw_plot()

    def toggle_compact_mode(self):
        self._compact = not self._compact
        self._apply_compact_mode()

    def _apply_compact_mode(self):
        show_full_ui = not self._compact
        self.control_frame.setVisible(show_full_ui)
        self.table_view.setVisible(show_full_ui)
        for tb in self.findChildren(QtWidgets.QToolBar):
            tb.setVisible(show_full_ui)
        self.menuBar().setVisible(show_full_ui)
        self.statusBar().setVisible(show_full_ui)
        self.toggle_compact_action.setChecked(self._compact)
        if self._compact:
            self.splitter.setSizes([0, 1])
        else:
            self.splitter.setSizes([400, 1000])
        if not self._compact:
            self.statusBar().showMessage("Double-click plot or press Esc to toggle plot-only mode.")
        self.canvas.draw_idle()


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
        if csv_path.lower().endswith('.csv'):
            QtCore.QTimer.singleShot(100, lambda: w.load_csv_file(csv_path))
    
    sys.exit(app.exec())
