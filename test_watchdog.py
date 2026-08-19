# ponytail: minimal self-check for the watchdog's alert state machine, run manually.
from watchdog import _decide

assert _decide(is_up=True, last_status="ok") is None
assert _decide(is_up=True, last_status="down") == "recovered"
assert _decide(is_up=False, last_status="ok") == "down"
assert _decide(is_up=False, last_status="down") is None
print("ok")
