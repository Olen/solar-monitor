import os
import platform

if platform.system() == 'Linux':
    if os.environ.get('LINUX_WITHOUT_DBUS', '0') == '0':
        from .gatt_linux import *
    else:
        from .gatt_stubs import *
else:
    from .gatt_stubs import *
