"""Tests for the agent_cli.py terminal REPL loop -- exit commands, blank
lines, message routing, and graceful interrupt handling. builtins.input
is mocked throughout; nothing here reads real stdin.
"""
from unittest.mock import patch

import agent_cli


def _run_with_inputs(inputs):
    with patch("builtins.input", side_effect=inputs):
        agent_cli.main()


def test_exit_command_stops_loop_and_prints_banner(capsys):
    _run_with_inputs(["exit"])
    out = capsys.readouterr().out
    assert "AI Finance Controller" in out


def test_quit_command_also_stops_loop(capsys):
    _run_with_inputs(["quit"])
    out = capsys.readouterr().out
    assert "AI Finance Controller" in out


def test_exit_command_is_case_insensitive(capsys):
    _run_with_inputs(["EXIT"])
    out = capsys.readouterr().out
    assert "AI Finance Controller" in out


def test_blank_and_whitespace_lines_are_skipped_not_routed():
    with patch("agent_cli.handle") as mock_handle:
        _run_with_inputs(["", "   ", "exit"])
    mock_handle.assert_not_called()


def test_non_empty_message_is_routed_and_result_printed(capsys):
    with patch("agent_cli.handle", return_value="mocked answer") as mock_handle:
        _run_with_inputs(["what's our match rate", "exit"])
    mock_handle.assert_called_once_with("what's our match rate")
    assert "mocked answer" in capsys.readouterr().out


def test_multiple_messages_before_exit_each_get_routed():
    with patch("agent_cli.handle", return_value="ok") as mock_handle:
        _run_with_inputs(["first question", "second question", "exit"])
    assert mock_handle.call_count == 2


def test_keyboard_interrupt_exits_gracefully_without_raising():
    with patch("builtins.input", side_effect=KeyboardInterrupt()):
        agent_cli.main()  # must not raise


def test_eof_error_exits_gracefully_without_raising():
    with patch("builtins.input", side_effect=EOFError()):
        agent_cli.main()  # must not raise


def test_interrupt_after_some_messages_does_not_crash():
    with patch("agent_cli.handle", return_value="ok"):
        with patch("builtins.input", side_effect=["a real question", KeyboardInterrupt()]):
            agent_cli.main()  # must not raise
