"""Model representing a Flappy Event"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FlappyEvent:
    """Represents a flappy event"""

    account: str
    region: str
    environment: str
    application: str
    team: Optional[str] = None
    key: str = field(init=False)
    count: int = 0
    spread: int = 0

    def __post_init__(self):
        self.key = "_".join(
            [
                self.account,
                self.region,
                self.environment,
                self.application,
            ]
        )

    @property
    def tags(self):
        """Returns the DD tags for the flappy event"""
        return [
            f"account:{self.account}",
            f"region:{self.region}",
            f"environment:{self.environment}",
            f"application:{self.application}",
            f"env:{self.environment}",
            f"service:{self.application}",
            f"team:{self.team}",
            "source:flappy_detector",
        ]
