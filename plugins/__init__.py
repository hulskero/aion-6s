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
                SKILL = mod.SKILL
                if not isinstance(SKILL, dict):
                    print(f"  [ERR] plugin {f}: SKILL must be a dict, got {type(SKILL).__name__}")
                    continue
                required_keys = {"name", "description", "run"}
                missing = required_keys - set(SKILL.keys())
                if missing:
                    print(f"  [ERR] plugin {f}: SKILL missing: {missing}")
                    continue
                if not callable(SKILL.get("run")):
                    print(f"  [ERR] plugin {f}: SKILL['run'] must be callable")
                    continue
                plugins[SKILL["name"]] = SKILL
        except Exception as e:
            print(f"  [ERR] plugin {name}: {e}")
    return plugins


def reload_plugins(plugins_dir):
    # Nuke all plugin modules and their imported dependencies
    plugin_keys = [k for k in sys.modules if k.startswith("plugins.") or k == "plugins"]
    for k in plugin_keys:
        del sys.modules[k]
    # Also clear any modules that plugins import from core/
    for name in list(sys.modules):
        if name.startswith("core."):
            del sys.modules[name]
    plugins_path = os.path.abspath(plugins_dir)
    for f in sorted(os.listdir(plugins_path)):
        if not f.endswith(".py") or f.startswith("_"):
            continue
        name = f[:-3]
        if name in sys.modules:
            del sys.modules[name]
    return load_plugins(plugins_dir)


def install_plugin(name, url, plugins_dir):
    """Download a .py plugin from URL, save to plugins_dir, load it."""
    import urllib.request
    import urllib.error

    if not name.endswith(".py"):
        name += ".py"
    dest = os.path.join(plugins_dir, name)
    if os.path.exists(dest):
        return None, f"Plugin '{name}' already exists."
    try:
        urllib.request.urlretrieve(url, dest)
    except urllib.error.URLError as e:
        return None, f"Download failed: {e}"
    except Exception as e:
        return None, f"Error: {e}"
    plugins = load_plugins(plugins_dir)
    plugin_name = name[:-3]
    if plugin_name in plugins:
        return plugins[plugin_name], None
    return None, "File saved but no valid SKILL found."


def remove_plugin(name, plugins_dir):
    """Remove a plugin from disk and memory."""
    if not name.endswith(".py"):
        name += ".py"
    path = os.path.join(plugins_dir, name)
    if not os.path.exists(path):
        return False, f"Plugin '{name}' not found."
    os.remove(path)
    mod_name = name[:-3]
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return True, None
