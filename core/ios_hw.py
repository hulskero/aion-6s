import ctypes
import platform
import plistlib
import re
import subprocess


_iokit = None
_cf = None
_CTYPES_READY = False

_str_tid = None
_num_tid = None
_dict_tid = None
_data_tid = None
_arr_tid = None
_bool_tid = None

_CFUTF8 = 0x08000100
_kCFNumberSInt32 = 3
_kCFNumberSInt64 = 4
_kCFNumberFloat32 = 12
_kCFNumberFloat64 = 13


def _load():
    global _iokit, _cf, _CTYPES_READY
    if _CTYPES_READY:
        return True
    try:
        _iokit = ctypes.cdll.LoadLibrary(
            '/System/Library/Frameworks/IOKit.framework/IOKit'
        )
        _cf = ctypes.cdll.LoadLibrary(
            '/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation'
        )
        _setup()
        _CTYPES_READY = True
        return True
    except Exception:
        _iokit = None
        _cf = None
        return False


def _setup():
    _iokit.IOServiceMatching.restype = ctypes.c_void_p
    _iokit.IOServiceMatching.argtypes = [ctypes.c_char_p]

    _iokit.IOServiceGetMatchingServices.restype = ctypes.c_int
    _iokit.IOServiceGetMatchingServices.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)
    ]

    _iokit.IOIteratorNext.restype = ctypes.c_uint32
    _iokit.IOIteratorNext.argtypes = [ctypes.c_uint32]

    _iokit.IOIteratorIsValid.restype = ctypes.c_bool
    _iokit.IOIteratorIsValid.argtypes = [ctypes.c_uint32]

    _iokit.IORegistryEntryCreateCFProperties.restype = ctypes.c_int
    _iokit.IORegistryEntryCreateCFProperties.argtypes = [
        ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p, ctypes.c_uint32
    ]

    _iokit.IOObjectRelease.restype = ctypes.c_int
    _iokit.IOObjectRelease.argtypes = [ctypes.c_uint32]

    _iokit.IOServiceGetMatchingService.restype = ctypes.c_uint32
    _iokit.IOServiceGetMatchingService.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p
    ]

    _cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    _cf.CFStringCreateWithCString.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32
    ]

    _cf.CFStringGetLength.restype = ctypes.c_long
    _cf.CFStringGetLength.argtypes = [ctypes.c_void_p]

    _cf.CFStringGetCString.restype = ctypes.c_bool
    _cf.CFStringGetCString.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32
    ]

    _cf.CFDictionaryGetCount.restype = ctypes.c_long
    _cf.CFDictionaryGetCount.argtypes = [ctypes.c_void_p]

    _cf.CFDictionaryGetKeysAndValues.restype = None
    _cf.CFDictionaryGetKeysAndValues.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
    ]

    _cf.CFDictionaryGetValue.restype = ctypes.c_void_p
    _cf.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

    _cf.CFNumberGetValue.restype = ctypes.c_bool
    _cf.CFNumberGetValue.argtypes = [
        ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p
    ]

    _cf.CFDataGetLength.restype = ctypes.c_long
    _cf.CFDataGetLength.argtypes = [ctypes.c_void_p]

    _cf.CFDataGetBytePtr.restype = ctypes.c_void_p
    _cf.CFDataGetBytePtr.argtypes = [ctypes.c_void_p]

    _cf.CFGetTypeID.restype = ctypes.c_ulong
    _cf.CFGetTypeID.argtypes = [ctypes.c_void_p]

    _cf.CFRelease.restype = None
    _cf.CFRelease.argtypes = [ctypes.c_void_p]

    _cf.CFArrayGetCount.restype = ctypes.c_long
    _cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]

    _cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
    _cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]

    global _str_tid, _num_tid, _dict_tid, _data_tid, _arr_tid, _bool_tid
    _str_tid = _cf.CFStringGetTypeID() if hasattr(_cf, 'CFStringGetTypeID') else 0
    _num_tid = _cf.CFNumberGetTypeID() if hasattr(_cf, 'CFNumberGetTypeID') else 0
    _dict_tid = _cf.CFDictionaryGetTypeID() if hasattr(_cf, 'CFDictionaryGetTypeID') else 0
    _data_tid = _cf.CFDataGetTypeID() if hasattr(_cf, 'CFDataGetTypeID') else 0
    _arr_tid = _cf.CFArrayGetTypeID() if hasattr(_cf, 'CFArrayGetTypeID') else 0

    try:
        _cf.CFBooleanGetTypeID.restype = ctypes.c_ulong
        _cf.CFBooleanGetTypeID.argtypes = []
        _cf.CFBooleanGetValue.restype = ctypes.c_bool
        _cf.CFBooleanGetValue.argtypes = [ctypes.c_void_p]
        _bool_tid = _cf.CFBooleanGetTypeID()
    except Exception:
        _bool_tid = 0


