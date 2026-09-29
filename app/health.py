from __future__ import annotations

from dataclasses import dataclass

from aiohttp import web


@dataclass(slots=True)
class HealthState:
    ready: bool = False

    def mark_ready(self) -> None:
        self.ready = True

    def mark_not_ready(self) -> None:
        self.ready = False


class HealthServer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        state: HealthState | None = None,
    ) -> None:
        self.state = state or HealthState()
        self._host = host
        self._port = port
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        if self._runner is not None:
            raise RuntimeError("health server is already started")

        app = web.Application()
        app["health_state"] = self.state
        app.router.add_get("/health/live", live_handler)
        app.router.add_get("/health/ready", ready_handler)

        runner = web.AppRunner(app, access_log=None)
        await runner.setup()

        try:
            site = web.TCPSite(runner, host=self._host, port=self._port)
            await site.start()
        except BaseException:
            await runner.cleanup()
            raise

        self._runner = runner

    async def close(self) -> None:
        runner = self._runner
        self._runner = None
        if runner is not None:
            await runner.cleanup()


async def live_handler(request: web.Request) -> web.Response:
    del request
    return web.json_response({"status": "live"})


async def ready_handler(request: web.Request) -> web.Response:
    state = request.app["health_state"]
    if not isinstance(state, HealthState):
        raise RuntimeError("health state is not configured")

    status = 200 if state.ready else 503
    body = {"status": "ready" if state.ready else "not_ready"}
    return web.json_response(body, status=status)
