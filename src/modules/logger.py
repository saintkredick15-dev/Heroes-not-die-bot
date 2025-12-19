import datetime

class Logger:
    def __init__(self, module: str = "MAIN"):
        self.module = module

    def _log(self, message: str, level: str) -> None:
        colors = {
            "INFO": "\033[38;5;36m",
            "WARNING": "\033[38;5;226m", 
            "ERROR": "\033[38;5;196m",
            "DEBUG": "\033[38;5;82m",
            "CRITICAL": "\033[38;5;201m"
        }
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"{colors.get(level, '')}{timestamp} [{self.module}] [{level}] :: {message}\033[0m")

    def info(self, message: str) -> None:
        self._log(message, "INFO")

    def warning(self, message: str) -> None:
        self._log(message, "WARNING")

    def error(self, message: str) -> None:
        self._log(message, "ERROR")

    def debug(self, message: str) -> None:
        self._log(message, "DEBUG")

    def critical(self, message: str) -> None:
        self._log(message, "CRITICAL")