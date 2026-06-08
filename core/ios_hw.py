import platform
import plistlib
import re
import subprocess


def ioreg_get_properties(class_name):
    """Get IORegistry properties via ioreg CLI"""
    return _ioreg_shell(class_name)


def ioreg_get_first(class_name):
    props = ioreg_get_properties(class_name)
    return props[0] if props else None


def ioreg_get_property(class_name, key):
    first = ioreg_get_first(class_name)
    if first:
        return first.get(key)
    return None


def _ioreg_shell(class_name):
    try:
        out = subprocess.check_output(
            ['ioreg', '-rc', class_name, '-w', '0'],
            stderr=subprocess.DEVNULL, timeout=5
        ).decode('utf-8', errors='replace')
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None

    entries = re.split(r'\+-o ', out)
    results = []
    for entry in entries:
        if not entry.strip():
            continue
        props = {}
        for line in entry.split('\n'):
            line = line.strip()
            if ' = ' not in line:
                continue
            key, _, val = line.partition(' = ')
            key = key.strip('"')
            if val.startswith('{') or val.startswith('"'):
                try:
                    parsed = plistlib.loads(val.encode('utf-8'))
                    props[key] = parsed
                except (ValueError, plistlib.InvalidFileException, TypeError):
                    props[key] = val.strip('"')
            elif val.startswith('<') and val.endswith('>'):
                try:
                    hexstr = val[1:-1].replace(' ', '')
                    props[key] = bytes.fromhex(hexstr)
                except ValueError:
                    props[key] = val
            else:
                props[key] = val.rstrip(',').strip('"')
        if props:
            results.append(props)
    return results if results else None


def get_device_model():
    try:
        return platform.machine()
    except (OSError, AttributeError):
        return 'unknown'


DEVICE_SPECS = {
    'iPhone8,1': {'w': 750, 'h': 1334, 'ppi': 326, 'scale': 2, 'name': 'iPhone 6s'},
    'iPhone8,2': {'w': 1080, 'h': 1920, 'ppi': 401, 'scale': 3, 'name': 'iPhone 6s Plus'},
    'iPhone8,4': {'w': 640, 'h': 1136, 'ppi': 326, 'scale': 2, 'name': 'iPhone SE'},
    'iPhone9,1': {'w': 750, 'h': 1334, 'ppi': 326, 'scale': 2, 'name': 'iPhone 7'},
    'iPhone9,2': {'w': 1080, 'h': 1920, 'ppi': 401, 'scale': 3, 'name': 'iPhone 7 Plus'},
    'iPhone9,3': {'w': 750, 'h': 1334, 'ppi': 326, 'scale': 2, 'name': 'iPhone 7'},
    'iPhone9,4': {'w': 1080, 'h': 1920, 'ppi': 401, 'scale': 3, 'name': 'iPhone 7 Plus'},
    'iPhone10,1': {'w': 750, 'h': 1334, 'ppi': 326, 'scale': 2, 'name': 'iPhone 8'},
    'iPhone10,2': {'w': 1080, 'h': 1920, 'ppi': 401, 'scale': 3, 'name': 'iPhone 8 Plus'},
    'iPhone10,3': {'w': 1125, 'h': 2436, 'ppi': 458, 'scale': 3, 'name': 'iPhone X'},
    'iPhone10,4': {'w': 750, 'h': 1334, 'ppi': 326, 'scale': 2, 'name': 'iPhone 8'},
    'iPhone10,5': {'w': 1080, 'h': 1920, 'ppi': 401, 'scale': 3, 'name': 'iPhone 8 Plus'},
    'iPhone10,6': {'w': 1125, 'h': 2436, 'ppi': 458, 'scale': 3, 'name': 'iPhone X'},
}


def get_display_specs(model=None):
    if model is None:
        model = get_device_model()
    return DEVICE_SPECS.get(model)
