"""Unit tests for YamlJurisdictionSource: YAML manifest files -> Jurisdiction domain object.

The source takes a mapping of namespace -> package directory. A jurisdiction's namespace is its
code lower-cased (`EX-ON` -> `ex-on`, `EX` -> `ex`), and its manifests are every `*.yaml` /
`*.yml` file in `roots[Namespace("ex-on")] / "manifests"`, or a subfolder of such
parts. Names are made up.

Each selection names a capability and fills its slots: `params` (slot -> family, optional),
`consumes` (slot -> artifact identifier, or a list of them kept in order as a tuple, optional)
and `produces` (slot -> artifact identifier, required). Slot names, and whether a slot takes one
identifier or a list, are not checked against capability classes here. The top-level `inputs` and
`outputs` list the computation's artifact identifiers: both required, non-empty lists of non-empty
strings without duplicates, and no identifier in both.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from textwrap import dedent
from types import MappingProxyType

import pytest

from tax_engine.adapters.outbound.yaml_jurisdictions import YamlJurisdictionSource
from tax_engine.domain.errors import InvalidManifestError, NotFoundError
from tax_engine.domain.jurisdiction import Jurisdiction
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import (
    CapabilitySelection,
    Default,
    Form,
    InputDeclaration,
    Manifest,
)
from tax_engine.domain.registry import Namespace
from tests.manifest_support import required_inputs

EX_ON = JurisdictionCode("EX-ON")

EX_ON_V1 = """\
jurisdiction: EX-ON
version: 1
valid_from_tax_year: 2025
inputs:
  - {name: ex/gross_income, required: true}
  - {name: ex/taxable_base, required: true}
outputs:
  - ex/savings_deduction
  - ex-on/levy
capabilities:
  - name: ex/savings_deduction
    params:
      cap: ex/savings_cap
      rate: ex/savings_rate
    consumes:
      income: ex/gross_income
    produces:
      output: ex/savings_deduction
  - name: ex/progressive_tax
    params:
      schedule: ex-on/brackets
    consumes:
      base: ex/taxable_base
    produces:
      output: ex-on/levy
"""


HEADER = """\
jurisdiction: EX-ON
version: 1
valid_from_tax_year: 2025
inputs: [{name: ex/x, required: true}]
outputs: [ex/y]
"""


def roots(directory: Path) -> Mapping[Namespace, Path]:
    """One made-up package, namespace `ex-on`, whose directory is `<directory>/ex-on`."""
    return {Namespace("ex-on"): directory / "ex-on"}


def source(directory: Path) -> YamlJurisdictionSource:
    return YamlJurisdictionSource(roots(directory))


def write(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(content), encoding="utf-8")
    return path


def returned(manifest: Manifest) -> Form:
    """The default form, the one of the parts without a `form:` key: `ex-on/return`."""
    (found,) = (form for form in manifest.forms if form.name == "ex-on/return")
    return found


def others(manifest: Manifest) -> tuple[Form, ...]:
    """The forms of `manifest` other than the default form."""
    return tuple(form for form in manifest.forms if form.name != "ex-on/return")


def test_parses_manifest_into_domain_objects(tmp_path: Path) -> None:
    write(tmp_path, "ex-on/manifests/v1.yaml", EX_ON_V1)

    result = source(tmp_path).get_jurisdiction(EX_ON)

    assert result == Jurisdiction(
        code=EX_ON,
        manifests=(
            Manifest(
                jurisdiction=EX_ON,
                version=1,
                valid_from_tax_year=2025,
                inputs=required_inputs(frozenset({"ex/gross_income", "ex/taxable_base"})),
                forms=(
                    Form(
                        required=True,
                        name="ex-on/return",
                        instances=None,
                        exports=("ex-on/levy", "ex/savings_deduction"),
                        capabilities=(
                            CapabilitySelection(
                                name="ex/savings_deduction",
                                params={"cap": "ex/savings_cap", "rate": "ex/savings_rate"},
                                consumes={"income": "ex/gross_income"},
                                produces={"output": "ex/savings_deduction"},
                            ),
                            CapabilitySelection(
                                name="ex/progressive_tax",
                                params={"schedule": "ex-on/brackets"},
                                consumes={"base": "ex/taxable_base"},
                                produces={"output": "ex-on/levy"},
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


def test_preserves_authored_capability_order(tmp_path: Path) -> None:
    write(
        tmp_path,
        "ex-on/manifests/m.yaml",
        """\
        jurisdiction: EX-ON
        version: 1
        valid_from_tax_year: 2025
        inputs: [{name: ex/x, required: true}]
        outputs: [ex/y]
        capabilities:
          - {name: ex/c, produces: {output: ex/c}}
          - {name: ex/a, produces: {output: ex/a}}
          - {name: ex/b, produces: {output: ex/b}}
        """,
    )

    (manifest,) = source(tmp_path).get_jurisdiction(EX_ON).manifests

    assert [c.name for c in returned(manifest).capabilities] == ["ex/c", "ex/a", "ex/b"]


def test_allows_same_capability_with_different_bindings(tmp_path: Path) -> None:
    write(
        tmp_path,
        "ex-on/manifests/m.yaml",
        """\
        jurisdiction: EX-ON
        version: 1
        valid_from_tax_year: 2025
        inputs: [{name: ex/x, required: true}]
        outputs: [ex/y]
        capabilities:
          - name: ex/progressive_tax
            params: {schedule: ex/brackets}
            consumes: {base: ex/taxable_base}
            produces: {output: ex/levy}
          - name: ex/progressive_tax
            params: {schedule: ex-on/brackets}
            consumes: {base: ex/taxable_base}
            produces: {output: ex-on/levy}
        """,
    )

    (manifest,) = source(tmp_path).get_jurisdiction(EX_ON).manifests

    assert [c.params for c in returned(manifest).capabilities] == [
        {"schedule": "ex/brackets"},
        {"schedule": "ex-on/brackets"},
    ]
    assert [c.produces for c in returned(manifest).capabilities] == [
        {"output": "ex/levy"},
        {"output": "ex-on/levy"},
    ]


def test_params_and_consumes_may_be_omitted(tmp_path: Path) -> None:
    write(
        tmp_path,
        "ex-on/manifests/m.yaml",
        """\
        jurisdiction: EX-ON
        version: 1
        valid_from_tax_year: 2025
        inputs: [{name: ex/x, required: true}]
        outputs: [ex/y]
        capabilities:
          - name: ex/flat_grant
            produces:
              output: ex/grant
        """,
    )

    (manifest,) = source(tmp_path).get_jurisdiction(EX_ON).manifests

    assert returned(manifest).capabilities == (
        CapabilitySelection(
            name="ex/flat_grant", params={}, consumes={}, produces={"output": "ex/grant"}
        ),
    )


def test_a_consumed_slot_may_list_identifiers(tmp_path: Path) -> None:
    write(
        tmp_path,
        "ex-on/manifests/m.yaml",
        HEADER
        + """\
capabilities:
  - name: ex/total_up
    consumes:
      base: ex/x
      parts:
        - ex/c
        - ex/a
        - ex/b
      others: [ex/d]
      none: []
    produces:
      total: ex/y
