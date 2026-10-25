"""参考文件的受限临时存储与本机打开；不接受命令或任意磁盘路径。"""
import atexit
import base64
import binascii
import os
from pathlib import Path
import re
import subprocess
import tempfile

MAX_BYTES = 50 * 1024 * 1024
DATA_URI = re.compile(r'data:([A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+);base64,([A-Za-z0-9+/]*={0,2})')
_STORE = tempfile.TemporaryDirectory(prefix='diagnostic-reference-')
atexit.register(_STORE.cleanup)
# 可执行、脚本和快捷方式仅进入系统软件选择器，避免把参考资料当作程序运行。
CHOOSER_EXTENSIONS = {'.exe', '.com', '.bat', '.cmd', '.ps1', '.psm1', '.vbs', '.vbe', '.js',
    '.jse', '.wsf', '.wsh', '.msi', '.msp', '.scr', '.pif', '.lnk', '.url', '.py', '.pyw',
    '.reg', '.hta', '.cpl', '.msc', '.application', '.appref-ms', '.jar', '.sh'}


def parse_reference_file(value):
    match = DATA_URI.fullmatch(value) if isinstance(value, str) else None
    if not match or len(match[2]) > ((MAX_BYTES + 2) // 3) * 4:
        raise ValueError('Invalid reference file data URI or file exceeds 50 MB')
    try:
        payload = base64.b64decode(match[2], validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError('Invalid reference file Base64') from error
    if len(payload) > MAX_BYTES or base64.b64encode(payload).decode('ascii') != match[2]:
        raise ValueError('Invalid reference file Base64 or file exceeds 50 MB')
    return match[1].lower(), payload


def choose_application(path):
    # 使用系统目录和参数数组，不拼接 shell 命令，不依赖 PATH 查找可执行文件。
    system = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32'
    subprocess.Popen([str(system / 'rundll32.exe'), str(system / 'shell32.dll') + ',OpenAs_RunDLL', str(path)], shell=False)


def launch_reference(path):
    if os.name != 'nt':
        raise RuntimeError('Opening reference files with local applications requires Windows')
    if path.suffix.lower() in CHOOSER_EXTENSIONS:
        choose_application(path)
        return 'chooser'
    try:
        os.startfile(str(path), 'open')
        return 'default'
    except OSError as error:
        if getattr(error, 'winerror', None) not in (1155, 31):
            raise
        choose_application(path)
        return 'chooser'


def open_reference_file(data):
    _, payload = parse_reference_file(data.get('dataUri'))
    name = data.get('name') or 'reference.bin'
    if not isinstance(name, str) or len(name) > 180 or re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or name in ('.', '..') or name.endswith((' ', '.')):
        raise ValueError('Invalid reference file name')
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        raise ValueError('Reserved reference file name')
    # 每次请求独立目录，防止同名覆盖及仍在外部程序读取时被删除。
    directory = Path(tempfile.mkdtemp(dir=_STORE.name))
    path = directory / name
    path.write_bytes(payload)
    return {'ok': True, 'openedWith': launch_reference(path)}
