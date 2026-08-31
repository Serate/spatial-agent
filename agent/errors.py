class AgentError(Exception):
    """Base error for recoverable Agent failures."""


class PersistenceError(AgentError):
    """A bounded failure while reading or writing durable state."""

    def __init__(self, message: str, *, code: str = "persistence_error", retryable: bool = True):
        self.category = "persistence"
        self.code = str(code)[:96]
        self.retryable = bool(retryable)
        super().__init__(message)


class PlanningError(AgentError):
    """The request cannot be converted into an executable plan.

    Planner implementations may attach bounded governance metadata to a
    failure.  The message remains a human-facing compatibility field, while
    Runtime uses these attributes for stable cross-entry failure evidence.
    """

    def __init__(self, message: str, *, category=None, code=None, retryable=None):
        super().__init__(message)
        self.category = str(category)[:64] if category else None
        self.code = str(code)[:96] if code else None
        self.retryable = bool(retryable) if retryable is not None else None


class ClarificationNeeded(PlanningError):
    """The request is missing information or asks for an unsupported capability."""

    def __init__(self, message: str, details=None):
        super().__init__(message)
        self.details = details if isinstance(details, dict) else None


class RequestRejected(PlanningError):
    """The request violates the runtime policy."""


class AnswerUnavailable(PlanningError):
    """The selected answer path is unavailable without changing the request."""


class ToolError(AgentError):
    """A tool could not validate or execute a call.

    ``category``/``code``/``retryable`` are optional governance metadata. The
    human-readable message remains backward compatible, while the Runtime can
    preserve a stable classification for provider-backed tools.
    """

    def __init__(self, message: str, *, category=None, code=None, retryable=None):
        super().__init__(message)
        self.category = str(category)[:64] if category else None
        self.code = str(code)[:96] if code else None
        self.retryable = bool(retryable) if retryable is not None else None


class RunCancelled(AgentError):
    """A running Agent task was cancelled at a safe execution boundary."""


class RunTimedOut(AgentError):
    """A running Agent task exceeded its cooperative time budget."""
