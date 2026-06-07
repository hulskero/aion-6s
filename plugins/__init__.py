import os
import sys
import importlib
import importlib.util
import ast


def _extract_skill_info(path):
    """Extract SKILL name and description from plugin file without executing it."""
    try:
        with open(path, "r") as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "SKILL":
                        if isinstance(node.value, ast.Dict):
                            skill = {}
                            for k, v in zip(node.value.keys, node.value.values):
                                if isinstance(k, ast.Constant):
                                    key = k.value
                                    if isinstance(v, ast.Constant):
                                        skill[key] = v.value
                                    elif key == "run":
                                        continue
                            if "name" in skill and "description" in skill:
                                return skill["name"], skill["description"]
    except Exception:
        pass
    return None, None


def load_plugins(plugins_dir, lazy=True):
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
            if lazy:
                skill_name, description = _extract_skill_info(path)
                if skill_name and description:
                    plugins[skill_name] = {
                        "name": skill_name,
                        "description": description,
                        "path": path,
                        "_lazy": True,
                    }
                continue
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


def _load_plugin_module(plugin_info):
    """Load a plugin module from its path and return the run function."""
    path = plugin_info["path"]
    name = os.path.basename(path)[:-3]
    if name in sys.modules:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if hasattr(mod, "SKILL") and callable(mod.SKILL.get("run")):
        return mod.SKILL["run"]
    raise RuntimeError(f"Plugin {name}: SKILL['run'] not callable")


def reload_plugins(plugins_dir):
    plugin_keys = [k for k in sys.modules if k.startswith("plugins.") or k == "plugins"]
    for k in plugin_keys:
        del sys.modules[k]
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
    return load_plugins(plugins_dir, lazy=True)


def install_plugin(name, url, plugins_dir):
    import urllib.request
    import urllib.error

    safe_name = os.path.basename(name)
    if not safe_name.endswith(".py"):
        safe_name += ".py"
    dest = os.path.join(plugins_dir, safe_name)
    real_dest = os.path.realpath(dest)
    real_plugins = os.path.realpath(plugins_dir)
    if not real_dest.startswith(real_plugins + os.sep) and real_dest != real_plugins:
        return None, f"Invalid plugin name: '{name}'"
    if os.path.exists(dest):
        return None, f"Plugin '{safe_name}' already exists."
    try:
        urllib.request.urlretrieve(url, dest)
    except urllib.error.URLError as e:
        return None, f"Download failed: {e}"
    except Exception as e:
        return None, f"Error: {e}"
    plugins = load_plugins(plugins_dir, lazy=True)
    plugin_name = name[:-3]
    if plugin_name in plugins:
        return plugins[plugin_name], None
    return None, "File saved but no valid SKILL found."


def remove_plugin(name, plugins_dir):
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