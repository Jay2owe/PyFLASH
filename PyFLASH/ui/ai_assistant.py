"""Shared assistant beside Streamlit; actions reuse the installed JSON runner.

The loopback proxy puts the original Streamlit window and ai-ify bridge on one
origin. No chat engine, panel or browser controller is copied into PyFLASH.
"""
from copy import deepcopy
from pathlib import Path
from threading import RLock
import json
import os
import subprocess
import sys
from uuid import uuid4


def overview(sessions, selected=None):
    source = deepcopy(sessions.get(selected, {})) if selected else {}
    from PyFLASH.control import describe
    return {"source": source.get("source"), "session": selected,
            "actions": describe(), "output_mode": "New recorded output per action"}


class RunnerSource:
    def __init__(self, snapshot, output_root):
        self.snapshot = snapshot
        self.output_root = Path(output_root)

    def names(self):
        from PyFLASH.control import describe
        return sorted(row["action"] for row in describe())

    def describe(self, name=None):
        from PyFLASH.control import describe
        if name is None:
            return {"actions": [{"name": row["action"], "summary": row.get("title", row["action"]),
                "mutates": row["access"] != "read-only", "destructive": row["access"] != "read-only"}
                for row in describe()]}
        row = describe(name)
        return {**row, "name": name, "summary": row.get("documentation", ""),
                "mutates": row["access"] != "read-only", "destructive": row["access"] != "read-only",
                "params": [*row["parameters"],
                    {"name": "_input", "required": False, "description": "CSV or trusted saved pickle; defaults to the pinned UI source."},
                    {"name": "_output", "required": False, "description": "New output directory; defaults to a unique assistant run."},
                    {"name": "_style", "required": False, "description": "Display options, separate from scientific parameters."}]}

    def run(self, name, params, *, confirm=False):
        if name not in self.names():
            return {"ok": False, "code": "unknown_action", "error": name}
        values = dict(params)
        pinned = self.snapshot()
        source = values.pop("_input", None) or (pinned.get("source") or {}).get("path")
        output = values.pop("_output", None) or self.output_root / uuid4().hex
        style = values.pop("_style", {})
        argv = [sys.executable, "-m", "PyFLASH.control", "run", name,
                "--params", json.dumps(values), "--style", json.dumps(style), "--output", str(output)]
        if source:
            argv += ["--input", str(source), "--group-col", pinned.get("group_col") or "Condition",
                     "--subject-col", pinned.get("subject_col") or "AnimalName"]
        try:
            process = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            for line in reversed(process.stdout.splitlines()):
                try:
                    reply = json.loads(line)
                except ValueError:
                    continue
                if isinstance(reply, dict) and "ok" in reply:
                    return reply
            return {"ok": False, "code": "failed", "error": process.stderr[-2000:] or "The recorded runner returned no JSON result."}
        except OSError as exc:
            return {"ok": False, "code": "failed", "error": str(exc)}


def create_app(upstream, token, *, options=None, engine_argv=None, output_root=None):
    import asyncio
    from contextlib import asynccontextmanager
    import httpx
    from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
    from fastapi.responses import JSONResponse, Response
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    from aiify import Agent
    from aiify.integration import helper_options
    from PyFLASH import context
    sessions, pinned, lock = {}, {}, RLock()

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(base_url=upstream, trust_env=False, timeout=120) as client:
            app.state.proxy = client
            yield

    app = FastAPI(title="PyFLASH", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    app.state.sessions = sessions

    def snapshot():
        with lock:
            return deepcopy(pinned)

    def capture(turn):
        identifier = turn.state.get("pyflash_session")
        with lock:
            pinned.clear()
            pinned.update(deepcopy(sessions.get(identifier, {})))

    agent = Agent("pyflash", actions=RunnerSource(snapshot, output_root or Path.cwd()/"assistant-runs"),
        guide=context, before_send=capture, engine_argv=engine_argv, prewarm=False,
        state=lambda: {"pinned_source": snapshot()}, limit_check_every=None,
        instructions="Use the installed PyFLASH action registry. Each action runs the same recorded JSON "
        "runner and creates a new output folder. Preserve scientific defaults and saved inputs. "
        "Use the on-screen bridge for the live Streamlit selection and to open results; do not "
        "claim a separately generated result was loaded into the window.",
        **helper_options(Path(__file__).resolve().parent.parent, env="PYFLASH_AIIFY_OPTIONS",
                         routes=(f"/{token}/workspace",), overrides=options))
    app.state.aiify_overview = lambda: overview(sessions, agent.ui_state.get("pyflash_session"))
    app.state.agent = agent

    @app.post(f"/{token}/workspace")
    async def update(request: Request):
        value = await request.json()
        if (not isinstance(value, dict) or set(value) - {"session", "source", "group_col", "subject_col"}
                or not isinstance(value.get("session"), str)):
            return JSONResponse({"error": "Invalid UI state"}, status_code=400)
        with lock:
            sessions[value["session"]] = deepcopy(value)
        return {"ok": True}

    @app.get(f"/{token}/workspace")
    async def current():
        return app.state.aiify_overview()

    @app.api_route("/{resource:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"])
    async def proxy(resource: str, request: Request):
        # Let the common panel own all assistant paths. These routes are inserted
        # after mounting below, while Streamlit remains the original UI/backend.
        headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length", "connection")}
        response = await app.state.proxy.request(request.method, "/"+resource,
            params=request.query_params, content=await request.body(), headers=headers)
        forwarded = {k: v for k, v in response.headers.items()
                     if k.lower() not in ("content-length", "content-encoding", "transfer-encoding", "connection")}
        return Response(response.content, status_code=response.status_code, headers=forwarded)

    @app.websocket("/{resource:path}")
    async def socket_proxy(websocket: WebSocket, resource: str):
        import websockets
        target = upstream.replace("http://", "ws://")+"/"+resource
        if websocket.url.query:
            target += "?"+websocket.url.query
        protocols = [p.strip() for p in websocket.headers.get("sec-websocket-protocol", "").split(",") if p.strip()]
        async with websockets.connect(target, subprotocols=protocols or None, max_size=None) as remote:
            await websocket.accept(subprotocol=remote.subprotocol)

            async def to_upstream():
                while True:
                    event = await websocket.receive()
                    if event["type"] == "websocket.disconnect":
                        return
                    await remote.send(event.get("text") if event.get("text") is not None else event["bytes"])

            async def to_window():
                async for message in remote:
                    await (websocket.send_text(message) if isinstance(message, str) else websocket.send_bytes(message))

            tasks = [asyncio.create_task(to_upstream()), asyncio.create_task(to_window())]
            try:
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

    # Mount before the proxy catch-all; shared routes must not go to Streamlit.
    proxy_routes = app.router.routes[-2:]
    del app.router.routes[-2:]
    agent.mount(app, prefix=f"/{token}/aiify", inject=lambda path: path == "/",
                panel={"title": "PyFLASH assistant", "layout": "float"})
    app.router.routes.extend(proxy_routes)
    return app


