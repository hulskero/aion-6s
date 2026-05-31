import os
import sys
import importlib
import importlib.util


def load_plugins(plugins_dir):
    plugins = {}
    if not os.path.isdir(plugins_dir):
        return plugins
    plugins_path = os.path.abspath(plugins_dir)
    if plugins_path not in sys.path:
        sys.path.insert(0, plugins_path)
    for f in sorted(os.listdir(plugins_path)):
        if not f.endswith(".py") or f.startswith("_"):
            continue
        name = f[:-3]
        path = os.path.join(plugins_path, f)
        try:
            if name in sys.modules:
                del sys.modules[name]
            spec = importlib.util.spec_from_file_location(name, path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "SKILL"):
                plugins[mod.SKILL["name"]] = mod.SKILL
        except Exception as e:
            print(f"  [ERR] plugin {name}: {e}")
    return plugins


def reload_plugins(plugins_dir):
    for mod_name in list(sys.modules.keys()):
        if "plugins." in mod_name or mod_name == "plugins":
            del sys.modules[mod_name]
    plugins_path = os.path.abspath(plugins_dir)
    for f in sorted(os.listdir(plugins_path)):
        if not f.endswith(".py") or f.startswith("_"):
            continue
        name = f[:-3]
        if name in sys.modules:
            del sys.modules[name]
    return load_plugins(plugins_dir)
