"""Authoritative Explorer hover lookup. No selection fallback and no OCR.

UIA identifies a visible file-view item, Shell.Application supplies the actual path.
Runs in a disposable STA process so an unresponsive provider cannot freeze Qt.
GPL-3.0-only, derived project: Open Tangerine / LocalConvert Windows.
"""
import ctypes
from ctypes import wintypes
from pathlib import Path


def explorer_at(x, y):
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.WindowFromPoint.argtypes = [wintypes.POINT]
    user.WindowFromPoint.restype = wintypes.HWND
    user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user.GetAncestor.restype = wintypes.HWND
    user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    hwnd = user.GetAncestor(user.WindowFromPoint(wintypes.POINT(x, y)), 2)
    name = ctypes.create_unicode_buffer(256)
    user.GetClassNameW(hwnd, name, 256)
    return int(hwnd or 0) if name.value in ('CabinetWClass', 'ExploreWClass') else 0


def unique_shell_path(items, label):
    """Compare Shell names, never construct a filesystem path from a UI label."""
    from engine import source_file
    candidates = set()
    for item in items:
        if item.IsFolder:
            continue
        raw = str(item.Path)
        if str(item.Name) == label or Path(raw).name == label:
            try:
                candidates.add(str(source_file(raw)))
            except (OSError, ValueError):
                pass
    if len(candidates) != 1:
        raise ValueError('Item sem caminho local único; nenhuma conversão oferecida.')
    return candidates.pop()


def resolve(x, y):
    import comtypes
    import comtypes.client
    import win32com.client
    from engine import source_file
    hwnd = explorer_at(x, y)
    if not hwnd:
        raise ValueError('O ponteiro não está em uma pasta comum do Explorador.')
    comtypes.CoInitialize()
    try:
        comtypes.client.GetModule('UIAutomationCore.dll')
        from comtypes.gen import UIAutomationClient as UIA
        automation = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
        element = automation.ElementFromPoint(wintypes.POINT(x, y))
        walker = automation.ControlViewWalker
        # Explorer labels can be Text or Edit. Walk to the real ListItem, not focus.
        for _ in range(14):
            if not element:
                break
            if element.CurrentControlType == 50007:
                break
            element = walker.GetParentElement(element)
        if not element or element.CurrentControlType != 50007:
            # ItemsView may return its container over the whitespace inside an
            # icon tile. Use that same Explorer's unique visible ListItem bounds,
            # never focused/selected items. Empty view space has zero matches.
            condition = automation.CreatePropertyCondition(30003, 50007)
            visible = automation.ElementFromHandle(hwnd).FindAll(4, condition)
            matches = []
            for index in range(visible.Length):
                candidate = visible.GetElement(index)
                rect = candidate.CurrentBoundingRectangle
                if not candidate.CurrentIsOffscreen and rect.left <= x < rect.right and rect.top <= y < rect.bottom:
                    matches.append(candidate)
            if len(matches) != 1:
                raise ValueError('Nenhum arquivo único sob o ponteiro.')
            element = matches[0]
        rect = element.CurrentBoundingRectangle
        bounds = [int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)]
        if not (bounds[0] <= x < bounds[2] and bounds[1] <= y < bounds[3]):
            raise ValueError('O ponteiro não pertence ao item encontrado.')
        label = element.CurrentName
        ancestor = walker.GetParentElement(element)
        file_view = False
        for _ in range(14):
            if not ancestor:
                break
            if ancestor.CurrentClassName in ('UIItemsView', 'SysListView32'):
                file_view = True
                break
            ancestor = walker.GetParentElement(ancestor)
        if not file_view:
            raise ValueError('Item fora da lista de arquivos; navegação lateral ignorada.')
        shell = win32com.client.Dispatch('Shell.Application')
        folder = None
        for window in shell.Windows():
            try:
                if int(window.HWND) == hwnd:
                    folder = window.Document.Folder
                    break
            except Exception:
                continue
        if folder is None:
            raise ValueError('Pasta do Explorador indisponível.')
        # ParseName returns a Shell FolderItem, not a concatenated path. Confirm
        # full name before accepting; hidden extensions use unique enumeration.
        candidate = folder.ParseName(label)
        if candidate is not None and not candidate.IsFolder and Path(str(candidate.Path)).name == label:
            path = str(source_file(str(candidate.Path)))
        else:
            path = unique_shell_path(folder.Items(), label)
        if explorer_at(x, y) != hwnd:
            raise ValueError('A janela mudou durante a identificação.')
        from engine import IMAGE_INPUTS, open_image
        if Path(path).suffix.lower() in IMAGE_INPUTS:
            with open_image(Path(path)):
                pass  # Decode and enforce pixel/frame limits before offering conversions.
        return dict(path=path, name=Path(path).name, bounds=bounds, hwnd=hwnd)
    finally:
        comtypes.CoUninitialize()