""",
    )

    (manifest,) = source(tmp_path).get_jurisdiction(EX_ON).manifests

    assert returned(manifest).capabilities == (
        CapabilitySelection(
            name="ex/total_up",
            params={},
            consumes={
                "base": "ex/x",
                "parts": ("ex/c", "ex/a", "ex/b"),
                "others": ("ex/d",),
                "none": (),
            },
            produces={"total": "ex/y"},
        ),
    )
    (selection,) = returned(manifest).capabilities
    assert isinstance(selection.consumes["base"], str)
    assert isinstance(selection.consumes["parts"], tuple)


def test_slot_bindings_are_read_only(tmp_path: Path) -> None:
    write(tmp_path, "ex-on/manifests/v1.yaml", EX_ON_V1)

    (manifest,) = source(tmp_path).get_jurisdiction(EX_ON).manifests

    for selection in returned(manifest).capabilities:
        for bindings in (selection.params, selection.consumes, selection.produces):
            assert isinstance(bindings, MappingProxyType)


def test_groups_every_manifest_version_of_the_jurisdiction(tmp_path: Path) -> None:
    write(tmp_path, "ex-on/manifests/v1.yaml", EX_ON_V1)
    write(tmp_path, "ex-on/manifests/older/v2.yml", EX_ON_V1.replace("version: 1", "version: 2"))
    write(tmp_path, "ex-on/manifests/README.md", "not a manifest")

    result = source(tmp_path).get_jurisdiction(EX_ON)

    assert result.code == EX_ON
    assert sorted(m.version for m in result.manifests) == [1, 2]
    assert {m.jurisdiction for m in result.manifests} == {EX_ON}


def test_reads_only_the_manifests_directory_of_the_jurisdictions_namespace(
    tmp_path: Path,
) -> None:
    ex_zz = JurisdictionCode("EX-ZZ")
    write(tmp_path, "pkg_on/manifests/v1.yaml", EX_ON_V1)
    write(tmp_path, "pkg_on/parameters/stray.yaml", EX_ON_V1.replace("version: 1", "version: 9"))
    write(tmp_path, "pkg_zz/manifests/v1.yaml", EX_ON_V1.replace("EX-ON", "EX-ZZ"))
    two = YamlJurisdictionSource(
        {Namespace("ex-on"): tmp_path / "pkg_on", Namespace("ex-zz"): tmp_path / "pkg_zz"}
    )

    on = two.get_jurisdiction(EX_ON)
    zz = two.get_jurisdiction(ex_zz)

    assert [m.version for m in on.manifests] == [1]
    assert {m.jurisdiction for m in on.manifests} == {EX_ON}
    assert {m.jurisdiction for m in zz.manifests} == {ex_zz}


def test_a_country_code_maps_to_its_lowercase_namespace(tmp_path: Path) -> None:
    write(tmp_path, "ex/manifests/v1.yaml", EX_ON_V1.replace("EX-ON", "EX"))

    result = YamlJurisdictionSource({Namespace("ex"): tmp_path / "ex"}).get_jurisdiction(
        JurisdictionCode("EX")
    )

    assert result.code == JurisdictionCode("EX")


def test_jurisdiction_without_a_namespace_root_is_not_found(tmp_path: Path) -> None:
    write(tmp_path, "ex-on/manifests/v1.yaml", EX_ON_V1)

    with pytest.raises(NotFoundError, match="EX-ZZ.*'ex-zz'"):
        source(tmp_path).get_jurisdiction(JurisdictionCode("EX-ZZ"))


def test_package_without_manifests_is_not_found(tmp_path: Path) -> None:
    (tmp_path / "ex-on").mkdir()

    with pytest.raises(NotFoundError, match="no manifests for jurisdiction EX-ON"):
        source(tmp_path).get_jurisdiction(EX_ON)


def test_missing_package_directory_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(InvalidManifestError, match="directory not found"):
        YamlJurisdictionSource({Namespace("ex-on"): tmp_path / "nope"}).get_jurisdiction(EX_ON)


def test_a_manifest_for_another_jurisdiction_in_the_package_is_rejected(tmp_path: Path) -> None:
    write(tmp_path, "ex-on/manifests/v1.yaml", EX_ON_V1)
    write(tmp_path, "ex-on/manifests/stray.yaml", EX_ON_V1.replace("EX-ON", "EX-ZZ"))

    with pytest.raises(InvalidManifestError, match="stray.yaml.*EX-ZZ"):
        source(tmp_path).get_jurisdiction(EX_ON)


def test_one_bad_file_fails_the_whole_load(tmp_path: Path) -> None:
    write(tmp_path, "ex-on/manifests/good.yaml", EX_ON_V1)
    write(tmp_path, "ex-on/manifests/bad.yaml", EX_ON_V1 + "extra: 1\n")

    with pytest.raises(InvalidManifestError, match="bad.yaml"):
        source(tmp_path).get_jurisdiction(EX_ON)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        pytest.param("", "manifest must be a mapping", id="empty-file"),
        pytest.param("- a\n- b\n", "manifest must be a mapping", id="document-is-list"),
        pytest.param(
            "jurisdiction: [unclosed\n", "while parsing a flow sequence", id="invalid-yaml"
        ),
        pytest.param(
            EX_ON_V1 + "version: 2\n", "duplicate key 'version'", id="duplicate-top-level-key"
        ),
        pytest.param(
            EX_ON_V1.replace(
                "  - name: ex/savings_deduction\n",
                "  - name: ex/savings_deduction\n    name: ex/other\n",
            ),
            "duplicate key 'name'",
            id="duplicate-capability-key",
        ),
        pytest.param(
            EX_ON_V1.replace(
                "      cap: ex/savings_cap\n", "      cap: ex/savings_cap\n      cap: ex/other\n"
            ),
            "duplicate key 'cap'",
            id="duplicate-parameter-slot",
        ),
        pytest.param(
            EX_ON_V1.replace(
                "      base: ex/taxable_base\n",
                "      base: ex/taxable_base\n      base: ex/other\n",
            ),
            "duplicate key 'base'",
            id="duplicate-consumed-slot",
        ),
        pytest.param(
            EX_ON_V1.replace(
                "      output: ex/savings_deduction\n",
                "      output: ex/savings_deduction\n      output: ex/other\n",
            ),
            "duplicate key 'output'",
            id="duplicate-produced-slot",
        ),
        pytest.param(EX_ON_V1 + "edges: []\n", r"unknown keys \['edges'\]", id="unknown-key"),
        pytest.param(
            EX_ON_V1.replace(
                "  - name: ex/savings_deduction\n",
                "  - name: ex/savings_deduction\n    after: ex/progressive_tax\n",
            ),
            r"capabilities\[0\]: unknown keys \['after'\]",
            id="unknown-capability-key",
        ),
        pytest.param(
            EX_ON_V1.replace(
                "  - name: ex/savings_deduction\n",
                "  - name: ex/savings_deduction\n    params_family: ex/savings\n",
            ),
            r"capabilities\[0\]: unknown keys \['params_family'\]",
            id="params-family-no-longer-accepted",
        ),
        pytest.param(
            EX_ON_V1.replace("version: 1\n", ""), r"missing keys \['version'\]", id="missing-key"
        ),
        pytest.param(
            EX_ON_V1.replace("  - name: ex/savings_deduction\n", "  -\n"),
            r"capabilities\[0\]: missing keys? \[?'name'",
            id="missing-capability-name",
        ),
        pytest.param(
            EX_ON_V1.replace("    produces:\n      output: ex/savings_deduction\n", ""),
            r"capabilities\[0\]: missing keys? \[?'produces'",
            id="missing-produces",
        ),
        pytest.param(
            EX_ON_V1.replace(
                "    produces:\n      output: ex/savings_deduction\n", "    produces: {}\n"
            ),
            r"capabilities\[0\]\.produces must name at least one slot",
            id="produces-empty",
        ),
        pytest.param(
            EX_ON_V1.replace(
                "      output: ex/savings_deduction", '      "": ex/savings_deduction'
            ),
            r"capabilities\[0\]\.produces: keys must not be empty",
            id="produced-slot-empty",
        ),
        pytest.param(
            EX_ON_V1.replace("      output: ex/savings_deduction", '      output: ""'),
            r"capabilities\[0\]\.produces\.output must not be empty",
            id="produced-identifier-empty",
        ),
        pytest.param(
            EX_ON_V1.replace("      cap: ex/savings_cap", "      cap: 7"),
            r"capabilities\[0\]\.params\.cap must be a string, got int",
            id="parameter-family-int",
        ),
        pytest.param(
            EX_ON_V1.replace("      income: ex/gross_income", "      income: [ex/gross_income, 7]"),
            r"capabilities\[0\]\.consumes\.income\[1\] must be a string, got int",
            id="consumed-list-element-int",
        ),
        pytest.param(
            EX_ON_V1.replace(
                "      income: ex/gross_income", '      income: [ex/gross_income, ""]'
            ),
            r"capabilities\[0\]\.consumes\.income\[1\] must not be empty",
            id="consumed-list-element-empty",
        ),
        pytest.param(
            EX_ON_V1.replace("      income: ex/gross_income", "      income: [[ex/gross_income]]"),
            r"capabilities\[0\]\.consumes\.income\[0\] must be a string, got list",
            id="consumed-list-element-list",
        ),
        pytest.param(
            EX_ON_V1.replace("      income: ex/gross_income", "      income: {a: ex/gross_income}"),
            r"capabilities\[0\]\.consumes\.income must be a string.*got dict",
            id="consumed-identifier-mapping",
        ),
        pytest.param(
            EX_ON_V1.replace("      cap: ex/savings_cap", "      cap: [ex/savings_cap]"),
            r"capabilities\[0\]\.params\.cap must be a string, got list",
            id="parameter-family-list",
        ),
        pytest.param(
            EX_ON_V1.replace(
                "      output: ex/savings_deduction", "      output: [ex/savings_deduction]"
            ),
            r"capabilities\[0\]\.produces\.output must be a string, got list",
            id="produced-identifier-list",
        ),
        pytest.param(
            EX_ON_V1.replace("      output: ex/savings_deduction", "      output: null"),
            r"capabilities\[0\]\.produces\.output must be a string, got NoneType",
            id="produced-identifier-null",
        ),
        pytest.param(
            EX_ON_V1.replace("      cap: ex/savings_cap", "      7: ex/savings_cap"),
            r"capabilities\[0\]\.params.*7.*must be a string",
            id="slot-name-int",
        ),
        pytest.param(
            EX_ON_V1.replace(
                "    params:\n      cap: ex/savings_cap\n      rate: ex/savings_rate\n",
                "    params: [ex/savings_cap]\n",
            ),
            r"capabilities\[0\]\.params must be a mapping",
            id="params-list",
        ),
        pytest.param(
            EX_ON_V1.replace(
                "    params:\n      cap: ex/savings_cap\n      rate: ex/savings_rate\n",
                "    params:\n",
            ),
            r"capabilities\[0\]\.params must be a mapping",
            id="params-null",
        ),
        pytest.param(
            EX_ON_V1.replace(
                "    consumes:\n      income: ex/gross_income\n", "    consumes: ex/gross_income\n"
            ),
            r"capabilities\[0\]\.consumes must be a mapping",
            id="consumes-string",
        ),
        pytest.param(
            EX_ON_V1.replace(
                "    produces:\n      output: ex/savings_deduction\n",
                "    produces: ex/savings_deduction\n",
            ),
            r"capabilities\[0\]\.produces must be a mapping",
            id="produces-string",
        ),
        pytest.param(
            EX_ON_V1.replace("version: 1", "version: '1'"),
            "version must be an integer, got str",
            id="version-str",
        ),
        pytest.param(
            EX_ON_V1.replace("version: 1", "version: yes"),
            "version must be an integer, got bool",
            id="version-bool",
        ),
        pytest.param(
            EX_ON_V1.replace("version: 1", "version: 1.0"),
            "version must be an integer, got float",
            id="version-float",
        ),
        pytest.param(
            EX_ON_V1.replace("valid_from_tax_year: 2025", "valid_from_tax_year: '2025'"),
            "valid_from_tax_year must be an integer, got str",
            id="tax-year-str",
        ),
        pytest.param(
            EX_ON_V1.replace("jurisdiction: EX-ON", "jurisdiction: 1"),
            "jurisdiction must be a string, got int",
            id="jurisdiction-int",
        ),
        pytest.param(
            EX_ON_V1.replace("jurisdiction: EX-ON", "jurisdiction: ex-on"),
            "jurisdiction: invalid jurisdiction code 'ex-on'",
            id="jurisdiction-malformed-code",
        ),
        pytest.param(
            HEADER + "capabilities: x\n",
            "capabilities must be a list",
            id="capabilities-not-list",
        ),
        pytest.param(
            HEADER + "capabilities: [x]\n",
            r"capabilities\[0\] must be a mapping",
            id="capability-not-mapping",
        ),
        pytest.param(
            EX_ON_V1.replace("name: ex/savings_deduction", "name: 7"),
            r"capabilities\[0\].name must be a string, got int",
            id="capability-name-int",
        ),
        pytest.param(
            EX_ON_V1.replace(
                "inputs:\n  - {name: ex/gross_income, required: true}\n"
                "  - {name: ex/taxable_base, required: true}\n",
                "",
            ),
            r"missing keys \['inputs'\]",
            id="missing-inputs",
        ),
        pytest.param(
            EX_ON_V1.replace("outputs:\n  - ex/savings_deduction\n  - ex-on/levy\n", ""),
            r"missing keys \['outputs'\]",
            id="missing-outputs",
        ),
        pytest.param(
            EX_ON_V1.replace(
                "inputs:\n  - {name: ex/gross_income, required: true}\n"
                "  - {name: ex/taxable_base, required: true}\n",
                "inputs: ex/gross_income\n",
            ),
            "inputs must be a list",
            id="inputs-not-list",
        ),
        pytest.param(
            EX_ON_V1.replace(
                "outputs:\n  - ex/savings_deduction\n  - ex-on/levy\n", "outputs: {a: ex/levy}\n"
            ),
            "outputs must be a list",
            id="outputs-not-list",
        ),
        pytest.param(
            EX_ON_V1.replace(
                "inputs:\n  - {name: ex/gross_income, required: true}\n"
                "  - {name: ex/taxable_base, required: true}\n",
                "inputs: []\n",
            ),
            "inputs must name at least one artifact",
            id="inputs-empty",
        ),
        pytest.param(
            EX_ON_V1.replace(
                "outputs:\n  - ex/savings_deduction\n  - ex-on/levy\n", "outputs: []\n"
            ),
            "outputs must name at least one artifact",
            id="outputs-empty",
        ),
        pytest.param(
            EX_ON_V1.replace(
                "inputs:\n  - {name: ex/gross_income, required: true}\n", "inputs:\n  - 7\n"
            ),
            r"inputs\[0\] must be a mapping",
            id="input-int",
        ),
        pytest.param(
            EX_ON_V1.replace("  - ex-on/levy\n", "  - null\n"),
            r"outputs\[1\] must be a string, got NoneType",
            id="output-null",
        ),
        pytest.param(
            EX_ON_V1.replace(
                "inputs:\n  - {name: ex/gross_income, required: true}\n",
                'inputs:\n  - {name: "", required: true}\n',
            ),
            r"inputs\[0\].name must not be empty",
            id="input-empty-string",
        ),
        pytest.param(
            EX_ON_V1.replace(
                "  - {name: ex/taxable_base, required: true}\n",
                "  - {name: ex/gross_income, required: true}\n",
            ),
            r"inputs\[1\]: 'ex/gross_income' is listed more than once",
            id="input-duplicate",
        ),
        pytest.param(
            EX_ON_V1.replace("  - ex-on/levy\n", "  - ex/savings_deduction\n"),
            r"outputs\[1\]: 'ex/savings_deduction' is listed more than once",
            id="output-duplicate",
        ),
    ],
)
def test_rejects_malformed_manifest(tmp_path: Path, content: str, message: str) -> None:
    write(tmp_path, "ex-on/manifests/ex-on-v1.yaml", content)

    with pytest.raises(InvalidManifestError, match=message) as excinfo:
        source(tmp_path).get_jurisdiction(EX_ON)

    assert "ex-on-v1.yaml" in str(excinfo.value)


def test_an_identifier_listed_as_both_input_and_output_is_carried_by_the_manifest(
    tmp_path: Path,
) -> None:
    write(
        tmp_path,
        "ex-on/manifests/v1.yaml",
        EX_ON_V1.replace("  - ex-on/levy\n", "  - ex-on/levy\n  - ex/taxable_base\n"),
    )

    manifest = source(tmp_path).get_jurisdiction(EX_ON).manifests[0]

    assert manifest.inputs.keys() == frozenset({"ex/gross_income", "ex/taxable_base"})
    assert frozenset(returned(manifest).exports) == frozenset(
        {"ex/savings_deduction", "ex-on/levy", "ex/taxable_base"}
    )


# --- A subfolder of manifests/ is one manifest, merged from its parts ---------------------
#
# Every `*.yaml` / `*.yml` file inside the subfolder (recursively) is a part, read in sorted path
# order. A part may carry any subset of the six manifest keys. The scalar keys (`jurisdiction`,
# `version`, `valid_from_tax_year`) must each be in exactly one part; the lists (`inputs`,
# `outputs`, `capabilities`) are concatenated in part order. The merged mapping then goes through
# the same strict parse as a flat file. Errors name the part file, except a key missing after the
# merge, which no part can own and so names the folder.

SCALARS = """\
jurisdiction: EX-ON
version: 1
valid_from_tax_year: 2025
"""

INPUTS = """\
inputs: [{name: ex/x, required: true}]
"""

OUTPUTS = """\
outputs: [ex/y]
"""

CAPABILITIES_A = """\
capabilities:
  - {name: ex/a, produces: {output: ex/a}}
  - {name: ex/b, produces: {output: ex/b}}
