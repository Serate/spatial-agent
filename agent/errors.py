class AgentError(Exception):
    """Base error for recoverable Agent failures."""


class PlanningError(AgentError):
    """The request cannot be converted into an executable plan."""


class ClarificationNeeded(PlanningError):
    """The request is missing information or asks for an unsupported capability."""


class RequestRejected(PlanningError):
    """The request violates the runtime policy."""


class ToolError(AgentError):
    """A tool could not validate or execute a call."""


class RunCancelled(AgentError):
    """A running Agent task was cancelled at a safe execution boundary."""


class RunTimedOut(AgentError):
    """A running Agent task exceeded its cooperative time budget."""