def _cfstr_to_py(cfstr):
    if not cfstr or not _cf:
        return None
    length = _cf.CFStringGetLength(cfstr) * 4 + 1
    buf = ctypes.create_string_buffer(length)
    if _cf.CFStringGetCString(cfstr, buf, length, _CFUTF8):
        return buf.value.decode('utf-8', errors='replace')
    return None


def _cfnum_to_py(cfnum):
    if not cfnum or not _cf:
        return None
    val = ctypes.c_double()
    if _cf.CFNumberGetValue(cfnum, _kCFNumberFloat64, ctypes.byref(val)):
        fv = val.value
        return int(fv) if fv == int(fv) and abs(fv) < 2**53 else fv
    iv = ctypes.c_long_long()
    if _cf.CFNumberGetValue(cfnum, _kCFNumberSInt64, ctypes.byref(iv)):
        return iv.value
    return None


def _cfdata_to_py(cfdata):
    if not cfdata or not _cf:
        return None
    length = _cf.CFDataGetLength(cfdata)
    ptr = _cf.CFDataGetBytePtr(cfdata)
    if ptr:
        return ctypes.string_at(ptr, length)
    return None


def _cfbool_to_py(cfbool):
    if not cfbool or not _cf or not _bool_tid:
        return None
    try:
        return bool(_cf.CFBooleanGetValue(cfbool))
    except Exception:
        return None


def _cfarr_to_py(cfarr):
    if not cfarr or not _cf or not _arr_tid:
        return []
    count = _cf.CFArrayGetCount(cfarr)
    return [_cfobj_to_py(_cf.CFArrayGetValueAtIndex(cfarr, i)) for i in range(count)]


def _cfobj_to_py(obj):
    if not obj or not _cf:
        return None
    tid = _cf.CFGetTypeID(obj)
    if _str_tid and tid == _str_tid:
        return _cfstr_to_py(obj)
    if _num_tid and tid == _num_tid:
        return _cfnum_to_py(obj)
    if _dict_tid and tid == _dict_tid:
        return _cfdict_to_py(obj)
    if _data_tid and tid == _data_tid:
        return _cfdata_to_py(obj)
    if _arr_tid and tid == _arr_tid:
        return _cfarr_to_py(obj)
    if _bool_tid and tid == _bool_tid:
        return _cfbool_to_py(obj)
    return None


def _cfdict_to_py(cfdict):
    if not cfdict or not _cf:
        return {}
    count = _cf.CFDictionaryGetCount(cfdict)
    if not count:
        return {}
    keys = (ctypes.c_void_p * count)()
    vals = (ctypes.c_void_p * count)()
    _cf.CFDictionaryGetKeysAndValues(cfdict, keys, vals)
    result = {}
    for i in range(count):
        k = _cfstr_to_py(keys[i])
        if k is not None:
            result[k] = _cfobj_to_py(vals[i])
    return result


def ioreg_get_properties(class_name):
    result = _ioreg_ctypes(class_name)
    if result is not None:
        return result
    return _ioreg_shell(class_name)


def ioreg_get_first(class_name):
    props = ioreg_get_properties(class_name)
    return props[0] if props else None


def ioreg_get_property(class_name, key):
    first = ioreg_get_first(class_name)
    if first:
        return first.get(key)
    return None


def _ioreg_ctypes(class_name):
    if not _load():
        return None
    try:
        matching = _iokit.IOServiceMatching(class_name.encode('utf-8'))
        if not matching:
            return None

        iterator = ctypes.c_uint32(0)
        kr = _iokit.IOServiceGetMatchingServices(
            None, matching, ctypes.byref(iterator)
        )
        if kr != 0 or not iterator.value:
            return None

        results = []
        while _iokit.IOIteratorIsValid(iterator):
            service = _iokit.IOIteratorNext(iterator)
            if not service:
                break

            props = ctypes.c_void_p()
            kr2 = _iokit.IORegistryEntryCreateCFProperties(
                service, ctypes.byref(props), None, 0
            )
            if kr2 == 0 and props.value:
                d = _cfdict_to_py(props.value)
                if d:
                    d['_service'] = service
                    results.append(d)
                _cf.CFRelease(props)

            _iokit.IOObjectRelease(service)

        _iokit.IOObjectRelease(iterator)
        for r in results:
            r.pop('_service', None)
        return results if results else None
    except Exception:
        return None


def _ioreg_shell(class_name):
    try:
        out = subprocess.check_output(
            ['ioreg', '-rc', class_name, '-w', '0'],
            stderr=subprocess.DEVNULL, timeout=5
        ).decode('utf-8', errors='replace')
    except Exception:
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
                except Exception:
                    props[key] = val.strip('"')
            elif val.startswith('<') and val.endswith('>'):
                try:
                    hexstr = val[1:-1].replace(' ', '')
                    props[key] = bytes.fromhex(hexstr)
                except Exception:
                    props[key] = val
            else:
                props[key] = val.rstrip(',').strip('"')
        if props:
            results.append(props)
    return results if results else None


def get_device_model():
    try:
        return platform.machine()
    except Exception:
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
