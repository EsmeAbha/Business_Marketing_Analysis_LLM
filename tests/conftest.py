"""Keep the developer's own .env out of the test run.

`lucida.config` calls `load_dotenv()` when it is imported, so every value in
a local `.env` reaches `os.environ` before a single test runs. That is right
for the app and wrong for the suite: it means the tests grade whatever
machine they happen to be on.

One of those values actually breaks them. `AIW_HTTPS=1` marks the session
cookie `Secure`, which is correct behind TLS and impossible under test —
`TestClient` speaks plain `http://testserver`, so the cookie is set, refused
on the way back, and every signed-in request lands on `/login`. The failure
surfaces as "signup failed", which points at authentication rather than at
the transport, and costs an afternoon to find twice.

Set rather than deleted, and set here rather than in a fixture. Deleting it
does nothing, because `load_dotenv()` has not run yet at this point and puts
the value straight back; but `load_dotenv()` does not overwrite a name that
is already in the environment, so claiming it first is what actually holds.
A fixture would be too late either way — `serve` builds its middleware stack
at import, when the first test module is collected.
"""

import os

os.environ["AIW_HTTPS"] = "0"