"""

CAPABILITIES_B = """\
capabilities:
  - {name: ex/c, produces: {output: ex/c}}
"""


def write_parts(directory: Path, parts: Mapping[str, str], folder: str = "v1") -> None:
    for name, content in parts.items():
        write(directory, f"ex-on/manifests/{folder}/{name}", content)


def only_manifest(directory: Path) -> Manifest:
    (manifest,) = source(directory).get_jurisdiction(EX_ON).manifests
    return manifest


def test_a_folder_is_one_manifest_merged_from_its_parts(tmp_path: Path) -> None:
    write_parts(
        tmp_path,
        {
            "00-header.yaml": SCALARS,
            "01-inputs.yaml": INPUTS,
            "02-outputs.yaml": OUTPUTS,
            "03-a.yaml": CAPABILITIES_A,
            "04-b.yaml": CAPABILITIES_B,
        },
    )

    assert only_manifest(tmp_path) == Manifest(
        jurisdiction=EX_ON,
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(frozenset({"ex/x"})),
        forms=(
            Form(
                required=True,
                name="ex-on/return",
                instances=None,
                exports=("ex/y",),
                capabilities=(
                    CapabilitySelection(
                        name="ex/a", params={}, consumes={}, produces={"output": "ex/a"}
                    ),
                    CapabilitySelection(
                        name="ex/b", params={}, consumes={}, produces={"output": "ex/b"}
                    ),
                    CapabilitySelection(
                        name="ex/c", params={}, consumes={}, produces={"output": "ex/c"}
                    ),
                ),
            ),
        ),
    )


def test_a_folder_loads_the_same_manifest_as_the_flat_file(tmp_path: Path) -> None:
    write(tmp_path, "flat/ex-on/manifests/v1.yaml", EX_ON_V1)
    head, _, rest = EX_ON_V1.partition("inputs:\n")
    inputs, _, capabilities = ("inputs:\n" + rest).partition("capabilities:\n")
    write_parts(
        tmp_path / "split",
        {"00.yaml": head, "01.yaml": inputs, "02.yaml": "capabilities:\n" + capabilities},
    )

    flat = YamlJurisdictionSource({Namespace("ex-on"): tmp_path / "flat" / "ex-on"})
    split = YamlJurisdictionSource({Namespace("ex-on"): tmp_path / "split" / "ex-on"})

    assert split.get_jurisdiction(EX_ON) == flat.get_jurisdiction(EX_ON)


def test_lists_are_concatenated_in_sorted_path_order_whatever_the_write_order(
    tmp_path: Path,
) -> None:
    write_parts(
        tmp_path,
        {
            "30-c.yaml": CAPABILITIES_B,
            "10-a.yaml": CAPABILITIES_A,
            "00-header.yaml": SCALARS + INPUTS + OUTPUTS,
        },
    )

    assert [c.name for c in returned(only_manifest(tmp_path)).capabilities] == [
        "ex/a",
        "ex/b",
        "ex/c",
    ]


def test_parts_in_nested_folders_are_read_and_yml_sorts_with_yaml(tmp_path: Path) -> None:
    write_parts(
        tmp_path,
        {
            "00-header.yaml": SCALARS + INPUTS + OUTPUTS,
            "01-a.yml": "capabilities:\n  - {name: ex/first, produces: {output: ex/first}}\n",
            "02-b.yaml": "capabilities:\n  - {name: ex/second, produces: {output: ex/second}}\n",
            "03-c.yml": "capabilities:\n  - {name: ex/third, produces: {output: ex/third}}\n",
            "sub/10-d.yaml": "capabilities:\n  - {name: ex/4, produces: {output: ex/4}}\n",
        },
    )

    names = [c.name for c in returned(only_manifest(tmp_path)).capabilities]

    assert names == ["ex/first", "ex/second", "ex/third", "ex/4"]


def test_inputs_and_outputs_are_concatenated_across_parts(tmp_path: Path) -> None:
    write_parts(
        tmp_path,
        {
            "00-header.yaml": SCALARS,
            "01-a.yaml": "inputs: [{name: ex/x1, required: true}]\noutputs: [ex/y1]\n",
            "02-b.yaml": (
                "inputs: [{name: ex/x2, required: true}]\noutputs: [ex/y2]\ncapabilities: []\n"
            ),
        },
    )

    manifest = only_manifest(tmp_path)

    assert manifest.inputs.keys() == frozenset({"ex/x1", "ex/x2"})
    assert frozenset(returned(manifest).exports) == frozenset({"ex/y1", "ex/y2"})


def test_a_part_may_carry_any_subset_of_the_keys(tmp_path: Path) -> None:
    write_parts(
        tmp_path,
        {
            "00-version.yaml": "version: 1\n",
            "01-jurisdiction.yaml": "jurisdiction: EX-ON\ninputs: [{name: ex/x, required: true}]\n",
            "02-year-and-outputs.yaml": "valid_from_tax_year: 2025\noutputs: [ex/y]\n",
            "03-a.yaml": CAPABILITIES_A,
        },
    )

    manifest = only_manifest(tmp_path)

    assert (manifest.jurisdiction, manifest.version, manifest.valid_from_tax_year) == (
        EX_ON,
        1,
        2025,
    )
    assert manifest.inputs.keys() == frozenset({"ex/x"})
    assert [c.name for c in returned(manifest).capabilities] == ["ex/a", "ex/b"]


def test_a_flat_file_still_loads_as_one_whole_manifest(tmp_path: Path) -> None:
    write(tmp_path, "ex-on/manifests/v1.yaml", SCALARS + INPUTS + OUTPUTS + CAPABILITIES_A)

    assert [c.name for c in returned(only_manifest(tmp_path)).capabilities] == ["ex/a", "ex/b"]


def test_a_flat_file_must_still_be_whole_on_its_own(tmp_path: Path) -> None:
    write(tmp_path, "ex-on/manifests/v1.yaml", SCALARS + INPUTS)

    with pytest.raises(InvalidManifestError, match=r"missing keys \['capabilities', 'outputs'\]"):
        source(tmp_path).get_jurisdiction(EX_ON)


def test_a_flat_file_and_a_folder_side_by_side_are_two_manifests(tmp_path: Path) -> None:
    write(tmp_path, "ex-on/manifests/v1.yaml", SCALARS + INPUTS + OUTPUTS + CAPABILITIES_A)
    write_parts(
        tmp_path,
        {
            "00-header.yaml": SCALARS.replace("version: 1", "version: 2"),
            "01-rest.yaml": INPUTS + OUTPUTS + CAPABILITIES_B,
        },
        folder="v2",
    )

    manifests = source(tmp_path).get_jurisdiction(EX_ON).manifests

    assert [m.version for m in manifests] == [1, 2]
    assert [len(returned(m).capabilities) for m in manifests] == [2, 1]


@pytest.mark.parametrize(
    ("parts", "message"),
    [
        pytest.param(
            {"00-header.yaml": SCALARS, "01-bad.yaml": "inputs: [unclosed\n"},
            "while parsing a flow sequence",
            id="malformed-yaml",
        ),
        pytest.param(
            {"00-header.yaml": SCALARS, "01-bad.yaml": ""},
            "manifest must be a mapping",
            id="empty-part",
        ),
        pytest.param(
            {"00-header.yaml": SCALARS, "01-bad.yaml": "- a\n- b\n"},
            "manifest must be a mapping",
            id="part-is-a-list",
        ),
        pytest.param(
            {
                "00-header.yaml": SCALARS,
                "01-bad.yaml": (
                    "inputs: [{name: ex/x, required: true}]\n"
                    "inputs: [{name: ex/z, required: true}]\n"
                ),
            },
            "duplicate key 'inputs'",
            id="duplicate-key-inside-one-part",
        ),
        pytest.param(
            {"00-header.yaml": SCALARS, "01-bad.yaml": "bogus: 1\n"},
            r"unknown keys \['bogus'\]",
            id="unknown-key",
        ),
        pytest.param(
            {"00-header.yaml": SCALARS, "01-bad.yaml": "bogus: 1\nextra: 2\n"},
            r"unknown keys \['bogus', 'extra'\]",
            id="unknown-keys-all-named",
        ),
        pytest.param(
            {"00-header.yaml": SCALARS, "01-bad.yaml": "inputs: ex/x\n"},
            "inputs must be a list",
            id="inputs-not-a-list",
        ),
        pytest.param(
            {"00-header.yaml": SCALARS, "01-bad.yaml": "outputs: {a: b}\n"},
            "outputs must be a list",
            id="outputs-not-a-list",
        ),
        pytest.param(
            {"00-header.yaml": SCALARS, "01-bad.yaml": "capabilities: ex/a\n"},
            "capabilities must be a list",
            id="capabilities-not-a-list",
        ),
        pytest.param(
            {
                "00-header.yaml": SCALARS.replace("version: 1\n", ""),
                "01-bad.yaml": "version: '1'\n",
            },
            "version must be an integer, got str",
            id="scalar-wrong-type",
        ),
        pytest.param(
            {
                "00-header.yaml": SCALARS,
                "01-bad.yaml": "inputs: [{name: ex/x, required: true}, 7]\n",
            },
            r"inputs\[1\] must be a mapping",
            id="input-element-wrong-type",
        ),
        pytest.param(
            {"00-header.yaml": SCALARS, "01-bad.yaml": "capabilities:\n  - {name: ex/a}\n"},
            r"capabilities\[0\]: missing keys \['produces'\]",
            id="capability-missing-produces",
        ),
        pytest.param(
            {"00-header.yaml": SCALARS, "01-bad.yaml": "inputs: [{name: '', required: true}]\n"},
            r"inputs\[0\].name must not be empty",
            id="input-empty-string",
        ),
        pytest.param(
            {
                "00-header.yaml": SCALARS,
                "01-bad.yaml": (
                    "inputs: [{name: ex/x, required: true}, {name: ex/x, required: true}]\n"
                ),
            },
            r"inputs\[1\]: 'ex/x' is listed more than once",
            id="input-repeated-inside-one-part",
        ),
    ],
)
def test_a_bad_part_is_rejected_naming_the_part_file(
    tmp_path: Path, parts: Mapping[str, str], message: str
) -> None:
    write_parts(tmp_path, parts)

    with pytest.raises(InvalidManifestError, match=message) as excinfo:
        source(tmp_path).get_jurisdiction(EX_ON)

    assert str(tmp_path / "ex-on" / "manifests" / "v1" / "01-bad.yaml") in str(excinfo.value)


@pytest.mark.parametrize(
    "scalar", ["jurisdiction: EX-ON", "version: 1", "valid_from_tax_year: 2025"]
)
def test_a_scalar_key_in_two_parts_is_rejected_naming_both_parts(
    tmp_path: Path, scalar: str
) -> None:
    key = scalar.split(":")[0]
    write_parts(
        tmp_path,
        {"00-header.yaml": SCALARS + INPUTS + OUTPUTS, "01-again.yaml": scalar + "\n"},
    )
    folder = tmp_path / "ex-on" / "manifests" / "v1"

    with pytest.raises(InvalidManifestError) as excinfo:
        source(tmp_path).get_jurisdiction(EX_ON)

    assert str(excinfo.value) == (
        f"{folder / '01-again.yaml'}: key {key!r} is already set in {folder / '00-header.yaml'}"
    )


def test_a_scalar_key_repeated_with_a_different_value_is_still_rejected(tmp_path: Path) -> None:
    write_parts(
        tmp_path,
        {"00-header.yaml": SCALARS + INPUTS + OUTPUTS, "01-again.yaml": "version: 2\n"},
    )

    with pytest.raises(InvalidManifestError, match="key 'version' is already set in"):
        source(tmp_path).get_jurisdiction(EX_ON)


@pytest.mark.parametrize("key", ["inputs", "outputs"])
def test_an_identifier_in_two_parts_is_rejected_naming_both_parts(tmp_path: Path, key: str) -> None:
    write_parts(
        tmp_path,
        {
            "00-header.yaml": SCALARS + "inputs: [{name: ex/x, required: true}]\noutputs: [ex/y]\n",
            "01-again.yaml": (
                "inputs: [{name: ex/other, required: true}, {name: ex/x, required: true}]\n"
                if key == "inputs"
                else "outputs: [ex/other, ex/y]\n"
            ),
        },
    )
    folder = tmp_path / "ex-on" / "manifests" / "v1"
    identifier = "ex/x" if key == "inputs" else "ex/y"

    with pytest.raises(InvalidManifestError) as excinfo:
        source(tmp_path).get_jurisdiction(EX_ON)

    assert str(excinfo.value) == (
        f"{folder / '01-again.yaml'}: {key}[1]: {identifier!r} is already listed in "
        f"{folder / '00-header.yaml'}"
    )


def test_the_same_identifier_as_input_in_one_part_and_output_in_another_is_not_a_repeat(
    tmp_path: Path,
) -> None:
    write_parts(
        tmp_path,
        {
            "00-header.yaml": SCALARS + "inputs: [{name: ex/x, required: true}]\noutputs: [ex/y]\n",
            "01-more.yaml": "outputs: [ex/x]\n",
            "02-caps.yaml": CAPABILITIES_A,
        },
    )

    manifest = only_manifest(tmp_path)

    assert manifest.inputs.keys() == frozenset({"ex/x"})
    assert frozenset(returned(manifest).exports) == frozenset({"ex/y", "ex/x"})


@pytest.mark.parametrize(
    "key",
    ["jurisdiction", "version", "valid_from_tax_year", "inputs", "outputs", "capabilities"],
)
def test_a_key_in_no_part_is_still_missing_after_the_merge(tmp_path: Path, key: str) -> None:
    whole = {
        "jurisdiction": "jurisdiction: EX-ON\n",
        "version": "version: 1\n",
        "valid_from_tax_year": "valid_from_tax_year: 2025\n",
        "inputs": INPUTS,
        "outputs": OUTPUTS,
        "capabilities": CAPABILITIES_A,
    }
    write_parts(
        tmp_path,
        {
            f"{n:02}.yaml": text
            for n, text in enumerate(text for name, text in whole.items() if name != key)
        },
    )

    with pytest.raises(InvalidManifestError, match=rf"missing keys \['{key}'\]") as excinfo:
        source(tmp_path).get_jurisdiction(EX_ON)

    assert str(tmp_path / "ex-on" / "manifests" / "v1") in str(excinfo.value)


def test_one_bad_part_fails_the_whole_load(tmp_path: Path) -> None:
    write(tmp_path, "ex-on/manifests/good.yaml", EX_ON_V1)
    write_parts(tmp_path, {"00-header.yaml": SCALARS, "01-bad.yaml": "bogus: 1\n"}, folder="v2")

    with pytest.raises(InvalidManifestError, match="01-bad.yaml"):
        source(tmp_path).get_jurisdiction(EX_ON)


def test_a_folder_manifest_for_another_jurisdiction_is_rejected(tmp_path: Path) -> None:
    write_parts(
        tmp_path,
        {
            "00-header.yaml": SCALARS.replace("EX-ON", "EX-BC") + INPUTS + OUTPUTS,
            "01-a.yaml": CAPABILITIES_A,
        },
    )

    with pytest.raises(InvalidManifestError, match="manifest is for EX-BC, but its package"):
        source(tmp_path).get_jurisdiction(EX_ON)


def test_a_subfolder_without_yaml_files_is_not_a_manifest(tmp_path: Path) -> None:
    write(tmp_path / "ex-on" / "manifests", "v1.yaml", EX_ON_V1)
    (tmp_path / "ex-on" / "manifests" / "__pycache__").mkdir()
    (tmp_path / "ex-on" / "manifests" / "notes").mkdir()
    (tmp_path / "ex-on" / "manifests" / "notes" / "readme.txt").write_text("not a part")

    (only,) = source(tmp_path).get_jurisdiction(EX_ON).manifests

    assert only.version == 1


# --- forms: the `form:` key of a part ------------------------------------------------------------
#
# A part may carry a `form:` mapping `{name, instances, exports}`, strict like the other keys, and
# then ALL `capabilities` of that part belong to that form (not to the return). A form may span
# several parts that carry the same `form.name`; only ONE of them declares `instances` and
# `exports` (both together), the others carry the name alone. A part with no `form:` key is the
# return's, as before. `inputs` and `outputs` stay top-level. Errors name the part file.

FORM_RENTAL = """\
form:
  name: ex/rental
  required: true
  instances: ex/rentals
  exports: [ex/net_income, ex/unit_list]
