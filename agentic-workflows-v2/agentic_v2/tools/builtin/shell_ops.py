"""Tier 0 Shell execution tools - No LLM required."""

from __future__ import annotations

import asyncio
import os
import shlex
from pathlib import Path
from typing import Any

from ..base import BaseTool, ToolResult
from ..subprocess_utils import minimal_subprocess_env

_SHELL_METACHARS = frozenset({"|", "&", ";", "<", ">", "`", "$(", "${", "\n", "\r"})


def _split_command(command: str) -> list[str]:
    """Return argv for a simple command while refusing shell syntax."""
    if any(token in command for token in _SHELL_METACHARS):
        raise ValueError(
            "Shell metacharacters are not supported; use shell_exec args instead"
        )
    return shlex.split(command, posix=os.name != "nt")


def _load_shell_allowlist() -> frozenset[str] | None:
    """Return the set of allowed command basenames, or None if env var is
    unset/empty."""
    raw = os.environ.get("AGENTIC_SHELL_ALLOWED_COMMANDS", "").strip()
    if not raw:
        return None
    return frozenset(name.strip().lower() for name in raw.split(",") if name.strip())


class ShellTool(BaseTool):
    """Execute shell commands securely."""

    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        return "Execute shell commands with security controls and output capture"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "command": {
                "type": "string",
                "description": "Shell command to execute",
                "required": True,
            },
            "cwd": {
                "type": "string",
                "description": "Working directory for command execution",
                "required": False,
                "default": ".",
            },
            "timeout": {
                "type": "number",
                "description": "Command timeout in seconds",
                "required": False,
                "default": 60,
            },
            "capture_output": {
                "type": "boolean",
                "description": "Whether to capture stdout/stderr",
                "required": False,
                "default": True,
            },
        }

    @property
    def tier(self) -> int:
        return 0

    @property
    def examples(self) -> list[str]:
        return [
            "shell(command='ls -la') → List directory contents",
            "shell(command='echo hello') → Echo a string",
            "shell(command='python --version') → Check Python version",
        ]

    async def execute(
        self,
        command: str,
        cwd: str = ".",
        timeout: float = 60.0,
        capture_output: bool = True,
    ) -> ToolResult:
        """Execute shell command."""
        try:
            # Load allowlist — fail-closed when env var is unset
            allowed = _load_shell_allowlist()
            if allowed is None:
                return ToolResult(
                    success=False,
                    error=(
                        "Shell commands are disabled. "
                        "Set AGENTIC_SHELL_ALLOWED_COMMANDS to a comma-separated list "
                        "of permitted command names (e.g. 'ls,cat,python')."
                    ),
                )

            # Verify working directory
            cwd_path = Path(cwd)
            if not cwd_path.exists():
                return ToolResult(
                    success=False, error=f"Working directory does not exist: {cwd}"
                )

            try:
                cmd_list = _split_command(command)
            except ValueError as exc:
                return ToolResult(success=False, error=str(exc))

            if not cmd_list:
                return ToolResult(success=False, error="Command must not be empty")

            # Allowlist check: compare the resolved executable basename
            exe = Path(cmd_list[0]).stem.lower()  # .stem strips .exe on Windows
            if exe not in allowed:
                return ToolResult(
                    success=False,
                    error=(
                        f"Command '{exe}' is not in the shell allowlist. "
                        f"Add it to AGENTIC_SHELL_ALLOWED_COMMANDS to permit it."
                    ),
                )

            # Execute command without a shell so user input cannot be reinterpreted.
            if capture_output:
                process = await asyncio.create_subprocess_exec(
                    *cmd_list,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(cwd_path),
                    env=minimal_subprocess_env(),
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), timeout=timeout
                    )

                    stdout_str = stdout.decode("utf-8", errors="replace")
                    stderr_str = stderr.decode("utf-8", errors="replace")

                    return ToolResult(
                        success=process.returncode == 0,
                        data={
                            "stdout": stdout_str,
                            "stderr": stderr_str,
                            "exit_code": process.returncode,
                            "command": command,
                        },
                        metadata={
                            "cwd": cwd,
                            "timeout": timeout,
                        },
                    )

                except TimeoutError:
                    process.kill()
                    await process.wait()
                    return ToolResult(
                        success=False,
                        error=f"Command timed out after {timeout} seconds",
                        metadata={"command": command, "timeout": timeout},
                    )

            else:
                # Fire and forget mode
                process = await asyncio.create_subprocess_exec(
                    *cmd_list,
                    cwd=str(cwd_path),
                    env=minimal_subprocess_env(),
                )

                return ToolResult(
                    success=True,
                    data={
                        "pid": process.pid,
                        "command": command,
                        "message": "Command started (output not captured)",
                    },
                    metadata={"cwd": cwd},
                )

        except Exception as e:
            return ToolResult(
                success=False, error=f"Failed to execute shell command: {e!s}"
            )


class ShellExecTool(BaseTool):
    """Execute shell commands with automatic argument escaping."""

    @property
    def name(self) -> str:
        return "shell_exec"

    @property
    def description(self) -> str:
        return "Execute shell commands with automatic argument escaping for safety"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "program": {
                "type": "string",
                "description": "Program/command to execute",
                "required": True,
            },
            "args": {
                "type": "array",
                "description": "Arguments to pass to the program",
                "required": False,
                "default": [],
            },
            "cwd": {
                "type": "string",
                "description": "Working directory",
                "required": False,
                "default": ".",
            },
            "timeout": {
                "type": "number",
                "description": "Command timeout in seconds",
                "required": False,
                "default": 60,
            },
        }

    async def execute(
        self,
        program: str,
        args: list[str] | None = None,
        cwd: str = ".",
        timeout: float = 60.0,
    ) -> ToolResult:
        """Execute command with escaped arguments."""
        try:
            cwd_path = Path(cwd)
            if not cwd_path.exists():
                return ToolResult(
                    success=False, error=f"Working directory does not exist: {cwd}"
                )

            cmd_list = [program]
            if args:
                cmd_list.extend(args)

            process = await asyncio.create_subprocess_exec(
                *cmd_list,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd_path),
                env=minimal_subprocess_env(),
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )

                return ToolResult(
                    success=process.returncode == 0,
                    data={
                        "stdout": stdout.decode("utf-8", errors="replace"),
                        "stderr": stderr.decode("utf-8", errors="replace"),
                        "exit_code": process.returncode,
                        "program": program,
                        "args": args or [],
                    },
                    metadata={"cwd": cwd},
                )

            except TimeoutError:
                process.kill()
                await process.wait()
                return ToolResult(
                    success=False, error=f"Command timed out after {timeout} seconds"
                )

        except Exception as e:
            return ToolResult(success=False, error=f"Failed to execute command: {e!s}")
