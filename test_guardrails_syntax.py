import ast
import os
import sys


def check_syntax(file_path):
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        ast.parse(content)
        print(f"Syntax of {file_path} is OK")
        return True
    except SyntaxError as e:
        print(f"Syntax error in {file_path}: {e}")
        return False
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return False


if __name__ == "__main__":
    file_to_check = os.path.join(os.path.dirname(__file__), "core", "guardrails.py")
    if check_syntax(file_to_check):
        sys.exit(0)
    else:
        sys.exit(1)
