"""Unit tests for CapabilitySelection and Manifest.

A selection is one capability chosen by a manifest, with its slots filled: `params` maps parameter
slots to families; `consumes` and `produces` map artifact slots to artifact identifiers. All are
kept as strings (the registries resolve them later) in read-only mappings. A manifest is a flat
set of `forms`, peers that together are the return, and the computation's `inputs`, a non-empty
frozenset of artifact identifiers. A form's `exports` (what the old manifest called `outputs`) may
include an input, carried onto the return as entered. Names are made up.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal
from types import MappingProxyType
from typing import Any, cast

import pytest

from tax_engine.domain.artifact import ArtifactKind, ArtifactRegistry
from tax_engine.domain.digits import DigitsKind
from tax_engine.domain.errors import InvalidManifestError
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import (
    CapabilitySelection,
    Default,
    Form,
    InputDeclaration,
    Manifest,
)
from tax_engine.domain.record_list import RecordListKind
from tests.manifest_support import required_inputs


def selection() -> CapabilitySelection:
    return CapabilitySelection(
        name="ex/progressive_tax",
        params={"schedule": "ex/brackets"},
        consumes={"base": "ex/taxable_base"},
        produces={"output": "ex/levy"},
    )


def test_holds_its_name_and_slot_bindings() -> None:
    chosen = selection()

    assert chosen.name == "ex/progressive_tax"
    assert chosen.params == {"schedule": "ex/brackets"}
    assert chosen.consumes == {"base": "ex/taxable_base"}
    assert chosen.produces == {"output": "ex/levy"}


def test_has_no_params_family() -> None:
    assert [field.name for field in dataclasses.fields(CapabilitySelection)] == [
        "name",
        "params",
        "consumes",
        "produces",
        "blank",
    ]


def test_blank_rules_default_to_none_and_are_read_only() -> None:
    assert selection().blank == {}
    chosen = CapabilitySelection(
        name="ex/x", params={}, consumes={}, produces={"output": "ex/y"}, blank={"less": "0"}
    )

    assert chosen.blank == {"less": "0"}
    assert isinstance(chosen.blank, MappingProxyType)
    assert hash(chosen) != hash(selection())


def test_slot_bindings_are_read_only() -> None:
    chosen = selection()

    for bindings in (chosen.params, chosen.consumes, chosen.produces, chosen.blank):
        assert isinstance(bindings, MappingProxyType)
        with pytest.raises(TypeError):
            cast(Any, bindings)["extra"] = "ex/other"


def test_slot_bindings_are_copied_from_what_it_was_given() -> None:
    params = {"schedule": "ex/brackets"}
    chosen = CapabilitySelection(
        name="ex/progressive_tax", params=params, consumes={}, produces={"output": "ex/levy"}
    )

    params["schedule"] = "ex/other"

    assert chosen.params == {"schedule": "ex/brackets"}


def test_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        cast(Any, selection()).name = "ex/other"


def test_selections_with_the_same_bindings_are_equal() -> None:
    assert selection() == selection()
    assert selection() != dataclasses.replace(selection(), produces={"output": "ex/other"})


def test_a_selection_may_bind_no_parameters_and_consume_nothing() -> None:
    chosen = CapabilitySelection(
        name="ex/flat_grant", params={}, consumes={}, produces={"output": "ex/grant"}
    )

    assert chosen.params == {}
    assert chosen.consumes == {}


def test_equal_selections_hash_alike() -> None:
    assert hash(selection()) == hash(selection())
    assert len({selection(), selection()}) == 1


def manifest(
    inputs: frozenset[str] = frozenset({"ex/taxable_base"}),
    outputs: tuple[str, ...] = ("ex/levy",),
) -> Manifest:
    return Manifest(
        jurisdiction=JurisdictionCode("EX-ON"),
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(inputs),
        forms=(
            Form(
                required=True,
                name="ex-on/return",
                instances=None,
                exports=outputs,
                capabilities=(selection(),),
            ),
        ),
    )


def test_manifest_holds_its_inputs_and_its_forms() -> None:
    found = manifest(inputs=frozenset({"ex/taxable_base", "ex/gross_income"}), outputs=("ex/levy",))

    assert found.inputs.keys() == frozenset({"ex/taxable_base", "ex/gross_income"})
    (only,) = found.forms
    assert only.name == "ex-on/return"
    assert only.exports == ("ex/levy",)
    assert only.capabilities == (selection(),)


def test_manifest_fields_in_order() -> None:
    assert [field.name for field in dataclasses.fields(Manifest)] == [
        "jurisdiction",
        "version",
        "valid_from_tax_year",
        "inputs",
        "forms",
    ]


def test_equal_manifests_are_equal_and_hash_alike() -> None:
    assert manifest() == manifest()
    assert hash(manifest()) == hash(manifest())
    assert manifest() != manifest(outputs=("ex/other",))


def test_manifest_rejects_empty_inputs() -> None:
    with pytest.raises(InvalidManifestError, match="inputs must name at least one artifact"):
        manifest(inputs=frozenset())


def test_manifest_rejects_no_forms() -> None:
    with pytest.raises(InvalidManifestError, match="forms must name at least one form"):
        dataclasses.replace(manifest(), forms=())


def test_manifest_accepts_an_identifier_that_is_both_input_and_export() -> None:
    found = manifest(inputs=frozenset({"ex/taxable_base", "ex/levy"}), outputs=("ex/levy",))

    assert found.inputs.keys() == frozenset({"ex/taxable_base", "ex/levy"})
    assert found.forms[0].exports == ("ex/levy",)


# --- list slots: a consumed slot filled with a list of identifiers ------------------------------


def listing(parts: Any) -> CapabilitySelection:
    return CapabilitySelection(
        name="ex/total_up",
        params={},
        consumes={"base": "ex/taxable_base", "parts": parts},
        produces={"total": "ex/total"},
    )


def test_a_consumed_slot_may_hold_a_list_of_identifiers_kept_as_a_tuple() -> None:
    chosen = listing(["ex/a", "ex/b", "ex/c"])

    assert chosen.consumes == {"base": "ex/taxable_base", "parts": ("ex/a", "ex/b", "ex/c")}
    assert isinstance(chosen.consumes["parts"], tuple)
    assert isinstance(chosen.consumes["base"], str)


def test_a_list_of_identifiers_keeps_its_order() -> None:
    assert listing(["ex/c", "ex/a", "ex/b"]).consumes["parts"] == ("ex/c", "ex/a", "ex/b")


def test_a_list_of_identifiers_may_be_empty() -> None:
    assert listing([]).consumes["parts"] == ()


def test_a_list_of_identifiers_is_copied_from_what_it_was_given() -> None:
    parts = ["ex/a", "ex/b"]
    chosen = listing(parts)

    parts.append("ex/c")

    assert chosen.consumes["parts"] == ("ex/a", "ex/b")


def test_selections_with_list_slots_compare_and_hash_by_value() -> None:
    assert listing(["ex/a", "ex/b"]) == listing(("ex/a", "ex/b"))
    assert listing(["ex/a", "ex/b"]) != listing(["ex/b", "ex/a"])
    assert hash(listing(["ex/a", "ex/b"])) == hash(listing(("ex/a", "ex/b")))
    assert len({listing(["ex/a", "ex/b"]), listing(("ex/a", "ex/b"))}) == 1


# --- forms: a named group of selections with its instances kind and its exports ---------------
#
# A `Form` is manifest data beside `CapabilitySelection`, not a capability: its `name`, the
# `instances` identifier of the record-list kind the caller supplies (one record per instance),
# the `exports` it produces as `<form>.<export>` artifacts, and its `capabilities`. All of them
# are plain identifiers `<namespace>/<snake_case>`: the dotted `<form>.<export>` is built by the
# engine, never written in a manifest.


def form(
    name: str = "ex/rental",
    instances: str | None = "ex/rentals",
    exports: Any = ("ex/net_income", "ex/unit_list"),
    capabilities: Any = None,
    **limits: Any,
) -> Form:
    return Form(
        required=True,
        name=name,
        instances=instances,
        exports=exports,
        capabilities=(selection(),) if capabilities is None else capabilities,
        **limits,
    )


def test_a_form_holds_its_name_instances_exports_and_selections() -> None:
    found = form()

    assert found.name == "ex/rental"
    assert found.instances == "ex/rentals"
    assert found.exports == ("ex/net_income", "ex/unit_list")
    assert found.capabilities == (selection(),)


def test_form_fields_in_order() -> None:
    assert [field.name for field in dataclasses.fields(Form)] == [
        "name",
        "instances",
        "exports",
        "capabilities",
        "required",
        "max_instances",
        "min_instances",
        "exclusive_group",
        "required_when",
        "basis",
        "fields",
    ]


def test_a_form_is_not_a_capability_selection() -> None:
    assert not issubclass(Form, CapabilitySelection)


def test_exports_and_capabilities_are_kept_as_tuples_copied_from_what_was_given() -> None:
    exports = ["ex/net_income"]
    chosen = [selection()]
    found = form(exports=exports, capabilities=chosen)

    exports.append("ex/other")
    chosen.clear()

    assert found.exports == ("ex/net_income",)
    assert found.capabilities == (selection(),)
    assert isinstance(found.exports, tuple)
    assert isinstance(found.capabilities, tuple)


def test_a_form_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        cast(Any, form()).name = "ex/other"


def test_equal_forms_are_equal_and_hash_alike() -> None:
    assert form() == form()
    assert hash(form()) == hash(form())
    assert len({form(), form()}) == 1
    assert form() != form(exports=("ex/net_income",))
    assert form() != form(instances="ex/other")


@pytest.mark.parametrize("field", ["name", "instances"])
@pytest.mark.parametrize(
    "bad", ["", "rental", "ex/Rental", "ex/rental.net_income", "ex/a/b", "ex/", "/rental"]
)
def test_a_form_name_and_instances_are_plain_namespaced_identifiers(field: str, bad: str) -> None:
    with pytest.raises(InvalidManifestError, match=field):
        form(**{field: bad})


def test_a_form_may_have_no_instances_list_and_then_has_one_instance() -> None:
    found = form(instances=None)

    assert found.instances is None
    assert found != form()


@pytest.mark.parametrize(
    "bad", ["", "net_income", "ex/NetIncome", "ex/rental.net_income", "ex/a/b"]
)
def test_an_export_is_a_plain_namespaced_identifier(bad: str) -> None:
    with pytest.raises(InvalidManifestError, match="exports"):
        form(exports=("ex/net_income", bad))


def test_a_form_must_export_something() -> None:
    with pytest.raises(InvalidManifestError, match="exports must name at least one artifact"):
        form(exports=())


@pytest.mark.parametrize(
    "exports", [("ex/net_income", "ex/net_income"), ("ex/net_income", "ca/net_income")]
)
def test_two_exports_with_the_same_local_id_are_refused(exports: tuple[str, ...]) -> None:
    # Both would be produced as `ex/rental.net_income`.
    with pytest.raises(InvalidManifestError, match=r"net_income.*more than once"):
        form(exports=exports)


# A form may limit its instances: `max_instances` (at least 1; `None` for no maximum) and an
# `exclusive_group` identifier `<namespace>/<snake_case>` (`None` for no group).


def test_a_form_has_no_maximum_and_no_group_by_default() -> None:
    assert form().max_instances is None
    assert form().exclusive_group is None


def test_a_form_holds_its_maximum_and_group() -> None:
    found = form(max_instances=1, exclusive_group="ex/either")

    assert found.max_instances == 1
    assert found.exclusive_group == "ex/either"
    assert found != form()
    assert hash(found) == hash(form(max_instances=1, exclusive_group="ex/either"))


@pytest.mark.parametrize("bad", [0, -1])
def test_a_maximum_below_one_is_refused(bad: int) -> None:
    with pytest.raises(InvalidManifestError, match=rf"max_instances must be at least 1, got {bad}"):
        form(max_instances=bad)


@pytest.mark.parametrize("bad", [1.5, "1", True])
def test_a_maximum_that_is_not_an_integer_is_refused(bad: object) -> None:
    with pytest.raises(InvalidManifestError, match="max_instances must be an integer"):
        form(max_instances=bad)


@pytest.mark.parametrize("bad", ["", "either", "ex/Either", "ex/a.b", "ex/a/b", "ex/"])
def test_a_group_is_a_plain_namespaced_identifier(bad: str) -> None:
    with pytest.raises(InvalidManifestError, match="exclusive_group"):
        form(exclusive_group=bad)


def test_a_form_has_no_minimum_by_default() -> None:
    assert form().min_instances is None


@pytest.mark.parametrize(
    "limit",
    [{"max_instances": 1}, {"min_instances": 1}, {"exclusive_group": "ex/either"}],
)
def test_a_limit_is_accepted_on_a_form_without_instances(limit: dict[str, Any]) -> None:
    # Such a form has a default instance list of one instance; the limits apply to that count.
    assert form(instances=None, **limit).instances is None


@pytest.mark.parametrize(
    "limits",
    [
        {"min_instances": 0},
        {"min_instances": 2},
        {"min_instances": 2, "max_instances": 5},
        {"min_instances": 1, "max_instances": 1},
        {"min_instances": 3, "max_instances": 3},
    ],
)
def test_a_form_holds_its_minimum_beside_a_maximum(limits: dict[str, Any]) -> None:
    found = form(**limits)

    assert found.min_instances == limits["min_instances"]
    assert found.max_instances == limits.get("max_instances")
    assert hash(found) == hash(form(**limits))


def test_a_minimum_above_the_maximum_is_refused_naming_the_form() -> None:
    with pytest.raises(
        InvalidManifestError, match=r"form 'ex/rental': min_instances 3 is above max_instances 2"
    ):
        form(min_instances=3, max_instances=2)


def test_a_negative_minimum_is_refused() -> None:
    with pytest.raises(
        InvalidManifestError, match=r"form 'ex/rental': min_instances must be at least 0, got -1"
    ):
        form(min_instances=-1)


@pytest.mark.parametrize("bad", [1.5, "1", True])
def test_a_minimum_that_is_not_an_integer_is_refused(bad: object) -> None:
    with pytest.raises(
        InvalidManifestError, match="form 'ex/rental': min_instances must be an integer"
    ):
        form(min_instances=bad)


def test_a_minimum_above_one_without_instances_is_refused_naming_the_form() -> None:
    with pytest.raises(
        InvalidManifestError,
        match=r"^form 'ex/rental': min_instances 2 can never hold: "
        "a form without an instances list has one instance$",
    ):
        form(instances=None, min_instances=2)


def test_manifest_fields_end_with_forms() -> None:
    assert [field.name for field in dataclasses.fields(Manifest)][-1] == "forms"


def test_a_manifest_holds_its_forms_as_a_tuple_in_order() -> None:
    other = form(name="ex/business", instances="ex/businesses", exports=("ex/profit",))
    found = dataclasses.replace(manifest(), forms=cast(Any, [form(), other]))

    assert found.forms == (form(), other)
    assert isinstance(found.forms, tuple)


def test_manifests_with_other_forms_differ_and_equal_ones_hash_alike() -> None:
    with_form = dataclasses.replace(manifest(), forms=(form(),))

    assert with_form != manifest()
    assert with_form == dataclasses.replace(manifest(), forms=(form(),))
    assert hash(with_form) == hash(dataclasses.replace(manifest(), forms=(form(),)))


def test_a_manifest_refuses_two_forms_of_one_name() -> None:
    again = form(instances="ex/others", exports=("ex/profit",))

    with pytest.raises(InvalidManifestError, match="ex/rental.*more than once"):
        dataclasses.replace(manifest(), forms=(form(), again))


# --- the default form is an ordinary form ------------------------------------------------------
#
# Nothing in a manifest singles out the form of the return: it is named `<namespace>/return` by
# the loader's convention only, and is one of `forms` like any other, so a manifest of forms that
# are all named otherwise is as good.


def test_a_manifest_needs_no_form_named_return() -> None:
    other = form(name="ex/rental", instances=None, exports=("ex/profit",))

    assert dataclasses.replace(manifest(), forms=(other,)).forms == (other,)


def test_a_form_named_return_is_refused_only_as_a_second_of_that_name() -> None:
    clash = form(name="ex-on/return", instances="ex/rentals", exports=("ex/profit",))

    with pytest.raises(InvalidManifestError, match="ex-on/return.*more than once"):
        dataclasses.replace(manifest(), forms=(*manifest().forms, clash))


# --- required, defaults and predicates -----------------------------------------------------------
#
# Every input, every field of a form's instances and every form says whether it is required. A
# required one takes no default; an optional input or field declares its default, written as the
# value (`Default(None)` is blank), and the printed sentence that justifies it as its `basis`. An
# optional form names a yes/no in `required_when`, with its own basis; a required form has neither.


def optional(name: str = "ex/credit", default: Default | None = None) -> InputDeclaration:
    return InputDeclaration(
        name=name,
        required=False,
        default=Default("0") if default is None else default,
        basis="Line 1: enter 0 if none",
    )


def test_a_required_input_takes_no_default_and_no_basis() -> None:
    assert InputDeclaration(name="ex/income", required=True).default is None

    with pytest.raises(InvalidManifestError, match="input 'ex/income': a required input takes no"):
        InputDeclaration(name="ex/income", required=True, default=Default("0"))
    with pytest.raises(InvalidManifestError, match="input 'ex/income': a required input takes no"):
        InputDeclaration(name="ex/income", required=True, basis="Line 1")


def test_an_optional_input_needs_a_default_and_a_basis() -> None:
    with pytest.raises(InvalidManifestError, match="input 'ex/credit': .* needs a default"):
        InputDeclaration(name="ex/credit", required=False, basis="Line 1")
    with pytest.raises(InvalidManifestError, match="input 'ex/credit': .* needs a basis"):
        InputDeclaration(name="ex/credit", required=False, default=Default("0"))
    with pytest.raises(InvalidManifestError, match="input 'ex/credit': .* needs a basis"):
        InputDeclaration(name="ex/credit", required=False, default=Default("0"), basis="")


@pytest.mark.parametrize("value", [None, "0", "", "375.03", ()])
def test_a_default_is_blank_text_a_figure_or_an_empty_list(value: str | tuple[()] | None) -> None:
    assert optional(default=Default(value)).default == Default(value)


@pytest.mark.parametrize("value", [0, 1.5, True, ("a",), ["x"]])
def test_a_default_of_any_other_type_is_refused(value: Any) -> None:
    with pytest.raises(InvalidManifestError, match="default must be null, a string or an empty"):
        Default(value)


def test_an_input_is_named_by_an_identifier() -> None:
    with pytest.raises(InvalidManifestError, match="input 'Credit'"):
        InputDeclaration(name="Credit", required=True)


AMOUNT = ArtifactKind("ex/amount", Decimal)
LEVY = ArtifactKind("ex/levy_amount", Decimal, non_negative=True)
COUNT = ArtifactKind("ex/count", int, non_negative=True)
ROWS = RecordListKind("ex/rows", fields=(AMOUNT, COUNT))
NOTE = ArtifactKind("ex/note", str)
BUSINESS_NUMBER = DigitsKind("ex/business_number", digits=9)


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        (AMOUNT, "0"),
        (AMOUNT, "-12.50"),
        (LEVY, "375.03"),
        (COUNT, "0"),
        (ROWS, ()),
        (NOTE, ""),
        (BUSINESS_NUMBER, ""),
        (BUSINESS_NUMBER, "123456789"),
        (AMOUNT, None),
        (ROWS, None),
        (COUNT, None),
    ],
)
def test_a_default_that_suits_its_kind_is_accepted(
    kind: ArtifactKind[Any], value: str | tuple[()] | None
) -> None:
    optional(default=Default(value)).check_kind(kind)


@pytest.mark.parametrize(
    ("kind", "value", "problem"),
    [
        (AMOUNT, "abc", "must be a plain decimal number"),
        (AMOUNT, "NaN", "must be a plain decimal number"),
        (AMOUNT, "1e5", "must be a plain decimal number"),
        (AMOUNT, " 5", "must be a plain decimal number"),
        (AMOUNT, (), "must be a quoted number"),
        (LEVY, "-1", "must not be below zero"),
        (COUNT, "1.5", "must be a whole number"),
        (COUNT, "1" * 5000, "is too long to read as a number"),
        (COUNT, "-1", "must not be below zero"),
        (ROWS, "0", "must be an empty list"),
        (NOTE, (), "must be a string"),
        (BUSINESS_NUMBER, "abc", "must be 9 digits"),
        (BUSINESS_NUMBER, "12345", "must be 9 digits"),
    ],
)
def test_a_default_that_does_not_suit_its_kind_is_refused_naming_the_input(
    kind: ArtifactKind[Any], value: str | tuple[()], problem: str
) -> None:
    with pytest.raises(InvalidManifestError, match=f"input 'ex/credit': default .* {problem}"):
        optional(default=Default(value)).check_kind(kind)


def optional_form(**changes: Any) -> Form:
    fields: dict[str, Any] = {
        "name": "ex/relief",
        "instances": None,
        "exports": ("ex/relief_amount",),
        "capabilities": (),
        "required": False,
        "required_when": "ex/relief_applies",
        "basis": "Complete this form if you claim relief",
    }
    return Form(**{**fields, **changes})


def test_an_optional_form_holds_its_predicate_and_its_basis() -> None:
    found = optional_form()

    assert (found.required, found.required_when) == (False, "ex/relief_applies")
    assert found.basis == "Complete this form if you claim relief"


def test_a_required_form_takes_no_predicate_and_no_basis() -> None:
    with pytest.raises(InvalidManifestError, match="form 'ex/relief': a required form takes no"):
        optional_form(required=True)
    with pytest.raises(InvalidManifestError, match="form 'ex/relief': a required form takes no"):
        optional_form(required=True, required_when=None)


def test_an_optional_form_needs_a_predicate_and_a_basis() -> None:
    with pytest.raises(InvalidManifestError, match="form 'ex/relief': .* needs a required_when"):
        optional_form(required_when=None)
    with pytest.raises(InvalidManifestError, match="form 'ex/relief': .* needs a basis"):
        optional_form(basis=None)


def test_a_predicate_is_an_identifier() -> None:
    with pytest.raises(InvalidManifestError, match="required_when 'Applies'"):
        optional_form(required_when="Applies")


@pytest.mark.parametrize("predicate", ["ex/relief_amount"])
def test_a_form_may_not_be_gated_by_its_own_export(predicate: str) -> None:
    with pytest.raises(InvalidManifestError, match="is one of its own exports"):
        optional_form(required_when=predicate)


def test_fields_belong_to_a_form_with_instances_and_are_declared_once() -> None:
    with pytest.raises(InvalidManifestError, match="fields belong to a form with instances"):
        optional_form(fields=(optional(),))

    found = optional_form(instances="ex/rows", fields=(optional("ex/amount"), optional("ex/count")))

    assert [declared.name for declared in found.fields] == ["ex/amount", "ex/count"]
    with pytest.raises(InvalidManifestError, match="field 'ex/amount' is declared twice"):
        optional_form(instances="ex/rows", fields=(optional("ex/amount"), optional("ex/amount")))


def with_forms(*forms: Form, inputs: dict[str, InputDeclaration] | None = None) -> Manifest:
    default = Form(
        required=True,
        name="ex-on/return",
        instances=None,
        exports=("ex/levy",),
        capabilities=(selection(),),
    )
    return Manifest(
        jurisdiction=JurisdictionCode("EX-ON"),
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(["ex/taxable_base", "ex/relief_applies"])
        if inputs is None
        else inputs,
        forms=(default, *forms),
    )


def test_a_predicate_may_be_a_required_input() -> None:
    assert with_forms(optional_form()).forms[1].required_when == "ex/relief_applies"


def test_a_predicate_may_be_produced_by_a_selection() -> None:
    answer = CapabilitySelection(
        name="ex/answer", params={}, consumes={}, produces={"output": "ex/relief_applies"}
    )
    produced = optional_form(name="ex/other", exports=("ex/other_amount",), capabilities=(answer,))
    inputs = required_inputs(["ex/taxable_base"])

    assert with_forms(produced, optional_form(), inputs=inputs).forms[2].name == "ex/relief"


def test_a_predicate_nothing_declares_or_produces_is_refused_naming_the_form() -> None:
    with pytest.raises(InvalidManifestError, match="form 'ex/relief': required_when 'ex/nope'"):
        with_forms(optional_form(required_when="ex/nope"))


def test_a_predicate_that_is_an_optional_input_is_refused() -> None:
    inputs = required_inputs(["ex/taxable_base"]) | {
        "ex/relief_applies": optional("ex/relief_applies")
    }

    with pytest.raises(InvalidManifestError, match="'ex/relief_applies' is an optional input"):
        with_forms(optional_form(), inputs=inputs)


def test_an_input_must_be_declared_under_its_own_name() -> None:
    with pytest.raises(InvalidManifestError, match="input 'ex/a' is declared as 'ex/b'"):
        with_forms(inputs={"ex/a": InputDeclaration(name="ex/b", required=True)})


def test_equal_manifests_with_declarations_hash_alike() -> None:
    first = with_forms(optional_form())

    assert first == with_forms(optional_form())
    assert hash(first) == hash(with_forms(optional_form()))
    assert first != with_forms(optional_form(basis="Complete this form if you owe"))


def registry(*kinds: ArtifactKind[Any]) -> ArtifactRegistry:
    found = ArtifactRegistry()
    for kind in kinds:
        found.register(kind.identifier, kind)
    return found


def test_the_artifacts_are_checked_for_defaults_fields_and_predicates() -> None:
    applies = ArtifactKind("ex/relief_applies", int, non_negative=True)
    amount = ArtifactKind("ex/relief_amount", Decimal)
    rows = RecordListKind("ex/rows", fields=(AMOUNT, COUNT))
    gated = optional_form(instances="ex/rows", fields=(optional("ex/amount"), optional("ex/count")))
    inputs = required_inputs(["ex/relief_applies"]) | {"ex/amount": optional("ex/amount")}
    known = registry(applies, amount, rows, AMOUNT, COUNT)

    with_forms(gated, inputs=inputs).check_artifacts(known)


def test_a_field_of_the_instances_kind_the_form_does_not_declare_is_refused() -> None:
    gated = optional_form(instances="ex/rows", fields=(optional("ex/amount"),))
    known = registry(ArtifactKind("ex/relief_applies", int, non_negative=True), ROWS)

    with pytest.raises(InvalidManifestError, match="field 'ex/count' of 'ex/rows' is not declared"):
        with_forms(gated, inputs=required_inputs(["ex/relief_applies"])).check_artifacts(known)


def test_a_declared_field_the_instances_kind_does_not_have_is_refused() -> None:
    extra = (optional("ex/amount"), optional("ex/count"), optional("ex/ghost"))
    gated = optional_form(instances="ex/rows", fields=extra)
    known = registry(ArtifactKind("ex/relief_applies", int, non_negative=True), ROWS)

    with pytest.raises(InvalidManifestError, match="field 'ex/ghost' is not a field of 'ex/rows'"):
        with_forms(gated, inputs=required_inputs(["ex/relief_applies"])).check_artifacts(known)


def test_a_field_default_must_suit_the_field_kind() -> None:
    bad = optional("ex/count", Default("1.5"))
    gated = optional_form(instances="ex/rows", fields=(optional("ex/amount"), bad))
    known = registry(ArtifactKind("ex/relief_applies", int, non_negative=True), ROWS)

    with pytest.raises(InvalidManifestError, match="input 'ex/count': default .* whole number"):
        with_forms(gated, inputs=required_inputs(["ex/relief_applies"])).check_artifacts(known)


@pytest.mark.parametrize(
    "kind",
    [ArtifactKind("ex/relief_applies", Decimal), ArtifactKind("ex/relief_applies", int)],
)
def test_a_predicate_that_is_not_a_yes_no_count_is_refused(kind: ArtifactKind[Any]) -> None:
    with pytest.raises(InvalidManifestError, match="required_when 'ex/relief_applies' is not a"):
        with_forms(optional_form(), inputs=required_inputs(["ex/relief_applies"])).check_artifacts(
            registry(kind)
        )
