"""Unit tests for cli_utils.py — safe_input function."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import sys
from pathlib import Path

# Make 'cli' package importable from any working directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# safe_input
# ---------------------------------------------------------------------------

class TestSafeInput:
    """Input handling with UTF-8 encoding recovery."""

    def test_returns_stripped_newline_only(self):
        from cli_utils import safe_input

        with patch("cli_utils.input", return_value="  hello  \n"):
            result = safe_input("> ")
        assert result == "  hello  "

    def test_handles_unicode_decode_error(self):
        from cli_utils import safe_input

        call_count = [0]

        def broken_input(prompt):
            call_count[0] += 1
            if call_count[0] == 1:
                raise UnicodeDecodeError("utf-8", b"", 0, 1, "mock error")
            return "recovered"

        with patch("cli_utils.input", side_effect=broken_input):
            result = safe_input("> ")
        assert result == "recovered"
        assert call_count[0] == 2

    def test_handles_eof(self):
        from cli_utils import safe_input

        with patch("cli_utils.input", side_effect=EOFError()):
            result = safe_input("> ")
        assert result == ""

    def test_reconfigure_raises_no_error(self):
        """When stdin.reconfigure raises AttributeError, should continue."""
        from cli_utils import safe_input

        mock_stdin = MagicMock()
        mock_stdin.reconfigure.side_effect = AttributeError("no attribute")

        with patch("cli_utils.sys.stdin", mock_stdin), \
             patch("cli_utils.input", return_value="test"):
            result = safe_input("> ")
        assert result == "test"

    def test_normal_input(self):
        from cli_utils import safe_input

        with patch("cli_utils.input", return_value="normal input"):
            result = safe_input("Enter: ")
        assert result == "normal input"

    def test_empty_string_input(self):
        from cli_utils import safe_input

        with patch("cli_utils.input", return_value=""):
            result = safe_input("> ")
        assert result == ""

    def test_whitespace_only_input(self):
        from cli_utils import safe_input

        with patch("cli_utils.input", return_value="   "):
            result = safe_input("> ")
        assert result == "   "
