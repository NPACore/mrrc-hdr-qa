#!/usr/bin/env python3
"""
Broadcast filesystem updates (via inotify) over websockets.
Serve javascript over HTTP for receiving websocket messages in a browser.
"""

import asyncio
import glob
import json
import logging
import os
import re

import aionotify
from tornado.httpserver import HTTPServer
from tornado.web import Application, RequestHandler
from websockets.asyncio.server import broadcast, serve

from template_checker import TemplateChecker

Station = str
Sequence = str


class CurSeqStation:
    "Current Sequence settings at a MR Scanner station"

    #: description of current scanner sequence: series and name concatenated
    series_seqname: str
    station: str #: scanner identifier
    count: int #: number of volumes (dicoms) seen

    def __init__(self, station: Station):
        "initialize new series"
        self.station = station
        self.series_seqname = ""
        self.count = 0

    def update_isnew(self, series, seqname: Sequence) -> bool:
        """
        Inspect new dicom. Maintain count of repeats seen if not new
        Update object otherwise
        :param series: series info TODO(20250223WF): is this a number?
        :param seqname: sequence description
        :return:  True if is new
        """
        serseq = f"{series}{seqname}"
        if self.series_seqname == serseq:
            self.count += 1
            return False

        self.series_seqname = serseq
        self.count = 0
        return True

    def __repr__(self) -> str:
        return f"{self.station} {self.series_seqname} {self.count}"


#: Websocket port used to send updates to browser
WS_PORT = 5000
#: HTTP port used to serve static/index.html
HTTP_PORT = 8080

FOLLOW_FLAGS = aionotify.Flags.CLOSE_WRITE | aionotify.Flags.CREATE
#: list of all web socket connections to broadcast to
WS_CONNECTIONS = set()

FILEDIR = os.path.dirname(__file__)
logging.basicConfig(level=os.environ.get("LOGLEVEL", logging.INFO))


#: track the current state of each scanner based on filename
#: we can skip parsing a dicoms (and spamming the browser) if we've already seen the session
STATE: dict[Station, CurSeqStation] = {}


class WebServer(Application):
    """HTTP server (tornado request handler)
    Currently (20241102), this is just a fancy way to serve a static page.
    Also can update any client on current state.

    In the future, this could give more insight into or modify DB.
    Expect motion (a la FIRMM) to be handled by websocket and javascript (not HTTP).
    """

    def __init__(self):
        handlers = [
            (r"/", HttpIndex),
            # TODO(20250204): add GetState
            # r"/state", GetState, # json state response
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
def session_from_fname(dcm_fname: os.PathLike) -> Sequence:
    """
    We can use the file name to see if session name has changed.
    Don't need to read the dicom header -- if we know the station name.
    Can extract from ``001_sequencenum_seriesnum``::

      ls /data/dicomstream/20241016.MRQART_test.24.10.16_16_50_16_DST_1.3.12.2.1107.5.2.43.67078/|head
      001_000001_000001.dcm
      ...
      001_000017_000066.dcm
    """
    session = os.path.basename(dcm_fname)
    (proj, sequence, number) = session.split("_")
    return sequence


async def monitor_dirs(watcher, dcm_checker):
    """
    Perpetually wait for new dicom files.
    Broadcast new files to the browser over websockets.
    """

    await watcher.setup()
    logging.debug("watching for new files")
    while True:
        event = await watcher.get_event()
        logging.debug("got event %s", event)
        file = os.path.join(event.alias, event.name)
        if os.path.isdir(file):
            watcher.watch(path=file, flags=FOLLOW_FLAGS)
            logging.info("%s is a dir! following with %d", file, FOLLOW_FLAGS)
            continue
        if event.flags == aionotify.Flags.CREATE:
            logging.debug("file created but waiting for WRITE finish")
            continue
        # Event(flags=256, cookie=0, name='a', alias='/home/foranw/src/work/mrrc-hdr-qa/./sim')
        if re.search("^MR.|.dcm$|.IMA$", event.name):

            # NB. we might be able to look at the file project_seqnum_seriesnum.dcm
            # and skip without having to read the header
            # not sure how we'd get station
            hdr = dcm_checker.reader.read_dicom_tags(file)
            current_ses = STATE.get(hdr["Station"])
            if not current_ses:
                STATE[hdr["Station"]] = CurSeqStation(hdr["Station"])
                current_ses = STATE.get(hdr["Station"])

            # only send to browser if new
            # TODO: what if browser started up rate
            if current_ses.update_isnew(hdr["SeriesNumber"], hdr["SequenceName"]):
                logging.debug("first time seeing  %s", current_ses)
                msg = {
                    "station": hdr["Station"],
                    "type": "new",
                    "content": dcm_checker.check_header(hdr),
                }
                logging.debug(msg)
                broadcast(WS_CONNECTIONS, json.dumps(msg, default=list))
            else:
                msg = {
                    "station": hdr["Station"],
                    "type": "update",
                    "content": current_ses.count,
                }
                broadcast(WS_CONNECTIONS, json.dumps(msg, default=list))
                logging.debug("already have %s", STATE[hdr["Station"]])

            # TODO: if epi maybe try plotting motion?
            # async alignment

        else:
            logging.warning("non dicom file %s", event.name)
            # if we want to do this, we need msg formatted
            # broadcast(WS_CONNECTIONS, f"non-dicom file: {event}")


async def main(paths):
    """
    Run all services on different threads.
    HTTP and inotify are forked. Websocket holds the main thread.
    """
    dcm_checker = TemplateChecker()
    watcher = aionotify.Watcher()
    for path in paths:
        logging.info("watching %s", path)
        watcher.watch(
            path=path,
            flags=FOLLOW_FLAGS,
            # NB. prev had just aionotify.Flags.CREATE but that triggers too early (partial file)
        )  # aionotify.Flags.MODIFY|aionotify.Flags.CREATE |aionotify.Flags.DELETE)
        for sub_path in glob.glob(path + "/*/"):
            logging.info("trying to add %s", sub_path)
            if os.path.isdir(sub_path):
                watcher.watch(path=sub_path, flags=FOLLOW_FLAGS)
    asyncio.create_task(monitor_dirs(watcher, dcm_checker))

    http_run()

    # while True:
    #    await asyncio.sleep(.1)
    async with serve(track_ws, "0.0.0.0", WS_PORT):
        await asyncio.get_running_loop().create_future()  # run forever

    watcher.close()
    logging.info("DONE")


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--watch", required=True, nargs="+", help="One or more directory paths to watch"
    )
    #: port is useful to tweak, especially for debugging
    parser.add_argument(
        "-p", "--port", type=int, default=8080, help="HTTP port (not websocket port) "
    )
    args = parser.parse_args()

    if not os.path.isdir(args.watch[0]):
        raise Exception(f"{args.watch} is not a directory!")
    print(args)
    asyncio.run(main(args.watch))
