"""Local server for the app: python servidor.py [port]   (default 8090, serves ./biblia)

Why not `python -m http.server`: on this Windows machine it cut es.json 625 bytes short every time
(ERR_CONNECTION_RESET), so the Spanish Bible never loaded. Speaking HTTP/1.1 fixes it.
"""
import functools, http.server, os, sys

port = int(sys.argv[1]) if len(sys.argv) > 1 else 8090
raiz = os.path.join(os.path.dirname(os.path.abspath(__file__)), "biblia")


class Handler(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def end_headers(self):
        # The app files change while we work on them; always revalidate.
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


print(f"Desliza en http://localhost:{port}  (Ctrl+C para salir)")
http.server.ThreadingHTTPServer(("", port), functools.partial(Handler, directory=raiz)).serve_forever()
