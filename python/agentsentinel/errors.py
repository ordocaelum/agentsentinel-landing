"""AgentSentinel exception hierarchy."""


class AgentSentinelError(Exception):
    """Base class for all AgentSentinel errors."""


class BudgetExceededError(AgentSentinelError):
    """Raised when an agent exceeds its configured spend budget."""

    def __init__(self, message: str = "Budget limit exceeded", *, budget: float = 0.0, spent: float = 0.0):
        super().__init__(message)
        self.budget = budget
        self.spent = spent


class ApprovalRequiredError(AgentSentinelError):
    """Raised when a tool invocation requires human approval before proceeding."""

    def __init__(self, message: str = "Human approval required", *, tool_name: str = ""):
        super().__init__(message)
        self.tool_name = tool_name


class RateLimitExceededError(AgentSentinelError):
    """Raised when a tool has been called more times than its configured rate limit allows."""

    def __init__(self, message: str = "Rate limit exceeded", *, tool_name: str = "", limit: str = ""):
        super().__init__(message)
        self.tool_name = tool_name
        self.limit = limit
