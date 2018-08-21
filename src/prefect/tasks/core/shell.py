import os
import subprocess

import prefect


class ShellTask(prefect.Task):
    """
    Task for running arbitrary shell commands.

    Args:
        - command (string): shell command to be executed
        - env (dict, optional): dictionary of environment variables to use for
            the subprocess; if provided, will override all other environment variables present
            on the system
        - **kwargs: additional keyword arguments to pass to the Task constructor
    """

    def __init__(self, command, env=None, **kwargs):
        self.command = command
        self.env = env or dict()
        super().__init__(**kwargs)

    def run(self):
        current_env = self.env or os.environ.copy()
        try:
            out = subprocess.check_output(
                ["bash", "-c", self.command], stderr=subprocess.STDOUT, env=current_env
            )
        except subprocess.CalledProcessError as exc:
            msg = "Command failed with exit code {0}: {1}".format(
                exc.returncode, exc.output
            )
            raise prefect.engine.signals.FAIL(msg) from None
        return out
