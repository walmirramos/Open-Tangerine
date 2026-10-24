"""Build the actual GPL-derived background Windows executable (no console)."""
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
# Generate the UIA typelib ahead of PyInstaller analysis.
import comtypes.client
comtypes.client.GetModule('UIAutomationCore.dll')
from PyInstaller.utils.hooks import collect_submodules
hidden = [value for module in collect_submodules('comtypes', filter=lambda name: '.test' not in name and '.tools' not in name)
          for value in ('--hidden-import', module)]
# Do not let developer tools (for example Poppler/Conda) inject an incompatible
# ICU DLL ahead of Windows' own ICU, which is used by this Qt distribution.
environment = dict(os.environ)
windows = Path(os.environ.get('SystemRoot', r'C:\Windows'))
environment['PATH'] = os.pathsep.join(map(str, [Path(sys.executable).parent, Path(sys.base_prefix), windows/'System32', windows]))
subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed',
    '--onedir', '--name', 'LocalConvert', '--collect-all', 'pypdf', *hidden,
    '--hidden-import', 'comtypes.gen.UIAutomationClient', '--hidden-import', 'win32com.shell.shell',
    '--hidden-import', 'win32com.client', '--hidden-import', 'windows_selftest',
    '--distpath', str(root.parent/'Aplicativo'), '--workpath', str(root/'build'),
    '--specpath', str(root), str(root/'windows_main.py')], cwd=root, env=environment, check=True)
dest = root.parent/'Aplicativo/LocalConvert'
source = dest/'source/Desktop'
source.mkdir(parents=True, exist_ok=True)
for file in root.glob('*.py'):
    shutil.copyfile(file, source/file.name)
for name in ['requirements.txt', 'README.md']:
    shutil.copyfile(root/name, source/name)
shutil.copytree(root/'tests', source/'tests', ignore=shutil.ignore_patterns('__pycache__'), dirs_exist_ok=True)
for name in ['LICENSE', 'NOTICE', 'THIRD_PARTY_NOTICES.md']:
    shutil.copyfile(root.parent/name, dest/name)
    shutil.copyfile(root.parent/name, source.parent/name)
shutil.copyfile(root.parent/'WINDOWS-LEIA-ME.md', dest/'LEIA-ME.md')
shutil.copyfile(root.parent/'WINDOWS-LEIA-ME.md', source.parent/'WINDOWS-LEIA-ME.md')
versions = {name: importlib.metadata.version(name) for name in ['Pillow', 'pypdf', 'PySide6-Essentials', 'shiboken6', 'comtypes', 'pywin32', 'pyinstaller']}
(dest/'dependencies.json').write_text(json.dumps(dict(python=sys.version, packages=versions), indent=2), encoding='utf8')
licenses = dest/'licenses'
licenses.mkdir(exist_ok=True)
shutil.copytree(root/'licenses', licenses/'upstream', dirs_exist_ok=True)
for name in versions:
    distribution = importlib.metadata.distribution(name)
    for file in distribution.files or []:
        if any(value in str(file).lower() for value in ('license', 'copying', 'copyright')):
            original = Path(distribution.locate_file(file))
            if original.is_file():
                target = licenses/name/str(file).replace('..', '_')
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original, target)
print(dest)
