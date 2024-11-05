#!/usr/bin/env python3
"""
Broadcast filesystem updates (via inotify) over websockets.
Serve javascript over HTTP for receiving websocket messages in a browser.
"""

import asyncio
import logging
import os

import aionotify
from tornado.httpserver import HTTPServer
from tornado.web import Application, RequestHandler
from websockets.asyncio.server import broadcast, serve

#: Websocket port used to send updates to browser
WS_PORT = 5000
#: HTTP port used to serve static/index.html
HTTP_PORT = 8080

#: list of all web socket connections to broadcast to
#: TODO: will eventually need to track station id when serving multiple scanners
WS_CONNECTIONS = set()

FILEDIR = os.path.dirname(__file__)
logging.basicConfig(level=os.environ.get("LOGLEVEL", logging.INFO))


class WebServer(Application):
    """HTTP server (tornado request handler)
    Currently (20241102), this is just a fancy way to serve a static page.  Eventually

    * will match ``/scanner-id`` URL to ``station id`` dicom header for scanner specific page
    * could give more insite into or  modify DB.
    """

    def __init__(self):
        handlers = [
            (r"/", HttpIndex),
        ]
        settings = dict(
            static_path=os.path.join(FILEDIR, "static"),
            debug=True,
        )
        super().__init__(handlers, **settings)


class HttpIndex(RequestHandler):
    """Handle index page request"""

    async def get(self):
        """Default is just the index page"""
        self.render("static/index.html")


def http_run():
    """
    Actually run web server, listening on :py:data:`HTTP_PORT`. :py:class:`WebServer` defines what is actually served (and dispatches to :py:class:`HttpIndex`)
    """
    print(f"# running on http://127.0.0.1:{HTTP_PORT}")
    app = WebServer()
    server = HTTPServer(app)
    server.listen(HTTP_PORT)


async def track_ws(websocket):
    """
    Track connecting and disconnecting websocket connections.

    Stored in :py:data:`WS_CONNECTIONS`.
    Might eventually need a dict to broadcast only to dicom specified station id.
    """
    WS_CONNECTIONS.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        WS_CONNECTIONS.remove(websocket)


####


async def monitor_dirs(watcher):
    """
    Perpetually wait for new dicom files.
    Broadcast new files to the browser over websockets.
    """

    await watcher.setup()
    logging.debug("watching for new files")
    while True:
        event = await watcher.get_event()
        logging.info("got event %s", event)
        broadcast(WS_CONNECTIONS, f"{event}")


async def main(path):
    """
    Run all services on different threads.
    HTTP and inotify are forked. Websocket holds the main thread.
    """

    watcher = aionotify.Watcher()
    watcher.watch(
        path=path, flags=aionotify.Flags.CREATE
    )  # aionotify.Flags.MODIFY|aionotify.Flags.CREATE |aionotify.Flags.DELETE)
    asyncio.create_task(monitor_dirs(watcher))

    http_run()

    # while True:
    #    await asyncio.sleep(.1)
    async with serve(track_ws, "localhost", WS_PORT):
        await asyncio.get_running_loop().create_future()  # run forever

    watcher.close()
    logging.info("DONE")


if __name__ == "__main__":
    # TODO: watch based on input argument
    watch_dir = os.path.join(FILEDIR, "sim")
    asyncio.run(main(watch_dir))