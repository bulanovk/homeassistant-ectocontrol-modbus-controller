"""PTY (pseudo-terminal) manager for virtual serial port testing.

This module provides a Python interface to socat for creating
virtual serial port pairs (PTY pairs) for integration testing
of serial communication without physical hardware.

Usage:
    manager = PTYManager()
    master, slave = await manager.create_pair()
    # Use master and slave as virtual serial ports
    await manager.close()
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

_LOGGER = logging.getLogger(__name__)


class PTYManager:
    """Manages socat PTY pairs for virtual serial port testing.

    Creates and manages pseudo-terminal pairs using socat.
    Each PTY pair provides two virtual serial ports that are
    connected to each other (like a null-modem cable).

    Example:
        >>> manager = PTYManager()
        >>> master, slave = await manager.create_pair()
        >>> print(f"Master: {master}, Slave: {slave}")
        Master: /dev/pts/0, Slave: /dev/pts/1
        >>> await manager.close()
    """

    def __init__(self):
        """Initialize the PTY manager."""
        self.process: Optional[asyncio.subprocess.Process] = None
        self.master_pty: Optional[str] = None
        self.slave_pty: Optional[str] = None

    async def create_pair(
        self,
        link_type: str = "pty,raw,echo=0",
        debug: bool = False
    ) -> tuple[str, str]:
        """Create a PTY pair using socat.

        Args:
            link_type: socat address type (default: pty,raw,echo=0)
            debug: Enable socat debug output

        Returns:
            (master_port, slave_port) tuple of PTY device paths

        Raises:
            RuntimeError: If socat is not installed or fails to create PTYs

        Example:
            >>> manager = PTYManager()
            >>> master, slave = await manager.create_pair()
            >>> master
            '/dev/pts/0'
            >>> slave
            '/dev/pts/1'
        """
        if self.process is not None:
            raise RuntimeError("PTY pair already exists. Call close() first.")

        # Build socat command
        cmd = ["socat"]

        if debug:
            cmd.extend(["-d", "-d"])

        cmd.extend([link_type, link_type])

        _LOGGER.debug("Starting socat: %s", " ".join(cmd))

        # Get list of PTYs before starting socat
        import os
        import subprocess
        import time

        existing_ptys = set()
        if os.path.exists("/dev/pts"):
            for f in os.listdir("/dev/pts"):
                if f.isdigit():
                    existing_ptys.add(f)

        _LOGGER.debug("Existing PTYs: %s", sorted(existing_ptys))

        try:
            # Start socat - let it run in background
            # We don't need its output, we'll just look for new PTYs
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=False
            )

            # Wait for socat to create PTYs
            time.sleep(1.0)

            # Check if process is still running
            poll_result = proc.poll()
            if poll_result is not None:
                raise RuntimeError(f"socat exited with code {poll_result}")

            # Scan for new PTYs
            new_ptys = []
            if os.path.exists("/dev/pts"):
                for f in os.listdir("/dev/pts"):
                    if f.isdigit() and f not in existing_ptys:
                        new_ptys.append(f"/dev/pts/{f}")

            _LOGGER.debug("New PTYs found: %s", new_ptys)

            if len(new_ptys) < 2:
                proc.kill()
                raise RuntimeError(
                    f"Failed to create PTY pair. Only found {len(new_ptys)} new PTYs."
                )

            # Store subprocess for cleanup
            self._subprocess = proc
            self.process = None  # Not using asyncio subprocess

            # Use first two new PTYs
            self.master_pty = new_ptys[0]
            self.slave_pty = new_ptys[1]

            _LOGGER.info("Created PTY pair: master=%s slave=%s",
                        self.master_pty, self.slave_pty)

            return self.master_pty, self.slave_pty

        except FileNotFoundError as exc:
            raise RuntimeError(
                "socat is not installed. Install with: sudo apt-get install socat"
            ) from exc

    async def close(self) -> None:
        """Close the socat process and cleanup PTY pair.

        This method terminates the socat subprocess and waits for it to exit.
        The PTY devices will be automatically cleaned up by the OS.
        """
        if self.process is None:
            return

        _LOGGER.debug("Closing PTY pair: %s <-> %s",
                     self.master_pty, self.slave_pty)

        await self._terminate_process()

        self.master_pty = None
        self.slave_pty = None

    async def _terminate_process(self) -> None:
        """Terminate the socat subprocess gracefully."""
        # Terminate synchronous subprocess if exists
        if hasattr(self, '_subprocess') and self._subprocess:
            try:
                self._subprocess.terminate()
                import time
                self._subprocess.wait(timeout=2.0)
                _LOGGER.debug("socat terminated gracefully")
            except:
                try:
                    self._subprocess.kill()
                    _LOGGER.debug("socat killed")
                except:
                    pass
            finally:
                self._subprocess = None
                return

        if self.process is None:
            return

        try:
            # Try graceful termination first
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=2.0)
                _LOGGER.debug("socat terminated gracefully")
                return
            except asyncio.TimeoutError:
                _LOGGER.warning("socat did not terminate gracefully, forcing kill")

            # Force kill if termination failed
            self.process.kill()
            await asyncio.wait_for(self.process.wait(), timeout=1.0)
            _LOGGER.debug("socat killed")

        except Exception as exc:
            _LOGGER.error("Error terminating socat: %s", exc)
        finally:
            self.process = None

    def __del__(self):
        """Cleanup on deletion.

        Note: This is a fallback cleanup. Always call close() explicitly
        in async code for proper cleanup.
        """
        if self.process is not None:
            # We can't use await in __del__, so just kill the process
            try:
                self.process.kill()
            except Exception:
                pass

    @property
    def is_active(self) -> bool:
        """Check if PTY pair is currently active.

        Returns:
            True if socat process is running, False otherwise
        """
        # Check subprocess first (new method)
        if hasattr(self, '_subprocess') and self._subprocess:
            return self._subprocess.poll() is None
        
        if self.process is None:
            return False

        return self.process.returncode is None

    @property
    def master_port(self) -> Optional[str]:
        """Get master PTY device path."""
        return self.master_pty

    @property
    def slave_port(self) -> Optional[str]:
        """Get slave PTY device path."""
        return self.slave_pty


async def check_socat_available() -> bool:
    """Check if socat is installed and available.

    Returns:
        True if socat is installed, False otherwise

    Example:
        >>> if await check_socat_available():
        ...     print("socat is installed")
        ... else:
        ...     print("socat is not available")
    """
    try:
        process = await asyncio.create_subprocess_exec(
            "socat", "-V",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await process.wait()
        return process.returncode == 0
    except FileNotFoundError:
        return False


# Standalone test
if __name__ == "__main__":
    async def main():
        """Test PTY manager."""
        print("Checking socat availability...")
        if not await check_socat_available():
            print("ERROR: socat is not installed")
            print("Install with: sudo apt-get install socat")
            return

        print("Creating PTY pair...")
        manager = PTYManager()
        try:
            master, slave = await manager.create_pair(debug=True)
            print(f"Master PTY: {master}")
            print(f"Slave PTY: {slave}")
            print(f"Active: {manager.is_active}")

            # Keep alive for a bit
            print("Waiting 3 seconds...")
            await asyncio.sleep(3)

        finally:
            print("Closing...")
            await manager.close()
            print("Done!")

    asyncio.run(main())
