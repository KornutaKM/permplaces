import socket

import httpx
import pytest

from app.health import HealthServer, HealthState


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.asyncio
async def test_health_server_reports_live_and_readiness_state() -> None:
    port = _free_port()
    state = HealthState()
    server = HealthServer(host="127.0.0.1", port=port, state=state)
    await server.start()

    try:
        async with httpx.AsyncClient() as client:
            live = await client.get(f"http://127.0.0.1:{port}/health/live")
            not_ready = await client.get(f"http://127.0.0.1:{port}/health/ready")

            assert live.status_code == 200
            assert live.json() == {"status": "live"}
            assert not_ready.status_code == 503
            assert not_ready.json() == {"status": "not_ready"}

            state.mark_ready()
            ready = await client.get(f"http://127.0.0.1:{port}/health/ready")

            assert ready.status_code == 200
            assert ready.json() == {"status": "ready"}

            state.mark_not_ready()
            shutting_down = await client.get(
                f"http://127.0.0.1:{port}/health/ready"
            )
            assert shutting_down.status_code == 503
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_health_server_close_is_idempotent() -> None:
    server = HealthServer(host="127.0.0.1", port=_free_port())

    await server.start()
    await server.close()
    await server.close()


@pytest.mark.asyncio
async def test_health_server_cannot_start_twice() -> None:
    server = HealthServer(host="127.0.0.1", port=_free_port())
    await server.start()

    try:
        with pytest.raises(RuntimeError, match="already started"):
            await server.start()
    finally:
        await server.close()