capabilities:
  - {name: ex/a, produces: {output: ex/net_income}}
"""

FORM_RENTAL_NAME_ONLY = """\
form:
  name: ex/rental
capabilities:
  - {name: ex/b, produces: {output: ex/unit_list}}
"""

FORM_BUSINESS = """\
form:
  name: ex/business
  required: true
  instances: ex/businesses
  exports: [ex/profit]
capabilities:
  - {name: ex/c, produces: {output: ex/profit}}
"""

RETURN_PART = """\
capabilities:
  - {name: ex/r, produces: {output: ex/y}}
"""

HEADER_PART = SCALARS + INPUTS + OUTPUTS


def selection_named(name: str, output: str) -> CapabilitySelection:
    return CapabilitySelection(name=name, params={}, consumes={}, produces={"output": output})


def part_path(directory: Path, name: str) -> Path:
    return directory / "ex-on" / "manifests" / "v1" / name


def test_a_manifest_without_a_form_key_has_no_forms(tmp_path: Path) -> None:
    write(tmp_path, "ex-on/manifests/v1.yaml", EX_ON_V1)

    assert others(only_manifest(tmp_path)) == ()


def test_a_part_with_a_form_key_gives_the_form_all_the_capabilities_of_that_part(
    tmp_path: Path,
) -> None:
    write_parts(
        tmp_path,
        {
            "00-header.yaml": HEADER_PART,
            "01-return.yaml": RETURN_PART,
            "02-rental.yaml": FORM_RENTAL,
        },
    )

    manifest = only_manifest(tmp_path)

    assert others(manifest) == (
        Form(
            required=True,
            name="ex/rental",
            instances="ex/rentals",
            exports=("ex/net_income", "ex/unit_list"),
            capabilities=(selection_named("ex/a", "ex/net_income"),),
        ),
    )
    assert returned(manifest).capabilities == (selection_named("ex/r", "ex/y"),)


def test_a_part_without_a_form_key_is_the_returns_whatever_its_neighbours_are(
    tmp_path: Path,
) -> None:
    write_parts(
        tmp_path,
        {
            "00-header.yaml": HEADER_PART,
            "01-rental.yaml": FORM_RENTAL,
            "02-return.yaml": RETURN_PART,
        },
    )

    assert returned(only_manifest(tmp_path)).capabilities == (selection_named("ex/r", "ex/y"),)


def test_a_form_may_span_parts_and_its_selections_follow_the_part_order(tmp_path: Path) -> None:
    write_parts(
        tmp_path,
        {
            "00-header.yaml": HEADER_PART,
            "01-rental.yaml": FORM_RENTAL,
            "02-rental-more.yaml": FORM_RENTAL_NAME_ONLY,
        },
    )

    (found,) = others(only_manifest(tmp_path))

    assert found.instances == "ex/rentals"
    assert found.exports == ("ex/net_income", "ex/unit_list")
    assert found.capabilities == (
        selection_named("ex/a", "ex/net_income"),
        selection_named("ex/b", "ex/unit_list"),
    )


def test_the_part_that_declares_the_form_need_not_be_the_first_of_its_parts(
    tmp_path: Path,
) -> None:
    write_parts(
        tmp_path,
        {
            "00-header.yaml": HEADER_PART,
            "01-rental-more.yaml": FORM_RENTAL_NAME_ONLY,
            "02-rental.yaml": FORM_RENTAL,
        },
    )

    (found,) = others(only_manifest(tmp_path))

    assert found.exports == ("ex/net_income", "ex/unit_list")
    assert [c.name for c in found.capabilities] == ["ex/b", "ex/a"]


def test_several_forms_are_kept_in_the_order_their_names_first_appear(tmp_path: Path) -> None:
    more = (
        "form:\n  name: ex/business\n"
        "capabilities:\n  - {name: ex/d, produces: {output: ex/profit_more}}\n"
    )
    write_parts(
        tmp_path,
        {
            "00-header.yaml": HEADER_PART,
            "01-business.yaml": FORM_BUSINESS,
            "02-rental.yaml": FORM_RENTAL,
            "03-business-more.yaml": more,
        },
    )

    business, rental = others(only_manifest(tmp_path))

    assert (business.name, rental.name) == ("ex/business", "ex/rental")
    assert [c.name for c in business.capabilities] == ["ex/c", "ex/d"]


@pytest.mark.parametrize(
    "extra", ["inputs: [{name: ex/rentals, required: true}]\n", "outputs: [ex/y]\n"]
)
def test_a_form_part_with_inputs_or_outputs_is_rejected_naming_the_part(
    tmp_path: Path, extra: str
) -> None:
    write_parts(tmp_path, {"00-header.yaml": HEADER_PART, "01-rental.yaml": FORM_RENTAL + extra})

    with pytest.raises(
        InvalidManifestError, match="form 'ex/rental'.*inputs are derived"
    ) as caught:
        source(tmp_path).get_jurisdiction(EX_ON)

    assert str(part_path(tmp_path, "01-rental.yaml")) in str(caught.value)


def test_a_form_part_with_no_capabilities_is_allowed(tmp_path: Path) -> None:
    declaration = FORM_RENTAL.partition("capabilities:")[0]
    write_parts(
        tmp_path,
        {
            "00-header.yaml": HEADER_PART,
            "01-rental.yaml": declaration,
            "02-rental-more.yaml": FORM_RENTAL_NAME_ONLY,
        },
    )

    (found,) = others(only_manifest(tmp_path))

    assert [c.name for c in found.capabilities] == ["ex/b"]


@pytest.mark.parametrize(
    ("form_text", "message"),
    [
        pytest.param(
            "form: {name: ex/rental, required: true, instances: ex/rentals, exports: [ex/n], "
            "extra: 1}\n",
            r"unknown keys \['extra'\]",
            id="unknown-key",
        ),
        pytest.param("form: ex/rental\n", "form must be a mapping", id="not-a-mapping"),
        pytest.param(
            "form: {instances: ex/rentals, exports: [ex/n]}\n",
            r"missing keys \['name'\]",
            id="no-name",
        ),
        pytest.param("form: {name: 7}\n", "name must be a string, got int", id="name-not-text"),
        pytest.param("form: {name: ''}\n", "name must not be empty", id="name-empty"),
        pytest.param(
            "form: {name: Rental, required: true, instances: ex/rentals, exports: [ex/n]}\n",
            "Rental",
            id="name-not-an-identifier",
        ),
        pytest.param(
            "form: {name: ex/rental.n, required: true, instances: ex/rentals, exports: [ex/n]}\n",
            r"ex/rental\.n",
            id="name-dotted",
        ),
        pytest.param(
            "form: {name: ex/rental, required: true, instances: [ex/rentals], exports: [ex/n]}\n",
            "instances must be a string, got list",
            id="instances-a-list",
        ),
        pytest.param(
            "form: {name: ex/rental, required: true, instances: ex/Rentals, exports: [ex/n]}\n",
            "ex/Rentals",
            id="instances-not-an-identifier",
        ),
        pytest.param(
            "form: {name: ex/rental, required: true, instances: ex/rentals, exports: ex/n}\n",
            "exports must be a list",
            id="exports-not-a-list",
        ),
        pytest.param(
            "form: {name: ex/rental, required: true, instances: ex/rentals, exports: [ex/n, 7]}\n",
            r"exports\[1\] must be a string, got int",
            id="export-element-wrong-type",
        ),
        pytest.param(
            "form: {name: ex/rental, required: true, instances: ex/rentals, exports: ['']}\n",
            r"exports\[0\] must not be empty",
            id="export-empty",
        ),
        pytest.param(
            "form: {name: ex/rental, required: true, instances: ex/rentals, exports: [ex/n, "
            "ex/n]}\n",
            r"exports\[1\]: 'ex/n' is listed more than once",
            id="export-repeated",
        ),
        pytest.param(
            "form: {name: ex/rental, required: true, instances: ex/rentals, exports: [ex/n, "
            "ca/n]}\n",
            "more than once",
            id="two-exports-of-one-local-id",
        ),
        pytest.param(
            "form: {name: ex/rental, required: true, instances: ex/rentals, "
            "exports: [ex/rental.n]}\n",
            r"ex/rental\.n",
            id="export-dotted",
        ),
        pytest.param(
            "form: {name: ex/rental, required: true, instances: ex/rentals, exports: []}\n",
            "exports must name at least one artifact",
            id="no-exports",
        ),
        pytest.param(
            "form: {name: ex/rental, instances: ex/rentals}\n",
            "form 'ex/rental'.*instances.*exports",
            id="instances-without-exports",
        ),
    ],
)
def test_a_bad_form_key_is_rejected_naming_the_part_file(
    tmp_path: Path, form_text: str, message: str
) -> None:
    write_parts(tmp_path, {"00-header.yaml": HEADER_PART, "01-bad.yaml": form_text})

    with pytest.raises(InvalidManifestError, match=message) as excinfo:
        source(tmp_path).get_jurisdiction(EX_ON)

    assert str(part_path(tmp_path, "01-bad.yaml")) in str(excinfo.value)


@pytest.mark.parametrize(
    "repeat",
    [
        "form: {name: ex/rental, required: true, instances: ex/rentals, exports: [ex/n]}\n",
        "form: {name: ex/rental, required: true, instances: ex/other, exports: [ex/m]}\n",
    ],
    ids=["same-declaration", "another-declaration"],
)
def test_a_second_part_that_declares_the_forms_instances_and_exports_is_rejected(
    tmp_path: Path, repeat: str
) -> None:
    write_parts(
        tmp_path,
        {"00-header.yaml": HEADER_PART, "01-rental.yaml": FORM_RENTAL, "02-again.yaml": repeat},
    )

    with pytest.raises(InvalidManifestError, match="form 'ex/rental'.*already") as caught:
        source(tmp_path).get_jurisdiction(EX_ON)

    message = str(caught.value)
    assert str(part_path(tmp_path, "02-again.yaml")) in message
    assert str(part_path(tmp_path, "01-rental.yaml")) in message


def test_a_form_declared_with_exports_alone_has_no_instances_list_and_one_instance(
    tmp_path: Path,
) -> None:
    alone = FORM_RENTAL.replace("  instances: ex/rentals\n", "")
    write_parts(tmp_path, {"00-header.yaml": HEADER_PART, "01-rental.yaml": alone})

    (found,) = others(only_manifest(tmp_path))

    assert found.instances is None
    assert found.exports == ("ex/net_income", "ex/unit_list")


def test_the_default_form_is_an_ordinary_form_named_return_in_the_namespace_first_of_the_forms(
    tmp_path: Path,
) -> None:
    write_parts(
        tmp_path,
        {
            "00-header.yaml": HEADER_PART,
            "01-rental.yaml": FORM_RENTAL,
            "02-return.yaml": RETURN_PART,
        },
    )

    default, rental = only_manifest(tmp_path).forms

    assert (default.name, default.instances) == ("ex-on/return", None)
    assert default.exports == ("ex/y",)
    assert rental.name == "ex/rental"


def test_a_form_no_part_declares_the_instances_of_is_rejected_naming_the_form(
    tmp_path: Path,
) -> None:
    write_parts(tmp_path, {"00-header.yaml": HEADER_PART, "01-rental.yaml": FORM_RENTAL_NAME_ONLY})

    with pytest.raises(InvalidManifestError, match="form 'ex/rental'.*exports"):
        source(tmp_path).get_jurisdiction(EX_ON)


def test_a_part_with_two_form_keys_is_rejected_naming_the_part_file(tmp_path: Path) -> None:
    write_parts(
        tmp_path,
        {"00-header.yaml": HEADER_PART, "01-bad.yaml": FORM_RENTAL + "form: {name: ex/business}\n"},
    )

    with pytest.raises(InvalidManifestError, match="01-bad.yaml"):
        source(tmp_path).get_jurisdiction(EX_ON)


def test_a_bad_selection_in_a_form_part_names_the_part_file(tmp_path: Path) -> None:
    bad = (
        "form: {name: ex/rental, required: true, instances: ex/rentals, exports: [ex/n]}\n"
        "capabilities:\n  - {name: ex/a}\n"
    )
    write_parts(tmp_path, {"00-header.yaml": HEADER_PART, "01-rental.yaml": bad})

    with pytest.raises(InvalidManifestError, match=r"capabilities\[0\]: missing keys") as caught:
        source(tmp_path).get_jurisdiction(EX_ON)

    assert str(part_path(tmp_path, "01-rental.yaml")) in str(caught.value)


def test_a_part_naming_the_return_form_is_rejected_naming_the_part(tmp_path: Path) -> None:
    named = FORM_RENTAL.replace("name: ex/rental", "name: ex-on/return")
    write_parts(tmp_path, {"00-header.yaml": HEADER_PART, "01-return.yaml": named})

    with pytest.raises(
        InvalidManifestError, match=r"ex-on/return.*reserved for the parts"
    ) as caught:
        source(tmp_path).get_jurisdiction(EX_ON)

    assert str(part_path(tmp_path, "01-return.yaml")) in str(caught.value)


def test_two_outputs_with_one_local_id_are_refused_as_outputs_not_exports(tmp_path: Path) -> None:
    clash = HEADER.replace("outputs: [ex/y]", "outputs: [ex/y, ca/y]")
    write(tmp_path, "ex-on/manifests/v1.yaml", clash + "capabilities: []\n")

    with pytest.raises(InvalidManifestError, match=r"outputs: local id 'y'.*more than once"):
        source(tmp_path).get_jurisdiction(EX_ON)


# --- forms: `max_instances`, `min_instances`, `exclusive_group` in the declaring part ----------
#
# These are optional keys of the `form:` mapping of the part that declares `exports`:
# `max_instances` an integer of at least 1, `min_instances` an integer of at least 0 (not above the
# maximum), `exclusive_group` an identifier. A part that does not declare exports takes none,
# and a second part repeating them is refused.


def limited(extra: str) -> str:
    return (
        "form:\n  name: ex/rental\n  required: true\n  instances: ex/rentals\n  exports: [ex/n]\n"
        f"{extra}capabilities:\n  - {{name: ex/a, produces: {{output: ex/n}}}}\n"
    )


def test_a_form_without_limits_has_none(tmp_path: Path) -> None:
    write_parts(tmp_path, {"00-header.yaml": HEADER_PART, "01-rental.yaml": FORM_RENTAL})

    (found,) = others(only_manifest(tmp_path))

    assert found.max_instances is None
    assert found.min_instances is None
    assert found.exclusive_group is None


def test_the_declaring_part_may_carry_a_maximum_and_a_group(tmp_path: Path) -> None:
    text = limited("  max_instances: 1\n  exclusive_group: ex/either\n")
    write_parts(tmp_path, {"00-header.yaml": HEADER_PART, "01-rental.yaml": text})

    (found,) = others(only_manifest(tmp_path))

    assert found.max_instances == 1
    assert found.exclusive_group == "ex/either"


def test_a_maximum_alone_and_a_group_alone_are_allowed(tmp_path: Path) -> None:
    write_parts(
        tmp_path,
        {
            "00-header.yaml": HEADER_PART,
            "01-rental.yaml": limited("  max_instances: 4\n"),
            "02-business.yaml": FORM_BUSINESS.replace(
                "  exports: [ex/profit]\n", "  exports: [ex/profit]\n  exclusive_group: ex/other\n"
            ),
        },
    )

    rental, business = others(only_manifest(tmp_path))

    assert (rental.max_instances, rental.exclusive_group) == (4, None)
    assert (business.max_instances, business.exclusive_group) == (None, "ex/other")


def test_the_limits_come_from_the_part_that_declares_them_whatever_its_place(
    tmp_path: Path,
) -> None:
    write_parts(
        tmp_path,
        {
            "00-header.yaml": HEADER_PART,
            "01-rental.yaml": FORM_RENTAL_NAME_ONLY,
            "02-declaration.yaml": limited("  max_instances: 2\n"),
        },
    )

    (found,) = others(only_manifest(tmp_path))

    assert found.max_instances == 2
    assert [c.name for c in found.capabilities] == ["ex/b", "ex/a"]


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        pytest.param(
            "  max_instances: 0\n",
            "form 'ex/rental': max_instances must be at least 1, got 0",
            id="zero",
        ),
        pytest.param(
            "  max_instances: -2\n",
            "form 'ex/rental': max_instances must be at least 1, got -2",
            id="neg",
        ),
        pytest.param(
            "  max_instances: '1'\n",
            "form\\.max_instances must be an integer, got str",
            id="str",
        ),
        pytest.param(
            "  max_instances: 1.5\n",
            "form\\.max_instances must be an integer, got float",
            id="float",
        ),
        pytest.param(
            "  max_instances: true\n",
            "form\\.max_instances must be an integer, got bool",
            id="bool",
        ),
        pytest.param(
            "  max_instances: [1]\n",
            "form\\.max_instances must be an integer, got list",
            id="list",
        ),
        pytest.param(
            "  min_instances: -1\n",
            "form 'ex/rental': min_instances must be at least 0, got -1",
            id="min-neg",
        ),
        pytest.param(
            "  min_instances: '1'\n",
            "form\\.min_instances must be an integer, got str",
            id="min-str",
        ),
        pytest.param(
            "  min_instances: true\n",
            "form\\.min_instances must be an integer, got bool",
            id="min-bool",
        ),
        pytest.param(
            "  min_instances: 1.5\n",
            "form\\.min_instances must be an integer, got float",
            id="min-float",
        ),
        pytest.param(
            "  min_instances: 3\n  max_instances: 2\n",
            "form 'ex/rental': min_instances 3 is above max_instances 2",
            id="min-above-max",
        ),
        pytest.param(
            "  exclusive_group: 7\n", "exclusive_group must be a string, got int", id="grp-int"
        ),
        pytest.param(
            "  exclusive_group: ''\n", "exclusive_group must not be empty", id="grp-empty"
        ),
        pytest.param(
            "  exclusive_group: either\n", "exclusive_group 'either'", id="grp-no-namespace"
        ),
        pytest.param(
            "  exclusive_group: ex/Either\n", "exclusive_group 'ex/Either'", id="grp-case"
        ),
        pytest.param(
            "  exclusive_group: [ex/a]\n", "exclusive_group must be a string", id="grp-list"
        ),
    ],
)
def test_a_bad_limit_is_rejected_naming_the_part_file(
    tmp_path: Path, extra: str, message: str
) -> None:
    write_parts(tmp_path, {"00-header.yaml": HEADER_PART, "01-bad.yaml": limited(extra)})

    with pytest.raises(InvalidManifestError, match=message) as caught:
        source(tmp_path).get_jurisdiction(EX_ON)

    assert str(part_path(tmp_path, "01-bad.yaml")) in str(caught.value)


def test_a_minimum_above_one_without_instances_is_rejected_naming_the_part(tmp_path: Path) -> None:
    text = (
        "form:\n  name: ex/rental\n  required: true\n  exports: [ex/n]\n  min_instances: 2\n"
        "capabilities:\n  - {name: ex/a, produces: {output: ex/n}}\n"
    )
    write_parts(tmp_path, {"00-header.yaml": HEADER_PART, "01-bad.yaml": text})

    with pytest.raises(
        InvalidManifestError,
        match=r"form 'ex/rental': min_instances 2 can never hold: "
        "a form without an instances list has one instance",
    ) as caught:
        source(tmp_path).get_jurisdiction(EX_ON)

    assert str(part_path(tmp_path, "01-bad.yaml")) in str(caught.value)


def test_the_declaring_part_may_carry_a_minimum_alone_or_with_a_maximum(tmp_path: Path) -> None:
    write_parts(
        tmp_path,
        {
            "00-header.yaml": HEADER_PART,
            "01-rental.yaml": limited("  min_instances: 2\n"),
            "02-business.yaml": FORM_BUSINESS.replace(
                "  exports: [ex/profit]\n",
                "  exports: [ex/profit]\n  min_instances: 0\n  max_instances: 3\n",
            ),
        },
    )

    rental, business = others(only_manifest(tmp_path))

    assert (rental.min_instances, rental.max_instances) == (2, None)
    assert (business.min_instances, business.max_instances) == (0, 3)


def test_exactly_one_instance_is_a_minimum_and_maximum_of_one(tmp_path: Path) -> None:
    write_parts(
        tmp_path,
        {
            "00-header.yaml": HEADER_PART,
            "01-rental.yaml": limited("  min_instances: 1\n  max_instances: 1\n"),
        },
    )

    (found,) = others(only_manifest(tmp_path))

    assert (found.min_instances, found.max_instances) == (1, 1)


def test_limits_are_accepted_on_a_form_without_instances(tmp_path: Path) -> None:
    text = (
        "form:\n  name: ex/rental\n  required: true\n  exports: [ex/n]\n  min_instances: 1\n"
        "  max_instances: 1\n"
        "  exclusive_group: ex/either\n"
        "capabilities:\n  - {name: ex/a, produces: {output: ex/n}}\n"
    )
    write_parts(tmp_path, {"00-header.yaml": HEADER_PART, "01-once.yaml": text})

    (found,) = others(only_manifest(tmp_path))

    assert found.instances is None
    assert (found.min_instances, found.max_instances) == (1, 1)
    assert found.exclusive_group == "ex/either"


@pytest.mark.parametrize(
    "key", ["max_instances: 1", "min_instances: 1", "exclusive_group: ex/either"]
)
def test_a_limit_in_a_part_that_does_not_declare_exports_is_rejected(
    tmp_path: Path, key: str
) -> None:
    name_only = (
        f"form:\n  name: ex/rental\n  {key}\n"
        "capabilities:\n  - {name: ex/b, produces: {output: ex/n}}\n"
    )
    write_parts(
        tmp_path,
        {"00-header.yaml": HEADER_PART, "01-rental.yaml": FORM_RENTAL, "02-more.yaml": name_only},
    )

    with pytest.raises(
        InvalidManifestError, match=r"form 'ex/rental'.*belongs to the part that declares exports"
    ) as caught:
        source(tmp_path).get_jurisdiction(EX_ON)

    assert str(part_path(tmp_path, "02-more.yaml")) in str(caught.value)
    assert key.split(":")[0] in str(caught.value)


@pytest.mark.parametrize(
    "key", ["max_instances: 1", "min_instances: 1", "exclusive_group: ex/either"]
)
def test_a_second_part_repeating_a_limit_is_rejected_like_a_repeated_declaration(
    tmp_path: Path, key: str
) -> None:
    again = (
        "form:\n  name: ex/rental\n  required: true\n  instances: ex/rentals\n  exports: [ex/n]\n"
        f"  {key}\n"
    )
    write_parts(
        tmp_path,
        {
            "00-header.yaml": HEADER_PART,
            "01-rental.yaml": limited(f"  {key}\n"),
            "02-again.yaml": again,
        },
    )

    with pytest.raises(InvalidManifestError, match="form 'ex/rental'.*already") as caught:
        source(tmp_path).get_jurisdiction(EX_ON)

    assert str(part_path(tmp_path, "02-again.yaml")) in str(caught.value)


def test_a_flat_manifest_file_still_takes_no_form_key_so_no_limits(tmp_path: Path) -> None:
    write(tmp_path, "ex-on/manifests/v1.yaml", EX_ON_V1 + "form: {name: ex/r, max_instances: 1}\n")

    with pytest.raises(InvalidManifestError, match="unknown keys"):
        source(tmp_path).get_jurisdiction(EX_ON)


def test_parses_the_blank_rules_of_a_selection(tmp_path: Path) -> None:
    write(
        tmp_path,
        "ex-on/manifests/v1.yaml",
        """\
        jurisdiction: EX-ON
        version: 1
        valid_from_tax_year: 2025
        inputs: [{name: ex/income, required: true}, {name: ex/deduction, required: true}]
        outputs: [ex/net]
        capabilities:
          - name: ex/subtract
            consumes:
              amount: ex/income
              less: ex/deduction
            blank:
              less: "0"
              amount: pass_on
            produces:
              output: ex/net
        """,
    )

    manifest = source(tmp_path).get_jurisdiction(EX_ON).manifests[0]

    (selection,) = returned(manifest).capabilities
    assert selection.blank == {"less": "0", "amount": "pass_on"}


def test_a_selection_without_blank_rules_has_none(tmp_path: Path) -> None:
    write(tmp_path, "ex-on/manifests/v1.yaml", EX_ON_V1)

    manifest = source(tmp_path).get_jurisdiction(EX_ON).manifests[0]

    assert all(not each.blank for each in returned(manifest).capabilities)


def test_blank_rules_must_be_a_mapping_of_strings(tmp_path: Path) -> None:
    write(
        tmp_path,
        "ex-on/manifests/v1.yaml",
        HEADER
        + """\
