"""Admin sidecar route modules (B6).

Each module registers its handlers on jarvis.admin.server.app when imported;
jarvis.admin.server imports them all at its end. Importing the server here
first means `import jarvis.admin.routes.<area>` on its own also works: the
server finishes loading (and registers every area) before the area module
is looked up, instead of failing on a half-initialised circular import.
"""

from jarvis.admin import server as _server  # noqa: F401
