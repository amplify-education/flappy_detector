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
    group_name: str
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
                self.group_name,
            ]
        )

    @property
    def tags(self):
        """Returns the DD tags for the flappy event"""
        tags = [
            f"account:{self.account}",
            f"region:{self.region}",
            f"environment:{self.environment}",
            f"application:{self.application}",
            f"env:{self.environment}",
            f"service:{self.application}",
            f"group_name:{self.group_name}",
            "source:flappy_detector",
        ]

        if self.team:
            tags.append(f"team:{self.team}")

        return tags