capabilities:
  - name: ex/subtract
    consumes: {amount: ex/x}
    blank: [less]
    produces: {output: ex/y}
""",
    )

    with pytest.raises(InvalidManifestError, match="blank"):
        source(tmp_path).get_jurisdiction(EX_ON)


# --- required, defaults, predicates and fields ---------------------------------------------------
#
# Every input, form and field of a form's instances says `required: true` or `required: false`;
# nothing is implicit. An optional input or field also has a `default:` written as the value (`null`
# for blank, a quoted figure, `[]`, `""`) and a `basis:` quoting the form. An optional form has a
# `required_when:` naming a yes/no and a `basis:`; a required form has neither. These belong to the
# part that declares the form's exports.

OPTIONAL_FORM = """\
form:
  name: ex/relief
  required: false
  required_when: ex/relief_applies
  basis: "Complete this form if you claim relief"
  exports: [ex/relief_amount]
capabilities:
  - {name: ex/a, produces: {output: ex/relief_amount}}
"""

PREDICATE_INPUT = """\
inputs:
  - {name: ex/relief_applies, required: true}
"""


def load_parts(directory: Path, parts: Mapping[str, str]) -> Manifest:
    write_parts(directory, {"00-header.yaml": SCALARS + OUTPUTS + "capabilities: []\n", **parts})
    return only_manifest(directory)


def refused(directory: Path, parts: Mapping[str, str], message: str) -> str:
    write_parts(directory, {"00-header.yaml": SCALARS + OUTPUTS + "capabilities: []\n", **parts})
    with pytest.raises(InvalidManifestError, match=message) as excinfo:
        source(directory).get_jurisdiction(EX_ON)
    return str(excinfo.value)


def test_an_input_declares_whether_it_is_required_and_optional_ones_a_default_and_a_basis(
    tmp_path: Path,
) -> None:
    manifest = load_parts(
        tmp_path,
        {
            "01-inputs.yaml": """\
                inputs:
                  - {name: ex/income, required: true}
                  - {name: ex/credit, required: false, default: "0", basis: "Line 1"}
                  - {name: ex/note, required: false, default: "", basis: "Line 2"}
                  - {name: ex/rows, required: false, default: [], basis: "Line 3"}
                  - {name: ex/box, required: false, default: null, basis: "Line 4"}
                """.replace("                ", "")
        },
    )

    assert manifest.inputs == {
        "ex/income": InputDeclaration(name="ex/income", required=True),
        "ex/credit": InputDeclaration("ex/credit", False, Default("0"), "Line 1"),
        "ex/note": InputDeclaration("ex/note", False, Default(""), "Line 2"),
        "ex/rows": InputDeclaration("ex/rows", False, Default(()), "Line 3"),
        "ex/box": InputDeclaration("ex/box", False, Default(None), "Line 4"),
    }


def test_an_input_that_omits_required_is_refused_naming_it_and_the_part(tmp_path: Path) -> None:
    message = refused(tmp_path, {"01-inputs.yaml": "inputs:\n  - {name: ex/income}\n"}, "ex/income")

    assert "input 'ex/income': required must be declared true or false" in message
    assert str(part_path(tmp_path, "01-inputs.yaml")) in message


def test_an_input_written_as_a_bare_identifier_is_refused(tmp_path: Path) -> None:
    refused(tmp_path, {"01-inputs.yaml": "inputs: [ex/income]\n"}, r"inputs\[0\] must be a mapping")


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ("{name: ex/c, required: false, basis: 'Line 1'}", "input 'ex/c': .* needs a default"),
        ("{name: ex/c, required: false, default: '0'}", "input 'ex/c': .* needs a basis"),
        ("{name: ex/c, required: true, default: '0'}", "input 'ex/c': a required input takes no"),
        (
            "{name: ex/c, required: true, basis: 'Line 1'}",
            "input 'ex/c': a required input takes no",
        ),
        ("{name: ex/c, required: maybe}", r"inputs\[0\].required must be true or false"),
        ("{name: ex/c, required: 'true'}", r"inputs\[0\].required must be true or false"),
        (
            "{name: ex/c, required: false, default: 0, basis: 'L'}",
            r"default must be null, a quoted",
        ),
        (
            "{name: ex/c, required: false, default: [1], basis: 'L'}",
            r"default must be null, a quoted",
        ),
        ("{name: ex/c, required: false, default: '0', basis: ''}", r"basis must not be empty"),
        ("{name: ex/c, required: true, extra: 1}", r"unknown keys \['extra'\]"),
        ("{required: true}", r"missing keys \['name'\]"),
    ],
)
def test_a_contradictory_or_malformed_input_declaration_is_refused(
    tmp_path: Path, entry: str, message: str
) -> None:
    refused(tmp_path, {"01-inputs.yaml": f"inputs:\n  - {entry}\n"}, message)


def test_an_input_declared_in_two_parts_is_still_refused(tmp_path: Path) -> None:
    parts = {"01-a.yaml": PREDICATE_INPUT, "02-b.yaml": PREDICATE_INPUT}

    refused(tmp_path, parts, "'ex/relief_applies' is already listed in")


def test_an_optional_form_declares_its_predicate_and_its_basis(tmp_path: Path) -> None:
    manifest = load_parts(
        tmp_path, {"01-inputs.yaml": PREDICATE_INPUT, "02-form.yaml": OPTIONAL_FORM}
    )

    (found,) = others(manifest)
    assert (found.required, found.required_when) == (False, "ex/relief_applies")
    assert found.basis == "Complete this form if you claim relief"


def test_the_default_form_is_required(tmp_path: Path) -> None:
    manifest = load_parts(tmp_path, {"01-inputs.yaml": INPUTS, "02-a.yaml": CAPABILITIES_A})

    assert returned(manifest).required is True
    assert (returned(manifest).required_when, returned(manifest).fields) == (None, ())


def test_a_form_that_omits_required_is_refused_naming_it_and_the_part(tmp_path: Path) -> None:
    text = OPTIONAL_FORM.replace("  required: false\n", "")

    message = refused(
        tmp_path, {"01-inputs.yaml": PREDICATE_INPUT, "02-form.yaml": text}, "ex/relief"
    )

    assert "form 'ex/relief': required must be declared true or false" in message
    assert str(part_path(tmp_path, "02-form.yaml")) in message


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            ("  required_when: ex/relief_applies\n", ""),
            "form 'ex/relief': .* needs a required_when",
        ),
        (
            ('  basis: "Complete this form if you claim relief"\n', ""),
            "form 'ex/relief': .* needs a basis",
        ),
        (("required: false", "required: true"), "form 'ex/relief': a required form takes no"),
        (("required: false", "required: 0"), r"required must be true or false"),
        (
            ("required_when: ex/relief_applies", "required_when: ex/relief_amount"),
            "is one of its own exports",
        ),
        (
            ("required_when: ex/relief_applies", "required_when: ex/unknown"),
            "form 'ex/relief': required_when 'ex/unknown' is not a required input",
        ),
        (("required_when: ex/relief_applies", "required_when: ''"), "must not be empty"),
    ],
)
def test_a_contradictory_or_unknown_form_requirement_is_refused(
    tmp_path: Path, change: tuple[str, str], message: str
) -> None:
    text = OPTIONAL_FORM.replace(*change)

    refused(tmp_path, {"01-inputs.yaml": PREDICATE_INPUT, "02-form.yaml": text}, message)


def test_a_predicate_that_is_an_optional_input_is_refused(tmp_path: Path) -> None:
    optional_input = (
        "inputs:\n  - {name: ex/relief_applies, required: false, default: '0', basis: 'Line 1'}\n"
    )

    refused(
        tmp_path,
        {"01-inputs.yaml": optional_input, "02-form.yaml": OPTIONAL_FORM},
        "'ex/relief_applies' is an optional input",
    )


def test_a_predicate_may_be_produced_by_a_selection(tmp_path: Path) -> None:
    answers = """\
