"""LocalConvert: GPL fork of Open Tangerine's real Windows desktop engine.

Keeps upstream workers, limits and rounded annular geometry. Replaces the main
batch window with a background tray and a persistent click-to-convert disk.
"""
import sys
import json
from pathlib import Path

if sys.platform == 'win32':
    # UIA rectangles and GetCursorPos must share physical pixel coordinates,
    # including the headless lookup subprocess (which never initializes Qt).
    import ctypes
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))


def restore_worker_streams():
    """Windowed PyInstaller clears sys.std*; inherit only explicit worker pipes."""
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
        return
    import ctypes
    import io
    import msvcrt
    import os
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetStdHandle.argtypes = [ctypes.c_ulong]
    kernel.GetStdHandle.restype = ctypes.c_void_p
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.DuplicateHandle.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p), ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    for name, number, mode in [('stdin', -10, 'rb'), ('stdout', -11, 'wb'), ('stderr', -12, 'wb')]:
        if getattr(sys, name) is not None:
            continue
        handle = kernel.GetStdHandle(number & 0xffffffff)
        duplicate = ctypes.c_void_p()
        process = kernel.GetCurrentProcess()
        if handle and handle != ctypes.c_void_p(-1).value and kernel.DuplicateHandle(process, handle, process, ctypes.byref(duplicate), 0, False, 2):
            fd = msvcrt.open_osfhandle(duplicate.value, os.O_BINARY | (os.O_RDONLY if name == 'stdin' else os.O_WRONLY))
            setattr(sys, name, io.TextIOWrapper(os.fdopen(fd, mode), encoding='utf-8', write_through=True))


# Headless subprocess routes must run before importing Qt or creating a tray.
if __name__ == '__main__' and '--worker' in sys.argv:
    restore_worker_streams()
    from engine import worker_main
    raise SystemExit(worker_main())
if __name__ == '__main__' and '--resolve-hover' in sys.argv:
    restore_worker_streams()
    try:
        from hover_resolver import resolve
        value = dict(ok=True, item=resolve(int(sys.argv[-2]), int(sys.argv[-1])))
    except Exception as error:
        value = dict(ok=False, error=str(error)[:400])
    print(json.dumps(value, ensure_ascii=True))
    raise SystemExit(0)

import os
import time
import ctypes
from ctypes import wintypes
from PySide6.QtCore import Qt, QPoint, QPointF, QRectF, QTimer, QProcess, QSettings, QMimeData, QUrl
from PySide6.QtGui import (QColor, QPainter, QPen, QLinearGradient, QFont, QCursor,
                           QIcon, QPixmap, QDesktopServices, QPainterPath)
from PySide6.QtWidgets import (QApplication, QWidget, QSystemTrayIcon, QMenu, QDialog,
    QFormLayout, QCheckBox, QComboBox, QSpinBox, QLineEdit, QPushButton, QFileDialog,
    QDialogButtonBox, QLabel, QInputDialog, QVBoxLayout)
from engine import IMAGE_INPUTS, IMAGE_OUTPUTS, source_file, open_image
from app import Batch
from glass_design import segment, point, target_at, format_label
from shift_tap import ShiftTap


