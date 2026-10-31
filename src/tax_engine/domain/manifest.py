"""Jurisdiction manifest: which capabilities run for a jurisdiction, and from which tax year.

A manifest selects capabilities and fills their slots (design.md §4): parameter slots with
families, artifact slots with artifact identifiers. The slots themselves are declared in code.
A manifest is a flat set of forms, peers that together are the return (a form is a named group of
selections with the artifacts it exports), and the declarations of the artifacts the computation
starts from. Every form, input and field of a form's instances says whether it is required, and an
optional input or field declares its default and basis; the YAML spelling is the loader's.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any

from tax_engine.domain.artifact import ArtifactKind, ArtifactRegistry
from tax_engine.domain.errors import (
    InvalidManifestError,
    InvalidRegistrationError,
    InvalidTextError,
)
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.record_list import RecordList, RecordListKind
from tax_engine.domain.registry import Namespace

# A number's spelling in manifest text, the same as a blank rule's fallback (capability_builder).
_DECIMAL_NUMBER = re.compile(r"-?[0-9]+(\.[0-9]+)?")
_WHOLE_NUMBER = re.compile(r"-?[0-9]+")


@dataclass(frozen=True, slots=True)
class CapabilitySelection:
    """One capability chosen by a manifest, with its slots filled by identifier.

    `params` maps parameter slots to families; `consumes` and `produces` map artifact slots to
    artifact identifiers, and a consumed slot may instead map to a list of identifiers, kept in
    order as a tuple. `blank` maps a consumed slot to what a blank in it does: the text of the
    fallback value taken in its place, or `pass_on`; a slot not named refuses a blank. Each is
    kept as a read-only copy of what it was given.
    """

    name: str
    params: Mapping[str, str]
    consumes: Mapping[str, str | tuple[str, ...]]
    produces: Mapping[str, str]
    blank: Mapping[str, str] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("params", "produces", "blank"):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))
        # A list of identifiers becomes a tuple, so the selection stays frozen and hashable.
        consumes = {
            slot: named if isinstance(named, str) else tuple(named)
            for slot, named in self.consumes.items()
        }
        object.__setattr__(self, "consumes", MappingProxyType(consumes))

    def __hash__(self) -> int:
        """Hash by value, like the frozen dataclass it is; the read-only mappings are unhashable."""
        bindings = (self.params, self.consumes, self.produces, self.blank)
        return hash((self.name, *(frozenset(mapping.items()) for mapping in bindings)))


@dataclass(frozen=True, slots=True)
class Default:
    """The value an optional input or field takes when the request leaves it out.

    Written in the manifest as the actual value: `None` for blank (carried downstream as a line
    left out), a quoted decimal such as `"0"` or a printed figure, `()` for an empty list, or
    text such as `""`. It is the wrapper that tells a declared blank from no default at all.
    """

    value: str | tuple[()] | None

    def __post_init__(self) -> None:
        if self.value is not None and not isinstance(self.value, str) and self.value != ():
            raise InvalidManifestError(
                f"default must be null, a string or an empty list, got {self.value!r}"
            )


@dataclass(frozen=True, slots=True)
class InputDeclaration:
    """How a manifest declares one input, or one field of a form's instances list.

    `required` says whether every request must give it. A required one takes no `default` and no
    `basis`; an optional one declares both: `default` is what the request is read as when it
    leaves the line out (`Default(None)` is blank, not "no default"), and `basis` is the printed
    sentence of the form that justifies the default, which nothing checks against the form text.
    """

    name: str
    required: bool
    default: Default | None = None
    basis: str | None = None

    def __post_init__(self) -> None:
        Form.check_identifier("input", self.name)
        if self.required:
            for key, value in (("default", self.default), ("basis", self.basis)):
                if value is not None:
                    raise InvalidManifestError(
                        f"input {self.name!r}: a required input takes no {key}"
                    )
            return
        if self.default is None:
            raise InvalidManifestError(f"input {self.name!r}: an optional input needs a default")
        if not self.basis:
            raise InvalidManifestError(f"input {self.name!r}: an optional input needs a basis")

    def check_kind(self, kind: ArtifactKind[Any]) -> None:
        """Refuse a default that no value of `kind` could be: blank is any kind's.

        A `Decimal` kind takes a decimal string (not below zero if the kind is non-negative), an
        `int` kind a whole-number string, a record-list kind `()` and any other kind a string.
        """
        if self.default is None or self.default.value is None:
            return
        value = self.default.value
        problem: str | None = None
        if kind.value_type is Decimal:
            problem = self._decimal_problem(value, kind.non_negative, whole=False)
        elif kind.value_type is int:
            problem = self._decimal_problem(value, kind.non_negative, whole=True)
        elif kind.value_type is RecordList:
            problem = None if value == () else "must be an empty list"
        elif not isinstance(value, str):
            problem = "must be a string"
        else:
            try:
                kind.check_value(value)  # a digits kind takes only its own digits, or blank
            except InvalidTextError as exc:
                problem = f"is not a value of the kind: {exc}"
        if problem is not None:
            raise InvalidManifestError(
                f"input {self.name!r}: default {value!r} {problem} for the kind {kind.identifier!r}"
            )

    @staticmethod
    def _decimal_problem(value: str | tuple[()], non_negative: bool, *, whole: bool) -> str | None:
        if not isinstance(value, str):
            return "must be a quoted number"
        pattern = _WHOLE_NUMBER if whole else _DECIMAL_NUMBER
        if not pattern.fullmatch(value):
            return "must be a whole number" if whole else "must be a plain decimal number"
        try:
            number = Decimal(int(value)) if whole else Decimal(value)
        except (InvalidOperation, ValueError):
            # Python refuses a whole number of more than 4300 digits.
            return "is too long to read as a number"
        if non_negative and number < 0:
            return "must not be below zero"
        return None


@dataclass(frozen=True, slots=True)
class Form:
    """A named group of selections run once per instance, with the artifacts it exports.

    A form is a peer of the others, not a capability: `instances` is the identifier of the
    record-list kind the caller supplies, one record per instance, or `None` for a form without an
    instances list, which has one instance; `exports` are the identifiers of the artifacts the form
    produces, each readable by every form (itself aside) as `<name>.<local id of the export>`. All
    are plain identifiers
    `<namespace>/<snake_case>`: the dotted identifier is built by the engine, never written.
    `exports` and `capabilities` (the form's selections) are kept as tuples copied from what was
    given. The inputs of a form are not declared: they are derived from its selections.

    `required` says whether the return must include the form. An optional form names the yes/no
    artifact that says when it is needed in `required_when` (the machine form of its printed
    "Complete this form if ..." sentence, which is kept as `basis`); a required form has neither,
    and an optional form may not be gated by one of its own exports. A form with an instances list
    declares each field of its records in `fields` (a field of a required form or of an attached
    optional form is required only when the form is attached); a form without one has no fields.

    A form without `instances` has a default instance list of one instance, and the limits apply to
    its count. `max_instances` is the most instances a caller may give (an integer of at least 1;
    `None` for no maximum) and `min_instances` the fewest (an integer of at least 0, 0 meaning no
    minimum; `None` for none); the minimum may not be above the maximum. `exclusive_group` is an
    identifier shared by forms of which at most one may have instances (`None` for no group).
    """

    name: str
    instances: str | None
    exports: tuple[str, ...]
    capabilities: tuple[CapabilitySelection, ...]
    required: bool
    max_instances: int | None = None
    min_instances: int | None = None
    exclusive_group: str | None = None
    required_when: str | None = None
    basis: str | None = None
    fields: tuple[InputDeclaration, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "exports", tuple(self.exports))
        object.__setattr__(self, "capabilities", tuple(self.capabilities))
        object.__setattr__(self, "fields", tuple(self.fields))
        self.check_identifier("name", self.name)
        if self.instances is not None:
            self.check_identifier("instances", self.instances)
        if not self.exports:
            raise InvalidManifestError("exports must name at least one artifact")
        self.check_exports("exports", self.exports)
        try:
            self.check_limits(self.max_instances, self.min_instances, self.instances is not None)
        except InvalidManifestError as exc:
            raise InvalidManifestError(f"form {self.name!r}: {exc}") from None
        if self.exclusive_group is not None:
            self.check_identifier("exclusive_group", self.exclusive_group)
        self._check_requirement()
        self._check_fields()

    def _check_requirement(self) -> None:
        if self.required:
            for key, value in (("required_when", self.required_when), ("basis", self.basis)):
                if value is not None:
                    raise InvalidManifestError(
                        f"form {self.name!r}: a required form takes no {key}"
                    )
            return
        if self.required_when is None:
            raise InvalidManifestError(
                f"form {self.name!r}: an optional form needs a required_when"
            )
        if not self.basis:
            raise InvalidManifestError(f"form {self.name!r}: an optional form needs a basis")
        self.check_identifier("required_when", self.required_when)
        if self.required_when in self.exports:
            raise InvalidManifestError(
                f"form {self.name!r}: required_when {self.required_when!r} is one of its own "
                "exports"
            )

    def _check_fields(self) -> None:
        if self.fields and self.instances is None:
            raise InvalidManifestError(
                f"form {self.name!r}: fields belong to a form with instances"
            )
        names = [declared.name for declared in self.fields]
        for name in names:
            if names.count(name) > 1:
                raise InvalidManifestError(f"form {self.name!r}: field {name!r} is declared twice")

    @staticmethod
    def check_limits(
        max_instances: object, min_instances: object, has_instances_list: bool
    ) -> None:
        """Refuse limits no instance count could satisfy; the message does not name the form.

        Each given limit must be an integer (a boolean is not): `max_instances` at least 1,
        `min_instances` at least 0 and not above the maximum. A form without an instances list has
        one instance, so a `min_instances` above 1 can never hold.
        """
        for field, value, least in (
            ("max_instances", max_instances, 1),
            ("min_instances", min_instances, 0),
        ):
            if value is None:
                continue
            if not isinstance(value, int) or isinstance(value, bool):
                raise InvalidManifestError(
                    f"{field} must be an integer, got {type(value).__name__}"
                )
            if value < least:
                raise InvalidManifestError(f"{field} must be at least {least}, got {value}")
        if (
            isinstance(min_instances, int)
            and isinstance(max_instances, int)
            and min_instances > max_instances
        ):
            raise InvalidManifestError(
                f"min_instances {min_instances} is above max_instances {max_instances}"
            )
        if isinstance(min_instances, int) and min_instances > 1 and not has_instances_list:
            raise InvalidManifestError(
                f"min_instances {min_instances} can never hold: "
                "a form without an instances list has one instance"
            )

    @staticmethod
    def check_exports(field: str, exports: Iterable[str]) -> None:
        """Refuse an identifier that is malformed or repeats a local id, naming `field`."""
        local_ids: set[str] = set()
        for export in exports:
            Form.check_identifier(field, export)
            local_id = export.partition("/")[2]
            if local_id in local_ids:
                raise InvalidManifestError(
                    f"{field}: local id {local_id!r} is listed more than once"
                )
            local_ids.add(local_id)

    @staticmethod
    def check_identifier(field: str, identifier: str) -> None:
        """Refuse an identifier that is not `<namespace>/<snake_case>`, naming `field`."""
        namespace, _, local_id = identifier.partition("/")
        try:
            Namespace(namespace).identifier(local_id)
        except InvalidRegistrationError as exc:
            raise InvalidManifestError(f"{field} {identifier!r}: {exc}") from None


@dataclass(frozen=True, slots=True)
class Manifest:
    """One structural version of a jurisdiction's composition.

    `forms` are the peers that together are the return, in a tuple of at least one form with
    distinct names. `inputs` declare the artifacts a computation starts from, by identifier and
    once each: a non-empty mapping, among them the instances kind of each form, which the caller
    supplies with the rest. Each form's own inputs are derived from its selections. The
    `required_when` of an optional form names a required input, an artifact one of the manifest's
    selections produces; that it is a yes/no
    is checked with the artifact kinds by `check_artifacts`.
    """

    jurisdiction: JurisdictionCode
    version: int
    valid_from_tax_year: int
    inputs: Mapping[str, InputDeclaration]
    forms: tuple[Form, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "inputs", MappingProxyType(dict(self.inputs)))
        object.__setattr__(self, "forms", tuple(self.forms))
        if not self.forms:
            raise InvalidManifestError("forms must name at least one form")
        names = [found.name for found in self.forms]
        for name in names:
            if names.count(name) > 1:
                raise InvalidManifestError(f"form {name!r} is listed more than once")
        if not self.inputs:
            raise InvalidManifestError("inputs must name at least one artifact")
        for name, declaration in self.inputs.items():
            if declaration.name != name:
                raise InvalidManifestError(f"input {name!r} is declared as {declaration.name!r}")
        self._check_predicates()

    def __hash__(self) -> int:
        """Hash by value, like the frozen dataclass it is; the read-only mapping is unhashable."""
        return hash(
            (
                self.jurisdiction,
                self.version,
                self.valid_from_tax_year,
                frozenset(self.inputs.items()),
                self.forms,
            )
        )

    def check_artifacts(self, artifacts: ArtifactRegistry) -> None:
        """Refuse what only the artifact kinds can say, naming the input or form.

        Every default must suit its input's kind; the fields of a form must be, both ways, those
        of the record-list kind it takes as instances, with defaults to suit them; and the
        `required_when` of a form must be a yes/no, a non-negative count (1 for yes, 0 for no).
        The forms' exports are registered before this is called.
        """
        for name, declaration in self.inputs.items():
            declaration.check_kind(artifacts.kind(name))
        for form in self.forms:
            if form.instances is not None:
                self._check_fields(form, artifacts.kind(form.instances))
            if form.required_when is not None:
                kind = artifacts.kind(form.required_when)
                if kind.value_type is not int or not kind.non_negative:
                    raise InvalidManifestError(
                        f"form {form.name!r}: required_when {form.required_when!r} is not a "
                        "yes/no: it must be a count, 1 for yes and 0 for no"
                    )

    @staticmethod
    def _check_fields(form: Form, instances: ArtifactKind[Any]) -> None:
        if not isinstance(instances, RecordListKind):
            return  # the composition refuses instances that are not a record list
        kinds = {kind.identifier: kind for kind in instances.fields}
        declared = {declaration.name: declaration for declaration in form.fields}
        for name in sorted(kinds.keys() - declared.keys()):
            raise InvalidManifestError(
                f"form {form.name!r}: field {name!r} of {instances.identifier!r} is not declared "
                "in the manifest"
            )
        for name in sorted(declared.keys() - kinds.keys()):
            raise InvalidManifestError(
                f"form {form.name!r}: field {name!r} is not a field of {instances.identifier!r}"
            )
        for name, declaration in declared.items():
            declaration.check_kind(kinds[name])

    def _check_predicates(self) -> None:
        """Refuse a `required_when` that names nothing the manifest has or an optional input."""
        required = {name for name, declaration in self.inputs.items() if declaration.required}
        produced = {
            identifier
            for form in self.forms
            for selection in form.capabilities
            for identifier in selection.produces.values()
        }
        for form in self.forms:
            predicate = form.required_when
            if predicate is None or predicate in required | produced:
                continue
            if predicate in self.inputs:
                raise InvalidManifestError(
                    f"form {form.name!r}: required_when {predicate!r} is an optional input, "
                    "and the filer always answers a yes/no"
                )
            raise InvalidManifestError(
                f"form {form.name!r}: required_when {predicate!r} is not a required input "
                "or produced by a selection"
            )
