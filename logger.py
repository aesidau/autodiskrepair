import logging
import logging.handlers


def setup(path: str, max_bytes: int, backup_count: int) -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)

    fh = logging.handlers.RotatingFileHandler(
        path, maxBytes=max_bytes, backupCount=backup_count
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)
