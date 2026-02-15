"""Запуск сервера ProspEl."""
import sys
import socket
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent))


def is_port_in_use(port: int) -> bool:
    """Проверка, занят ли порт."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


if __name__ == "__main__":
    if is_port_in_use(8000):
        print("ВНИМАНИЕ: Порт 8000 уже занят. Запущено несколько backend?")
        print("Выполните stop_backend.bat перед запуском.")
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
