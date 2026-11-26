"""A supervised pool of worker processes (ADR-0002)."""

import json
import logging
import multiprocessing
import signal
import sys
import tomllib

from jobqueue import worker

CONFIG_PATH = "jobqueue.toml"


def load_config(path: str = CONFIG_PATH) -> dict:
    with open(path, "rb") as fh:
        return tomllib.load(fh)


class JsonLines(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({"level": record.levelname, "msg": record.getMessage(), "job": getattr(record, "job", None)})


def run(handler) -> None:
    config = load_config()
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(JsonLines())
    logging.basicConfig(level=logging.INFO, handlers=[stream])

    procs = [multiprocessing.Process(target=worker.run_forever, args=(handler,)) for _ in range(config["workers"])]
    for proc in procs:
        proc.start()

    def drain(_signum, _frame):
        for proc in procs:
            proc.join(timeout=config["drain_seconds"])
            if proc.is_alive():
                logging.warning("drain timeout")
                proc.kill()
        sys.exit(0)

    signal.signal(signal.SIGTERM, drain)
    while True:
        for i, proc in enumerate(procs):
            if not proc.is_alive():
                procs[i] = multiprocessing.Process(target=worker.run_forever, args=(handler,))
                procs[i].start()
        signal.pause()
