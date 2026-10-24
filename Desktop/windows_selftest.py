"""Explicit local integration test. Uses own fixtures and real Explorer/Shell.

No hardware input claim: coordinates, Shift samples and sector clicks are supplied
by this test. The Explorer, resolver subprocess, Qt overlay and worker are real.
"""
import ctypes
import hashlib
import json
import sys
import time
from pathlib import Path
from PySide6.QtCore import QTimer, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtCore import QEvent


def run(host, root):
    import uuid
    from PIL import Image
    from shift_tap import ShiftTap
    root = Path(root).resolve()/('execucao-'+uuid.uuid4().hex[:8])
    root.mkdir(parents=True)
    checks = []
    def check(value, name):
        if not value:
            raise AssertionError(name)
        checks.append(name)
    def fail(error):
        (root/'resultado.json').write_text(json.dumps(dict(passed=False, checks=checks, error=str(error)), ensure_ascii=False, indent=2), encoding='utf8')
        print('FAIL', error, root, flush=True)
        host.quit()
    try:
        # Test isolation: no persisted preference changes and no physical input.
        host.timer.stop()
        a, b = root/'A selecionado.jpg', root/'B sob ponteiro ç.jpg'
        Image.new('RGB', (48, 32), 'crimson').save(a)
        Image.new('RGB', (48, 32), 'royalblue').save(b)
        hashes = {p: hashlib.sha256(p.read_bytes()).digest() for p in (a, b)}
        gesture = ShiftTap()
        check(not gesture.sample(True, False, 10), 'Shift pressionado não abre')
        check(gesture.sample(False, False, 14.828), 'Shift isolado de 4828 ms aceito')
        gesture.sample(True, False, 20)
        gesture.sample(True, True, 20.1)
        check(not gesture.sample(False, False, 20.2), 'Combinação cancela ativação')
        import win32com.client
        import win32com.shell.shell as shell
        folder = shell.SHILCreateFromPath(str(root), 0)[0]
        file = shell.SHILCreateFromPath(str(a), 0)[0]
        shell.SHOpenFolderAndSelectItems(folder, [file[-1:]], 0)
        state = dict(attempt=0)
        def inspect():
            try:
                state['attempt'] += 1
                view = None
                for w in win32com.client.Dispatch('Shell.Application').Windows():
                    try:
                        if str(w.Document.Folder.Self.Path).casefold() == str(root).casefold():
                            view = w
                            break
                    except Exception:
                        pass
                if view is None:
                    if state['attempt'] < 30:
                        QTimer.singleShot(300, inspect)
                        return
                    raise AssertionError('Pasta de teste não abriu no Explorador')
                selected = [str(item.Path) for item in view.Document.SelectedItems()]
                if str(a) not in selected or str(b) in selected:
                    if state['attempt'] < 30:
                        QTimer.singleShot(300, inspect)
                        return
                    raise AssertionError('Seleção de A não confirmou no Explorador')
                import comtypes.client
                comtypes.client.GetModule('UIAutomationCore.dll')
                from comtypes.gen import UIAutomationClient as U
                automation = comtypes.client.CreateObject(U.CUIAutomation, interface=U.IUIAutomation)
                condition = automation.CreatePropertyCondition(30003, 50007)
                elements = automation.ElementFromHandle(int(view.HWND)).FindAll(4, condition)
                target = None
                for n in range(elements.Length):
                    element = elements.GetElement(n)
                    if element.CurrentName in (b.name, b.stem):
                        target = element
                        break
                if target is None:
                    if state['attempt'] < 30:
                        QTimer.singleShot(300, inspect)
                        return
                    raise AssertionError('B não localizado no painel de arquivos real')
                check(str(a) in selected and str(b) not in selected, 'A selecionado; B não selecionado no Explorador real')
                rect = target.CurrentBoundingRectangle
                x, y = (rect.left+rect.right)//2, (rect.top+rect.bottom)//2
                state.update(x=x, y=y)
                from PySide6.QtCore import QProcess
                query = QProcess()
                host.test_query = query
                args = [] if getattr(sys, 'frozen', False) else [str(Path(__file__).with_name('windows_main.py'))]
                def resolved(code, status):
                    try:
                        result = json.loads(bytes(query.readAllStandardOutput()))
                        (root/'resolvedor.json').write_text(json.dumps(dict(result=result, x=x, y=y), ensure_ascii=False, indent=2), encoding='utf8')
                        check(code == 0 and result.get('ok') and Path(result['item']['path']) == b, 'UIA + Shell real resolve B; seleção de A ignorada')
                        host.disk.present([str(b)], QPoint(x, y))
                        QTimer.singleShot(150, click)
                    except Exception as error:
                        fail(error)
                query.finished.connect(resolved)
                query.start(sys.executable, args+['--resolve-hover', str(x), str(y)])
                QTimer.singleShot(12000, lambda: query.kill() if query.state() != QProcess.NotRunning else None)
            except Exception as error:
                fail(error)
        def click():
            try:
                disk = host.disk
                user = ctypes.WinDLL('user32')
                user.IsWindowVisible.argtypes = [ctypes.c_void_p]
                check(bool(user.IsWindowVisible(int(disk.winId()))), 'Overlay Qt visível como janela nativa')
                check(disk.sector(QPointF(210, 167)) == 0, 'Hit testing aponta PNG')
                check(disk.sector(QPointF(210, 290)) == -1, 'Centro não executa conversão')
                disk.hover = 0
                disk.grab().save(str(root/'disco-real.png'))
                event = QMouseEvent(QEvent.MouseButtonPress, QPointF(210, 167), QPointF(210, 167), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
                disk.mousePressEvent(event)
                check(not disk.isVisible(), 'Clique no setor fecha disco')
                state['deadline'] = time.monotonic()+25
                wait_output()
            except Exception as error:
                fail(error)
        def wait_output():
            try:
                if host.batch and host.batch.isRunning():
                    if time.monotonic() > state['deadline']:
                        raise TimeoutError('Worker não terminou')
                    QTimer.singleShot(100, wait_output)
                    return
                # Deliver queued result/finished slots before reading outputs.
                if not getattr(host, 'outputs', []) and time.monotonic() < state['deadline']:
                    QTimer.singleShot(100, wait_output)
                    return
                check(bool(host.outputs) and not host.errors, 'Worker original do Open Tangerine converte de verdade')
                output = Path(host.outputs[-1])
                with Image.open(output) as image:
                    image.load()
                    pixel = image.getpixel((10, 10))
                    check(image.format == 'PNG' and pixel[2] > pixel[0]+50, 'PNG válido com pixels de B')
                check(all(hashlib.sha256(p.read_bytes()).digest() == digest for p, digest in hashes.items()), 'Originais A/B preservados por SHA-256')
                report = dict(passed=True, checks=checks, output=str(output), simulated=['amostras Shift', 'ponto do ponteiro', 'clique Qt'], real=['Explorador/seleção', 'UIA e Shell', 'overlay nativo', 'Batch/runner/engine herdados', 'arquivo convertido'], not_validated='Gesto físico global e múltiplos monitores não validados por este teste.')
                (root/'resultado.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
                print('PASS', len(checks), root, flush=True)
                host.quit()
            except Exception as error:
                fail(error)
        QTimer.singleShot(1000, inspect)
    except Exception as error:
        fail(error)
