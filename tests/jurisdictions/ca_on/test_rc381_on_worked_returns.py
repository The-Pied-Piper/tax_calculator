"""Form RC381 on the worked returns: the form's lines on each return's inputs, one copy.

The return carries Schedule 8 or Form RC381, never both (the exclusive group
`ca/cpp_calculation`), and a worked return in `returns/` carries Schedule 8 (except Returns BO and
BP, which carry Form RC381 and expect its lines themselves), so the lines of the form `ca/rc381` are
checked here instead: for each return listed in `rc381_lines.yaml`, the return with its Schedule 8
left out and one copy of Form RC381 carried, expecting the lines listed for the form's one copy. A
line the file leaves out is not checked.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from tax_engine import build_tax_computation
from tax_engine.adapters.outbound.yaml_jurisdictions import YamlJurisdictionSource
from tax_engine.domain.artifact import ArtifactRegistry
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.registrations import JURISDICTIONS
from tests.jurisdictions.ca_on.end_to_end.support import service as shared_service
from tests.jurisdictions.ca_on.test_worked_returns import RETURNS, check_against
from tests.jurisdictions.ca_on.worked_return import WorkedReturn

# Schedule 8's Part 4 and Part 5 choices: a return carrying Form RC381 may not set them.
SCHEDULE_8_PARTS_COMPLETED = ("ca/cpp_part_4_completed", "ca/cpp_part_5_completed")
LINES: dict[str, Any] = yaml.safe_load((Path(__file__).parent / "rc381_lines.yaml").read_text())


def rc381_instead_of_schedule_8(stem: str, directory: Path) -> Path:
    """A copy of the worked return `stem` carrying one Form RC381 and no Schedule 8.

    It expects only the lines of the form that `rc381_lines.yaml` lists for the return.
    """
    original = yaml.safe_load((RETURNS / f"{stem}.yaml").read_text())
    # The Schedule 8 line 1 total of the return is the form's own box 26 input and the copy keeps
    # it: a box 16 total above its rate on a box 26 of 0 is refused.
    inputs = {
        **{k: v for k, v in original["inputs"].items() if k not in SCHEDULE_8_PARTS_COMPLETED},
        "ca/schedule_8_instances": [],
        "ca/rc381_instances": [{}],
    }
    path = directory / f"{stem}.yaml"
    path.write_text(yaml.safe_dump({**original, "inputs": inputs, "expected": LINES[stem]}))
    return path


@pytest.mark.parametrize("stem", sorted(LINES))
def test_the_rc381_lines_of_the_return_are_those_of_its_form(stem: str, tmp_path: Path) -> None:
    path = rc381_instead_of_schedule_8(stem, tmp_path)
    service = shared_service()  # registers the catalogs the loader resolves through
    artifacts = ArtifactRegistry.shared()
    build_tax_computation().compose(JurisdictionCode("CA-ON"), 2025)
    worked = WorkedReturn.load(path, artifacts)
    manifest = (
        YamlJurisdictionSource(JURISDICTIONS.roots())
        .get_jurisdiction(worked.jurisdiction)
        .manifest_for(worked.tax_year)
    )
    # No blank is expected of the return's own lines: they are those of a return with no
    # Schedule 8, which the worked return of the same name does not claim.
    worked = worked.with_blanks(frozenset(manifest.inputs), frozenset(), artifacts)
    worked.check_forms(manifest.forms, artifacts)
    check_against(worked, service)
