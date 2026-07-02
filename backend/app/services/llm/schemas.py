from dataclasses import dataclass


VALID_ROLES = frozenset({"system", "user", "assistant"})


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str

    def __post_init__(self) -> None:
        if self.role not in VALID_ROLES:
            raise ValueError(
                f"Invalid message role {self.role!r}; expected one of "
                f"{sorted(VALID_ROLES)}."
            )
        if not isinstance(self.content, str):
            raise TypeError(
                f"LLMMessage.content must be str, got {type(self.content).__name__}."
            )


@dataclass(frozen=True)
class LLMResponse:
    content: str
    model: str
    backend: str
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