form:
  name: ex/answers
  required: true
  exports: [ex/relief_applies]
capabilities:
  - {name: ex/answer, produces: {output: ex/relief_applies}}
"""

    manifest = load_parts(
        tmp_path,
        {"01-inputs.yaml": INPUTS, "02-answers.yaml": answers, "03-form.yaml": OPTIONAL_FORM},
    )

    assert [form.required_when for form in others(manifest)] == [None, "ex/relief_applies"]


@pytest.mark.parametrize("key", ["required", "required_when", "basis", "fields"])
def test_a_requirement_key_in_a_part_that_does_not_declare_exports_is_rejected(
    tmp_path: Path, key: str
) -> None:
    value = {
        "required": "true",
        "required_when": "ex/relief_applies",
        "basis": "'Line 1'",
        "fields": "[]",
    }
    declaring = OPTIONAL_FORM
    beside = f"form:\n  name: ex/relief\n  {key}: {value[key]}\n"

    message = refused(
        tmp_path,
        {"01-inputs.yaml": PREDICATE_INPUT, "02-form.yaml": declaring, "03-more.yaml": beside},
        f"form 'ex/relief': {key} belongs to the part that declares exports",
    )

    assert str(part_path(tmp_path, "03-more.yaml")) in message


def test_a_form_with_instances_declares_its_fields_like_inputs(tmp_path: Path) -> None:
    text = """\
