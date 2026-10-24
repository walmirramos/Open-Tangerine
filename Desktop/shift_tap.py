"""Small deterministic gesture state machine. Never consumes system input."""
class ShiftTap:
    def __init__(self):
        self.started = None
        self.invalid = False
        self.last = -10

    def sample(self, down, conflict, now):
        if down:
            if self.started is None:
                self.started = now
                self.invalid = bool(conflict)
            self.invalid |= bool(conflict)
            return False
        if self.started is None:
            return False
        elapsed = now - self.started
        result = not self.invalid and not conflict and .025 <= elapsed <= 5 and now-self.last >= .6
        self.started = None
        self.invalid = False
        if result:
            self.last = now
        return result

    def reset(self):
        self.started = None
        self.invalid = False