class Disk(QWidget):
    """Actual annular paths; only the same painted path receives a click."""
    def __init__(self, host):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.host = host
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName('LocalConvert: menu radial. Setas escolhem; Enter executa; Escape fecha.')
        self.resize(420, 510)
        self.paths = []
        self.hover = -1
        self.category = 0
        self.formats = []

    def choices(self):
        image = all(Path(p).suffix.lower() in IMAGE_INPUTS for p in self.paths)
        if self.category == 0:
            # Only engines present in this package. No optional codecs advertised.
            if image:
                from PIL import features
                formats = ['PNG', 'WEBP', 'JPEG', 'TIFF', 'BMP', 'Image → PDF']
                return formats if features.check('webp') else [v for v in formats if v != 'WEBP']
            suffix = Path(self.paths[0]).suffix.lower() if self.paths else ''
            return {'.pdf': ['PDF → Text', 'Split PDF'], '.srt': ['SRT → VTT'],
                    '.vtt': ['VTT → SRT']}.get(suffix, [])
        if self.category == 1:
            return ['Redimensionar', 'Girar 90°', 'Comprimir', 'SHA-256'] if image else ['SHA-256']
        return ['Copiar arquivo', 'Copiar caminho', 'Mostrar origem', 'Fixar arquivo']

    def present(self, paths, position):
        self.paths = paths
        self.category = 0
        self.formats = self.choices()
        if not self.formats:
            self.category = 2
            self.formats = self.choices()
        self.hover = -1
        screen = QApplication.screenAt(position) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        self.move(max(area.left(), min(position.x()-210, area.right()-self.width()+1)),
                  max(area.top(), min(position.y()-290, area.bottom()-self.height()+1)))
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self.update()

    def category_to(self, index):
        self.category = index
        self.formats = self.choices()
        self.hover = -1
        self.update()

    def focusNextPrevChild(self, forward):
        self.category_to((self.category+(1 if forward else -1)) % 3)
        return True

    def sector(self, p):
        return target_at(QPointF(p.x()-20, p.y()-100), self.formats)

    def mouseMoveEvent(self, event):
        self.hover = self.sector(event.position())
        self.update()

    def leaveEvent(self, event):
        self.hover = -1
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.show_list()
            return
        if event.button() != Qt.LeftButton:
            return
        p = event.position()
        if 12 <= p.y() <= 47:
            self.category_to(max(0, min(2, int((p.x()-24)/124))))
            return
        index = self.sector(p)
        if index >= 0:
            self.execute(index)

    def execute(self, index):
        if 0 <= index < len(self.formats):
            target = self.formats[index]
            paths = list(self.paths)
            self.hide()
            self.host.execute(paths, target)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Escape:
            self.hide()
        elif key in (Qt.Key_Left, Qt.Key_Up, Qt.Key_Right, Qt.Key_Down):
            if self.formats:
                self.hover = (self.hover + (-1 if key in (Qt.Key_Left, Qt.Key_Up) else 1)) % len(self.formats)
                self.update()
        elif key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.execute(self.hover)
        elif key == Qt.Key_Tab:
            self.category_to((self.category+1) % 3)
        elif key == Qt.Key_F2:
            self.show_list()

    def show_list(self):
        menu = QMenu(self)
        for index, label in enumerate(self.formats):
            action = menu.addAction(format_label(label))
            action.triggered.connect(lambda checked=False, i=index: self.execute(i))
        menu.exec(self.mapToGlobal(QPoint(210, 290)))

    def focusOutEvent(self, event):
        # Windows outside clicks normally deactivate this tool window.
        QTimer.singleShot(0, lambda: self.hide() if not self.isActiveWindow() else None)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        dark = self.host.dark()
        fg = QColor('#f3f3f3' if dark else '#171a1b')
        muted = QColor('#c0c4c7' if dark else '#747f82')
        font = QFont('Segoe UI', 10)
        p.setFont(font)
        for i, label in enumerate(['Converter', 'Ferramentas', 'Ações']):
            rect = QRectF(24+i*124, 12, 120, 32)
            p.setBrush(QColor('#343638' if dark else '#f4f5f5'))
            p.setPen(QPen(QColor('#ff5a00') if i == self.category else QColor('#cdd1d2'), 1))
            p.drawRoundedRect(rect, 16, 16)
            p.setPen(fg)
            p.drawText(rect, Qt.AlignCenter, label)
        p.setPen(muted)
        p.drawText(QRectF(40, 60, 340, 24), Qt.AlignCenter, 'Shift  ·  '+Path(self.paths[0]).name[:40] if self.paths else 'LocalConvert')
        p.save()
        p.translate(20, 100)
        # Soft shadow, opaque shared rim, neutral materials and an orange wedge.
        for spread in range(9, 0, -1):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 2))
            p.drawEllipse(QRectF(8-spread, 10-spread, 364+2*spread, 364+2*spread))
        p.setBrush(QColor('#292d30' if dark else '#eceeef'))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(7, 7, 366, 366))
        for i, label in enumerate(self.formats):
            active = self.hover == i
            material = QLinearGradient(30, 0, 350, 375)
            material.setColorAt(0, QColor('#ff5a00') if active else QColor('#41474b' if dark else '#f6f7f7'))
            material.setColorAt(1, QColor('#ff5a00') if active else QColor('#292d30' if dark else '#e4e8e9'))
            p.setBrush(material)
            p.setPen(QPen(QColor('#ff5a00') if active else QColor('#535b60' if dark else '#cbd0d1'), 1))
            p.drawPath(segment(i, len(self.formats)))
            location = point(123, i*360/len(self.formats)-90)
            p.setPen(QColor('white') if active else fg)
            font.setBold(True)
            font.setPointSize(11 if self.category == 0 else 9)
            p.setFont(font)
            p.drawText(QRectF(location.x()-53, location.y()-27, 106, 54), Qt.AlignCenter | Qt.TextWordWrap, format_label(label))
        p.setBrush(QColor('#202427' if dark else '#fafbfb'))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(126, 126, 128, 128))
        p.setBrush(QColor('#363c40' if dark else 'white'))
        p.drawRoundedRect(QRectF(138, 169, 104, 42), 21, 21)
        value = self.formats[self.hover] if 0 <= self.hover < len(self.formats) else Path(self.paths[0]).suffix[1:].upper() if self.paths else ''
        font.setPointSize(10)
        font.setBold(False)
        p.setFont(font)
        p.setPen(fg)
        p.drawText(QRectF(139, 169, 102, 42), Qt.AlignCenter | Qt.TextWordWrap, format_label(value))
        p.restore()
        description = ('Converter para '+format_label(value)) if self.category == 0 and self.hover >= 0 else value if self.hover >= 0 else 'Escolha uma opção · Esc para fechar'
        p.setPen(muted)
        p.drawText(QRectF(20, 480, 380, 24), Qt.AlignCenter, description)