form:
  name: ex/rental
  required: true
  instances: ex/rentals
  exports: [ex/n]
  fields:
    - {name: ex/gross_rent, required: true}
    - {name: ex/expenses, required: false, default: "0", basis: "Line 2"}
capabilities:
  - {name: ex/a, produces: {output: ex/n}}
"""

    (found,) = others(load_parts(tmp_path, {"01-inputs.yaml": INPUTS, "02-form.yaml": text}))

    assert found.fields == (
        InputDeclaration(name="ex/gross_rent", required=True),
        InputDeclaration("ex/expenses", False, Default("0"), "Line 2"),
    )


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ("[{name: ex/gross_rent}]", "input 'ex/gross_rent': required must be declared"),
        ("[{name: ex/g, required: false, basis: 'L'}]", "input 'ex/g': .* needs a default"),
        (
            "[{name: ex/g, required: true}, {name: ex/g, required: true}]",
            r"fields\[1\]: 'ex/g' is listed more than once",
        ),
        ("ex/gross_rent", "fields must be a list"),
    ],
)
def test_a_bad_field_declaration_is_refused(tmp_path: Path, fields: str, message: str) -> None:
    text = f"""\
form:
  name: ex/rental
  required: true
  instances: ex/rentals
  exports: [ex/n]
  fields: {fields}
capabilities:
  - {{name: ex/a, produces: {{output: ex/n}}}}
"""

    refused(tmp_path, {"01-inputs.yaml": INPUTS, "02-form.yaml": text}, message)


def test_fields_on_a_form_without_instances_are_refused(tmp_path: Path) -> None:
    text = OPTIONAL_FORM.replace(
        "  exports: [ex/relief_amount]\n",
        "  exports: [ex/relief_amount]\n  fields: [{name: ex/x, required: true}]\n",
    )

    refused(
        tmp_path,
        {"01-inputs.yaml": PREDICATE_INPUT, "02-form.yaml": text},
        "form 'ex/relief': fields belong to a form with instances",
    )