def publish(state):
    """Publish from Streamlit's UI thread; no worker thread touches its session state."""
    endpoint = os.environ.get("PYFLASH_AIIFY_WORKSPACE")
    if not endpoint:
        return
    from urllib.request import Request, urlopen
    from streamlit.components.v1 import html
    identifier = state.setdefault("ui_assistant_session", uuid4().hex)
    value = {"session": identifier, "source": state.get("ui_source"),
             "group_col": (state.get("ui_source") or {}).get("group_col", "Condition"),
             "subject_col": (state.get("ui_source") or {}).get("subject_col", "AnimalName")}
    request = Request(endpoint, data=json.dumps(value).encode(),
                      headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=2) as response:
        response.read()
    # Streamlit's own component shares the app origin. Only register a state hook;
    # the unmodified ai-ify bridge controls the actual parent page.
    html('<script>const p=window.parent; const fn=()=>('+json.dumps({"pyflash_session": identifier})+');'
         'if(p.aiify){p.aiify.setState(fn);}else{p.aiify={_pendingState:fn};}</script>', height=0)


def launch(command):
    """Run the existing Streamlit process behind an owned loopback assistant host."""
    import secrets
    import socket
    import uvicorn
    public_port = 8501
    args = list(command)
    for index, argument in enumerate(args):
        address = (args[index+1] if argument == "--server.address" and index+1 < len(args)
                   else argument.split("=", 1)[1] if argument.startswith("--server.address=") else None)
        if address is not None and address not in ("127.0.0.1", "localhost"):
            raise ValueError("The PyFLASH assistant launcher binds to loopback only.")
        if argument.startswith("--server.port="):
            public_port = int(argument.split("=", 1)[1])
        elif argument == "--server.port" and index+1 < len(args):
            public_port = int(args[index+1])
    if not 1024 <= public_port <= 65535:
        raise ValueError("Use a local port from 1024 to 65535.")
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        inner_port = available.getsockname()[1]
    filtered, skip = [], False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg in ("--server.port", "--server.address", "--browser.serverPort", "--server.headless"):
            skip = True
        elif not arg.startswith(("--server.port=", "--server.address=", "--browser.serverPort=", "--server.headless=")):
            filtered.append(arg)
    token = secrets.token_urlsafe(32)
    endpoint = f"http://127.0.0.1:{public_port}/{token}/workspace"
    process = subprocess.Popen([*filtered, f"--server.port={inner_port}", "--server.address=127.0.0.1",
        f"--browser.serverPort={public_port}", "--server.headless=true"],
        env={**os.environ, "PYFLASH_AIIFY_WORKSPACE": endpoint},
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        # Do not open a page until its original Streamlit server is listening.
        import time
        from urllib.request import urlopen
        deadline = time.monotonic() + 45
        while True:
            if process.poll() is not None:
                raise RuntimeError("The Streamlit process exited before its window was ready.")
            try:
                with urlopen(f"http://127.0.0.1:{inner_port}/_stcore/health", timeout=1):
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("The Streamlit window did not become ready within 45 seconds.")
                time.sleep(.1)
        app = create_app(f"http://127.0.0.1:{inner_port}", token)
        print(f"PyFLASH with assistant: http://127.0.0.1:{public_port}", flush=True)
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=public_port, log_level="warning",
                                                timeout_graceful_shutdown=5))
        headless = "--server.headless=true" in args or any(
            arg == "--server.headless" and index+1 < len(args) and args[index+1].lower() == "true"
            for index, arg in enumerate(args))
        if not headless:
            import threading, webbrowser
            def open_window():
                while not server.started and not server.should_exit:
                    time.sleep(.05)
                if server.started:
                    webbrowser.open(f"http://127.0.0.1:{public_port}")
            threading.Thread(target=open_window, daemon=True).start()
        server.run()
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=10)