class Settings(QDialog):
    def __init__(self, host):
        super().__init__()
        self.setWindowTitle('LocalConvert · Configurações')
        self.setMinimumWidth(440)
        layout = QFormLayout(self)
        enabled = QCheckBox('Ativar hover + toque em Shift')
        enabled.setChecked(host.enabled)
        layout.addRow(enabled)
        theme = QComboBox()
        theme.addItems(['Sistema', 'Claro', 'Escuro'])
        theme.setCurrentText(host.settings.value('theme', 'Sistema'))
        layout.addRow('Aparência', theme)
        quality = QSpinBox()
        quality.setRange(1, 100)
        quality.setValue(int(host.settings.value('quality', 90)))
        layout.addRow('Qualidade JPEG / WebP', quality)
        folder = QLineEdit(host.settings.value('output', ''))
        folder.setPlaceholderText('Pasta original por padrão')
        layout.addRow('Pasta de saída', folder)
        choose = QPushButton('Escolher pasta…')
        choose.clicked.connect(lambda: folder.setText(QFileDialog.getExistingDirectory(self, 'Pasta de saída') or folder.text()))
        layout.addRow(choose)
        hint = QLabel('Tab alterna categorias; setas escolhem; Enter executa.\nF2 ou botão direito: lista acessível das operações.\nSem upload, telemetria ou início automático com Windows.\nAtalho secundário: Ctrl + Alt + Espaço (opcional).')
        layout.addRow(hint)
        alternate = QCheckBox('Ativar Ctrl + Alt + Espaço')
        alternate.setChecked(host.settings.value('alternate', False, type=bool))
        layout.addRow(alternate)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.rejected.connect(self.reject)
        def save():
            if folder.text() and not Path(folder.text()).is_dir():
                host.notify('Escolha uma pasta existente.', True)
                return
            host.settings.setValue('theme', theme.currentText())
            host.settings.setValue('quality', quality.value())
            host.settings.setValue('output', folder.text())
            host.settings.setValue('alternate', alternate.isChecked())
            host.set_enabled(enabled.isChecked())
            self.accept()
        buttons.accepted.connect(save)
        layout.addRow(buttons)


