"""Initialize persistent settings once, then replace this process with Uvicorn."""
import os
from pathlib import Path
import sys
import tempfile


def initialize_config(target, source):
    target, source = Path(target), Path(source)
    if target.exists(): return
    content = source.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temp:
            name = temp.name
            temp.write(content)
            temp.flush()
            os.fsync(temp.fileno())
        # Publish a complete file without replacing another initializer's output.
        try: os.link(name, target)
        except FileExistsError: pass
    finally:
        if name is not None: Path(name).unlink(missing_ok=True)


if __name__ == '__main__':
    os.umask(0o077)
    initialize_config(os.environ.get('PII_CONFIG','/data/config/rules.yaml'), Path(__file__).parent/'config/rules.yaml')
    os.execv(sys.executable,[sys.executable,'-m','uvicorn','web:app','--host','0.0.0.0','--port','8000','--workers','1'])
