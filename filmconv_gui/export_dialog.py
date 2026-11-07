"""Export dialog: which frames, which formats, contact sheet, where to."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QFileDialog,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget, QListWidgetItem,
    QPushButton, QRadioButton, QVBoxLayout,
)

from filmconv import export
from filmconv.roll import Roll

CURRENT, CHOOSE, ALL = range(3)


class ExportDialog(QDialog):
    def __init__(self, parent, roll: Roll, current: str, selected: list[str],
                 icons: dict[str, QIcon], mode: int | None = None):
        super().__init__(parent)
        self.setWindowTitle("Export")
        self.roll, self.current = roll, current
        names = roll.names()
        if mode is None:
            mode = CHOOSE if len(selected) > 1 else CURRENT
        lay = QVBoxLayout(self)

        # Which frames
        g = QGroupBox("Which frames?")
        gl = QVBoxLayout(g)
        self.group = QButtonGroup(self)
        labels = [f"This frame only   ({current})", "Choose frames", f"All frames   ({len(names)})"]
        for i, text in enumerate(labels):
            rb = QRadioButton(text)
            self.group.addButton(rb, i)
            gl.addWidget(rb)
        self.list = QListWidget()
        self.list.setViewMode(QListView.IconMode)
        self.list.setIconSize(QSize(120, 80))
        self.list.setGridSize(QSize(136, 112))
        self.list.setResizeMode(QListView.Adjust)
        self.list.setMovement(QListView.Static)
        self.list.setSelectionMode(QAbstractItemView.MultiSelection)   # a click toggles
        self.list.setMinimumSize(720, 260)
        self.list.setStyleSheet(
            "QListWidget { background: #202020; color: #ccc; }"
            "QListWidget::item { border: 3px solid transparent; border-radius: 4px; }"
            "QListWidget::item:selected { background: #1f4f99; color: white; border-color: #4d8df0; }")
        chosen = set(selected) | {current}
        for n in names:
            item = QListWidgetItem(icons.get(n, QIcon()), f"{roll.number(n)}  {Path(n).stem}")
            item.setData(Qt.UserRole, n)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.list.addItem(item)
            item.setSelected(n in chosen)
        self.list.itemSelectionChanged.connect(self._sync_checks)
        self.choose_box = QGroupBox()
        cl = QVBoxLayout(self.choose_box)
        cl.setContentsMargins(0, 0, 0, 0)
        hint = QLabel("Click frames to add or remove them.")
        hint.setStyleSheet("color: #999;")
        cl.addWidget(hint)
        cl.addWidget(self.list)
        row = QHBoxLayout()
        for text, on in (("Select all", True), ("Select none", False)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, on=on: self._select_all(on))
            row.addWidget(b)
        row.addStretch()
        cl.addLayout(row)
        gl.addWidget(self.choose_box)
        lay.addWidget(g)

        # Formats
        g = QGroupBox("Formats")
        gl = QVBoxLayout(g)
        row = QHBoxLayout()
        self.chk_fmt: dict[str, QCheckBox] = {}
        for fmt, (_suffix, label) in export.FORMATS.items():
            chk = QCheckBox(label, checked=fmt in roll.formats)
            chk.toggled.connect(self._update)
            self.chk_fmt[fmt] = chk
            row.addWidget(chk)
        row.addStretch()
        gl.addLayout(row)
        tip = QLabel("JPEG: for viewing and sharing.  TIFF 16-bit: best quality for archiving "
                     "and editing (large files).  TIFF 8-bit / PNG: lossless, smaller.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #999;")
        gl.addWidget(tip)
        self.chk_sheet = QCheckBox("Also make a contact sheet (one JPEG with all exported frames)",
                                   checked=roll.contact_sheet)
        self.chk_sheet.toggled.connect(self._update)
        gl.addWidget(self.chk_sheet)
        lay.addWidget(g)

        # Where
        g = QGroupBox("Save to")
        row = QHBoxLayout(g)
        self.txt_out = QLineEdit(str(roll.output_dir or roll.folder / "positives"))
        self.txt_out.textChanged.connect(self._update)
        b = QPushButton("Browse…")
        b.clicked.connect(self._browse)
        row.addWidget(self.txt_out)
        row.addWidget(b)
        lay.addWidget(g)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.btn_ok = self.buttons.button(QDialogButtonBox.Ok)
        self.btn_ok.setStyleSheet("font-weight: bold;")
        lay.addWidget(self.buttons)

        self.group.idToggled.connect(lambda *_: self._update())
        self.group.button(mode).setChecked(True)
        self._sync_checks()

    # --- results -------------------------------------------------------------
    def names(self) -> list[str]:
        mode = self.group.checkedId()
        if mode == CURRENT:
            return [self.current]
        if mode == ALL:
            return self.roll.names()
        picked = {i.data(Qt.UserRole) for i in self.list.selectedItems()}
        return [n for n in self.roll.names() if n in picked]

    def formats(self) -> list[str]:
        return [f for f, chk in self.chk_fmt.items() if chk.isChecked()]

    def contact_sheet(self) -> bool:
        return self.chk_sheet.isEnabled() and self.chk_sheet.isChecked()

    def output_dir(self) -> Path | None:
        text = self.txt_out.text().strip()
        return Path(text) if text else None

    # --- internals -----------------------------------------------------------
    def _select_all(self, on: bool):
        if on:
            self.list.selectAll()
        else:
            self.list.clearSelection()

    def _sync_checks(self):
        """Show a check mark on chosen frames (a click toggles the choice)."""
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setCheckState(Qt.Checked if item.isSelected() else Qt.Unchecked)
        self.list.blockSignals(False)
        self._update()

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Save to folder", self.txt_out.text())
        if d:
            self.txt_out.setText(d)

    def _update(self):
        choose = self.group.checkedId() == CHOOSE
        self.choose_box.setVisible(choose)
        n = len(self.names())
        self.chk_sheet.setEnabled(n > 1)
        ok = n > 0 and (self.formats() or self.contact_sheet()) and self.output_dir() is not None
        self.btn_ok.setEnabled(bool(ok))
        if self.formats():
            self.btn_ok.setText(f"Export {n} frame{'s' if n != 1 else ''}")
        else:
            self.btn_ok.setText("Make contact sheet")
        self.adjustSize()
