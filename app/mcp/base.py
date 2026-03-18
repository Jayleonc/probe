from typing import Generic, Protocol, TypeVar

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class BaseMCP(Protocol, Generic[InputT, OutputT]):
    async def execute(self, input_data: InputT) -> OutputT:  # pragma: no cover
        ...