class Controller:
    def __init__(self):
        self.settings = QSettings('LocalConvert', 'OpenTangerineWindows')
        self.enabled = self.settings.value('enabled', True, type=bool)
        self.batch = None
        self.last_output = None
        self.gesture = ShiftTap()
        self.epoch = 0
        self.query_epoch = 0
        self.status = 'Aguardando Shift'
        self.disk = Disk(self)
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.user.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.user.GetAsyncKeyState.restype = ctypes.c_short
        self.user.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        self.lookup = QProcess()
        self.lookup.finished.connect(self.resolved)
        self.lookup_timer = QTimer()
        self.lookup_timer.setSingleShot(True)
        self.lookup_timer.timeout.connect(self.lookup.kill)
        self.timer = QTimer()
        self.timer.timeout.connect(self.poll)
        self.timer.start(16)
        self.mouse_was = False
        self.alt_was = False
        self.dialog = None
        self.shelves = []
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor('#ff5a00'))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 2, 28, 28)
        painter.setPen(QPen(QColor('white'), 2))
        painter.drawLine(10, 12, 22, 12)
        painter.drawLine(22, 12, 18, 8)
        painter.drawLine(22, 20, 10, 20)
        painter.drawLine(10, 20, 14, 24)
        painter.end()
        self.tray = QSystemTrayIcon(QIcon(pixmap))
        self.menu = QMenu()
        self.active_action = self.menu.addAction('Ativar hover + Shift')
        self.active_action.setCheckable(True)
        self.active_action.setChecked(self.enabled)
        self.active_action.toggled.connect(self.set_enabled)
        self.menu.addAction('Configurações…', self.show_settings)
        self.menu.addAction('Abrir pasta de saída', self.open_output)
        self.cancel_action = self.menu.addAction('Cancelar conversão', self.cancel)
        self.cancel_action.setEnabled(False)
        self.menu.addSeparator()
        self.menu.addAction('Encerrar', self.quit)
        self.tray.setContextMenu(self.menu)
        self.tray.setToolTip('LocalConvert · hover sobre arquivo + Shift')
        self.tray.activated.connect(lambda reason: self.show_settings() if reason == QSystemTrayIcon.DoubleClick else None)
        self.tray.show()

    def dark(self):
        theme = self.settings.value('theme', 'Sistema')
        return theme == 'Escuro' or (theme == 'Sistema' and QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark)

    def held(self, vk):
        return bool(self.user.GetAsyncKeyState(vk) & 0x8000)

    def position(self):
        point = wintypes.POINT()
        self.user.GetCursorPos(ctypes.byref(point))
        return point.x, point.y

    def set_enabled(self, value):
        self.enabled = bool(value)
        self.epoch += 1
        self.settings.setValue('enabled', self.enabled)
        self.gesture.reset()
        self.disk.hide()
        if self.active_action.isChecked() != self.enabled:
            self.active_action.setChecked(self.enabled)

    def poll(self):
        shift = self.held(0x10)
        mouse = any(self.held(vk) for vk in (1, 2, 4, 5, 6))
        if self.disk.isVisible():
            x, y = self.position()
            # Global Escape closes even if the overlay did not receive focus.
            if self.held(0x1b) or (mouse and not self.mouse_was and not self.disk.frameGeometry().contains(QCursor.pos())):
                self.disk.hide()
            self.mouse_was = mouse
            self.gesture.reset()
            return
        self.mouse_was = mouse
        if not self.enabled or (self.batch and self.batch.isRunning()) or (self.dialog and self.dialog.isVisible()):
            self.gesture.reset()
            return
        # Only instantaneous boolean states are checked, never recorded as text.
        conflict = mouse or any(self.held(vk) for vk in range(8, 255) if vk not in (0x10, 0xa0, 0xa1))
        if shift and self.gesture.started is None:
            self.epoch += 1
        if self.gesture.sample(shift, conflict, time.monotonic()):
            self.request_hover(*self.position())
        if conflict and self.lookup.state() != QProcess.NotRunning:
            self.epoch += 1
        alternate = self.settings.value('alternate', False, type=bool) and self.held(0x11) and self.held(0x12) and self.held(0x20) and not mouse
        if alternate and not self.alt_was:
            self.request_hover(*self.position())
        self.alt_was = alternate

    def request_hover(self, x, y):
        from hover_resolver import explorer_at
        if not explorer_at(x, y) or self.lookup.state() != QProcess.NotRunning:
            return
        self.query_epoch = self.epoch
        self.query_point = (x, y)
        self.status = 'Identificando arquivo sob o ponteiro'
        arguments = [] if getattr(sys, 'frozen', False) else [str(Path(__file__).resolve())]
        self.lookup.start(sys.executable, arguments + ['--resolve-hover', str(x), str(y)])
        self.lookup_timer.start(8000)

    def resolved(self, code, status):
        self.lookup_timer.stop()
        if not self.enabled or self.query_epoch != self.epoch:
            return
        try:
            result = json.loads(bytes(self.lookup.readAllStandardOutput()))
            if code != 0 or not result.get('ok'):
                self.status = result.get('error', 'Não foi possível identificar o arquivo.')
                self.tray.setToolTip('LocalConvert · '+self.status[:100])
                return
            item = result['item']
            x, y = self.position()
            l, t, r, b = item['bounds']
            if not l <= x < r or not t <= y < b:
                self.status = 'Ponteiro saiu do arquivo durante a identificação'
                return
            path = str(source_file(item['path']))
            # Resolver subprocess already decoded images; worker validates again.
            self.disk.present([path], QCursor.pos())
            self.status = 'Disco aberto para '+Path(path).name
        except Exception as error:
            self.status = str(error)[:180]
            self.notify(self.status, True)

    def notify(self, message, error=False):
        self.tray.showMessage('LocalConvert', message[:240], QSystemTrayIcon.Warning if error else QSystemTrayIcon.Information, 4000)

    def execute(self, paths, target):
        try:
            paths = [str(source_file(path)) for path in paths]
            if target == 'Copiar caminho':
                QApplication.clipboard().setText('\n'.join(paths))
                self.notify('Caminho copiado.')
                return
            if target == 'Copiar arquivo':
                mime = QMimeData()
                mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
                # Qt Windows maps local URLs to CF_HDROP for Explorer paste.
                mime.setData('Preferred DropEffect', (1).to_bytes(4, 'little'))
                QApplication.clipboard().setMimeData(mime)
                self.notify('Arquivo copiado. Cole no Explorador.')
                return
            if target == 'Mostrar origem':
                import win32com.shell.shell as shell
                shell.SHOpenFolderAndSelectItems(shell.SHILCreateFromPath(str(Path(paths[0]).parent), 0)[0],
                    [shell.SHILCreateFromPath(paths[0], 0)[0][-1:]], 0)
                return
            if target == 'Fixar arquivo':
                self.shelves.append(Shelf(paths[0]))
                return
            if self.batch and self.batch.isRunning():
                self.notify('Aguarde a conversão atual ou cancele pela bandeja.', True)
                return
            options = dict(output=self.settings.value('output', ''), quality=int(self.settings.value('quality', 90)), width=0, rotation=0)
            if target == 'Redimensionar':
                width, ok = QInputDialog.getInt(None, 'Redimensionar', 'Maior lado em pixels:', 1600, 1, 10000)
                if not ok:
                    return
                options['width'] = width
                target = 'PNG'
            elif target == 'Girar 90°':
                options['rotation'] = 90
                target = 'PNG'
            elif target == 'Comprimir':
                quality, ok = QInputDialog.getInt(None, 'Comprimir como JPEG', 'Qualidade (menor = arquivo menor). Transparência ficará branca.', 75, 1, 100)
                if not ok:
                    return
                options['quality'] = quality
                target = 'JPEG'
            self.errors = []
            self.outputs = []
            self.batch = Batch(paths, target, options)
            self.batch.result.connect(self.result)
            self.batch.finished.connect(self.finished)
            self.cancel_action.setEnabled(True)
            self.tray.setToolTip('LocalConvert · Convertendo…')
            self.batch.start()
        except Exception as error:
            self.notify(str(error), True)

    def result(self, index, status, outputs):
        self.outputs.extend(outputs)
        if status != 'Done':
            self.errors.append(status)

    def finished(self):
        self.cancel_action.setEnabled(False)
        if self.outputs:
            self.last_output = self.outputs[-1]
        self.notify(self.errors[0] if self.errors else f'{len(self.outputs)} arquivo(s) criado(s). Original preservado.', bool(self.errors))
        self.tray.setToolTip('LocalConvert · hover sobre arquivo + Shift')

    def show_settings(self):
        self.disk.hide()
        self.dialog = Settings(self)
        self.dialog.show()
        self.dialog.activateWindow()

    def open_output(self):
        folder = self.settings.value('output', '') or (str(Path(self.last_output).parent) if self.last_output else str(Path.home()/'Downloads'))
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def cancel(self):
        if self.batch:
            self.batch.cancel.set()

    def quit(self):
        self.enabled = False
        self.timer.stop()
        self.lookup_timer.stop()
        self.lookup.kill()
        self.disk.hide()
        self.cancel()
        if self.batch and self.batch.isRunning():
            QTimer.singleShot(100, self.quit)
            return
        self.tray.hide()
        QApplication.instance().quit()


