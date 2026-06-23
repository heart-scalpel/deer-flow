"""
DeerFlow CLI Utilities

Shared utility functions for CLI modules.
"""

import sys


def safe_input(prompt):
    """
    Safely read input with UTF-8 encoding.

    Handles encoding errors and EOF gracefully.

    Args:
        prompt: The input prompt to display.

    Returns:
        str: The input line, stripped of trailing newline.
    """
    try:
        sys.stdin.reconfigure(encoding='utf-8')
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
    while True:
        try:
            return input(prompt).rstrip('\n')
        except UnicodeDecodeError:
            print("\n[Error] Input encoding error. Please use UTF-8. | 输入编码错误，请使用UTF-8\n")
        except EOFError:
            return ""
