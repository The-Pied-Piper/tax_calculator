"""YesOrNoCount: a count that answers a yes or no question, refused when it is above 1.

For a form line that asks a yes or no question and takes the answer as a count: 1 for yes, 0 for
no. The count is produced as is when it is 0 or 1; a count above 1 is not capped to 1 but is an
input error, `InputAboveBoundError`, naming the kind and its value. A negative count is refused by
the kind's `non_negative` declaration, not here. It records one `YesOrNoCountLine`.

The count may be blank (`BLANK_ALLOWED`); what a blank does is the manifest step's `blank:` line,
which passes it on here: a blank answer gives a blank checked count, and the check validates an
answer rather than inventing one.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from tax_engine.domain.artifact import Artifact, ArtifactKind
from tax_engine.domain.capability import Capability, CapabilityResult, capability
from tax_engine.domain.errors import InputAboveBoundError
from tax_engine.domain.trace import YesOrNoCountLine


@capability(identifier="yes_or_no_count")
class YesOrNoCount(Capability):
    """Produces `output`: the consumed `count`, unchanged, when it is 0 or 1."""

    CONSUMES: ClassVar[Mapping[str, type]] = {"count": int}
    PRODUCES: ClassVar[Mapping[str, type]] = {"output": int}
    BLANK_ALLOWED: ClassVar[frozenset[str]] = frozenset({"count"})

    def __init__(self, count: ArtifactKind[int], output: ArtifactKind[int]) -> None:
        """Wire the capability: the count checked, the count produced."""
        super().__init__(count=count, output=output)
        self._count = count
        self._output = output

    def compute(self, inputs: tuple[Artifact[Any], ...]) -> CapabilityResult:
        count = self._input(inputs, self._count).value
        if count > 1:
            raise InputAboveBoundError(
                f"{self._count.identifier} {count} is above a yes or no answer of 1"
            )
        return CapabilityResult(
            outputs=(Artifact(self._output, count),),
            trace=(
                YesOrNoCountLine(
                    output=self._output,
                    count_kind=self._count,
                    count=count,
                ),
            ),
        )