class Shelf(QWidget):
    def __init__(self, path):
        super().__init__(None, Qt.Tool | Qt.WindowStaysOnTopHint)
        self.path = path
        self.setWindowTitle('Arquivo fixado · LocalConvert')
        layout = QVBoxLayout(self)
        image = QLabel()
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            image.setPixmap(pixmap.scaled(140, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            layout.addWidget(image)
        layout.addWidget(QLabel(Path(path).name))
        layout.addWidget(QLabel('Arraste para outro aplicativo'))
        self.show()

    def mousePressEvent(self, event):
        from PySide6.QtGui import QDrag
        if event.button() == Qt.LeftButton:
            drag = QDrag(self)
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(self.path)])
            drag.setMimeData(mime)
            drag.exec(Qt.CopyAction)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('LocalConvert')
    app.setQuitOnLastWindowClosed(False)
    # Explicit app identity keeps this fork separate from the original package.
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    socket = QLocalSocket()
    socket.connectToServer('LocalConvert.OpenTangerine.Windows')
    if socket.waitForConnected(250):
        socket.write(b'quit' if '--quit' in sys.argv else b'settings')
        socket.waitForBytesWritten(500)
        return 0
    if '--quit' in sys.argv:
        return 0
    server = QLocalServer()
    server.listen('LocalConvert.OpenTangerine.Windows')
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return 2
    host = Controller()
    def receive():
        client = server.nextPendingConnection()
        def read():
            command = bytes(client.readAll())
            if command == b'quit':
                host.quit()
            else:
                host.show_settings()
            client.disconnectFromServer()
        client.readyRead.connect(read)
        if client.bytesAvailable():
            read()
    server.newConnection.connect(receive)
    if '--settings' in sys.argv:
        host.show_settings()
    if '--self-test' in sys.argv:
        from windows_selftest import run
        QTimer.singleShot(500, lambda: run(host, sys.argv[sys.argv.index('--self-test')+1]))
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
