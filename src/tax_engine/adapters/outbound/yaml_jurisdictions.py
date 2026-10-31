"""Reads jurisdictions from YAML manifest files. Implements JurisdictionSource.

The source takes a mapping of namespace -> jurisdiction package directory. A jurisdiction's
namespace is its code lower-cased (`EX-ON` -> `ex-on`). Each `*.yaml` / `*.yml` file directly in
`<roots[ex-on]>/manifests/` is one whole manifest, and each subfolder there is one manifest too,
merged from its parts: every `*.yaml` / `*.yml` file inside it (recursively), read in sorted path
order. A part may carry any of the six manifest keys or a `form:` key; the scalar keys
(`jurisdiction`, `version`, `valid_from_tax_year`) must each be in exactly one part, and the lists
(`inputs`, `outputs`, `capabilities`) are concatenated in part order, an identifier listed in two
parts of `inputs` or of `outputs` being rejected. The merged mapping then goes through the same
parse as a whole file. A manifest naming another jurisdiction is rejected.
A manifest is a flat set of forms. A part with a `form:` key (`name`, and `exports` with an optional
`instances`, all identifiers `<namespace>/<snake_case>`) gives all its `capabilities` to that
form; without `instances` the form has one instance. A part without one joins the default
form, named `<namespace>/return` and otherwise an ordinary form: its exports are the
manifest's `outputs`. A form may span parts that carry the same `form.name`, in part order:
exactly one of them declares `exports` (with its `instances`), and a second that does is rejected.
A form without `instances` has a default list of one instance, and limits apply to its count.
That part may also declare `max_instances` (an integer of at least 1), `min_instances` (an integer
of at least 0, not above `max_instances`) and `exclusive_group` (an identifier): the most and the
fewest instances the form may have, and a group of forms of which at most one may have instances.
Any of these keys in a part that does not declare `exports`, or repeated by a second part, is
rejected.
A part with a `form:` key takes no `inputs` or `outputs`: inputs are derived, exports are declared
in the `form:` block. The default form's name is reserved for the parts without a `form:` key; a
`form:` part naming it is rejected, naming the part. The default form's `outputs` are its exports,
so two with one local id (`ex/x` and `ca/x`, both `<ns>/return.x`) are rejected as "outputs".
A single manifest file is not a part and takes no `form:` key: all of it is the default form.
Each selection names a capability and fills its slots: `params` (slot -> family, optional),
`consumes` (slot -> artifact identifier, or a list of them kept in order as a tuple, optional)
`blank` (consumed slot -> what a blank in it does: the text of a fallback value, or `pass_on`;
optional, a slot not named refuses a blank) and `produces` (slot -> artifact identifier,
required, at least one). Slot names, and whether a
slot takes one identifier or a list, are not checked against capability classes here.
The top-level `outputs` list the default form's exports: a required, non-empty list of non-empty
strings without duplicates (an identifier in both `inputs` and `outputs` is an input carried onto
the return as entered).
Every input says whether it is required: `inputs` is a required, non-empty list of mappings with
`name` and `required` (`true` or `false`, nothing implicit; a bare identifier is rejected). An
optional input also declares `default` and `basis`: `default` is written as the value the request
is read as when it leaves the line out (`null` for blank, a quoted figure such as `"0"`, `[]`, or
`""`), and must be present even when `null`; `basis` is the printed sentence of the form that
justifies it, which the loader keeps but does not check. A required input takes neither.
A `form:` block that declares `exports` also declares `required` (`true` or `false`) and, for an
optional form, `required_when` (the identifier of the yes/no artifact that says when the form is
needed: a required input or an artifact a selection produces, never one of its own exports) and
`basis` (the printed "Complete this form if" sentence); a required form takes neither. A form with
`instances` lists `fields`, one mapping per field of the instances kind, declared like inputs
(`name`, `required`, and for an optional one `default` and `basis`); a form without `instances` has
none. Which fields the instances kind has, that defaults suit their kinds and that a predicate is a
yes/no count are checked when the manifest is composed (`Manifest.check_artifacts`), where the
kinds are known.
Any of these keys in a part that does not declare `exports` is rejected. The default form is
always required.
Parsing is strict because a manifest must stay selection plus slot bindings
(design.md §4): unknown keys, duplicate keys and wrongly typed values are
rejected with the offending file (for a folder, the offending part) named, never coerced or
ignored.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import NamedTuple

import yaml

from tax_engine.adapters.outbound.yaml_support import YamlNode, YamlShapeError
from tax_engine.domain.errors import (
    InvalidJurisdictionCodeError,
    InvalidManifestError,
    NotFoundError,
)
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

_MANIFEST_KEYS = frozenset(
    {"jurisdiction", "version", "valid_from_tax_year", "inputs", "outputs", "capabilities"}
)
_PART_KEYS = _MANIFEST_KEYS | {"form"}
_FORM_KEYS = frozenset({"name"})
_OPTIONAL_FORM_KEYS = frozenset(
    {
        "instances",
        "exports",
        "max_instances",
        "min_instances",
        "exclusive_group",
        "required",
        "required_when",
        "basis",
        "fields",
    }
)
_OPTIONAL_INPUT_KEYS = frozenset({"default", "basis"})
_DEFAULT_FORM = "return"
_CAPABILITY_KEYS = frozenset({"name", "produces"})
_OPTIONAL_CAPABILITY_KEYS = frozenset({"params", "consumes", "blank"})
_SCALAR_KEYS = ("jurisdiction", "version", "valid_from_tax_year")
_IDENTIFIER_LISTS = ("inputs", "outputs")
_PATTERNS = ("*.yaml", "*.yml")


class _Declaration(NamedTuple):
    """What the one part of a form that declares its instances and exports declares."""

    instances: str | None
    exports: tuple[str, ...]
    max_instances: int | None
    min_instances: int | None
    exclusive_group: str | None
    required: bool
    required_when: str | None
    basis: str | None
    fields: tuple[InputDeclaration, ...]

    def form(self, name: str, selections: tuple[CapabilitySelection, ...]) -> Form:
        """The form `name` with this declaration and `selections`, which checks the declaration."""
        return Form(
            name=name,
            instances=self.instances,
            exports=self.exports,
            capabilities=selections,
            max_instances=self.max_instances,
            min_instances=self.min_instances,
            exclusive_group=self.exclusive_group,
            required=self.required,
            required_when=self.required_when,
            basis=self.basis,
            fields=self.fields,
        )


class YamlJurisdictionSource:
    """Jurisdictions read from the `manifests/` directory of each jurisdiction package."""

    def __init__(self, roots: Mapping[Namespace, Path]) -> None:
        """Read manifests under each namespace's package directory in `roots`."""
        self._roots = dict(roots)

    def get_jurisdiction(self, code: JurisdictionCode) -> Jurisdiction:
        """The jurisdiction with every manifest in its package; see JurisdictionSource."""
        manifests = tuple(self._load_all(code))
        if not manifests:
            raise NotFoundError(f"no manifests for jurisdiction {code} in {self._manifests(code)}")
        return Jurisdiction(code=code, manifests=manifests)

    def _load_all(self, code: JurisdictionCode) -> list[Manifest]:
        manifests = self._manifests(code)
        if not manifests.parent.is_dir():
            raise InvalidManifestError(f"package directory not found: {manifests.parent}")
        if not manifests.is_dir():
            return []
        paths = sorted(
            p
            for p in manifests.iterdir()
            if (p.is_dir() and self._parts(p))
            or (p.is_file() and any(p.match(pattern) for pattern in _PATTERNS))
        )
        return [self._load_for(code, path) for path in paths]

    def _manifests(self, code: JurisdictionCode) -> Path:
        namespace = code.namespace
        if namespace not in self._roots:
            raise NotFoundError(
                f"no jurisdiction {code}: no jurisdiction package declares namespace "
                f"{namespace.name!r}"
            )
        return self._roots[namespace] / "manifests"

    @classmethod
    def _load_for(cls, code: JurisdictionCode, path: Path) -> Manifest:
        manifest = cls.load(path)
        if manifest.jurisdiction != code:
            raise InvalidManifestError(
                f"{path}: manifest is for {manifest.jurisdiction}, but its package is {code}'s"
            )
        return manifest

    @classmethod
    def load(cls, path: Path) -> Manifest:
        """The manifest in the file `path`, or merged from the parts in the folder `path`."""
        if path.is_dir():
            return cls._load_folder(path)
        try:
            document = YamlNode.load(path, "manifest")
        except (OSError, yaml.YAMLError) as exc:
            raise InvalidManifestError(f"{path}: {exc}") from exc
        try:
            return cls._manifest(document)
        except (InvalidManifestError, YamlShapeError) as exc:
            raise InvalidManifestError(f"{path}: {exc}") from exc

    @staticmethod
    def _parts(folder: Path) -> list[Path]:
        """The `*.yaml` / `*.yml` files under `folder`, in sorted path order."""
        return sorted(p for pattern in _PATTERNS for p in folder.rglob(pattern) if p.is_file())

    @classmethod
    def _load_folder(cls, folder: Path) -> Manifest:
        parts = cls._parts(folder)
        merged: dict[str, object] = {}
        scalar_owners: dict[str, Path] = {}
        lists: dict[str, list[object]] = {}
        form_selections: dict[str, list[CapabilitySelection]] = {}
        declarations: dict[str, tuple[Path, _Declaration]] = {}
        identifier_owners: dict[str, dict[str, Path]] = {key: {} for key in _IDENTIFIER_LISTS}
        for part in parts:
            contents = cls._part(part)
            if "form" in contents:
                cls._join_form(part, contents, form_selections, declarations)
            for key, node in contents.items():
                if key in _SCALAR_KEYS:
                    if key in scalar_owners:
                        raise InvalidManifestError(
                            f"{part}: key {key!r} is already set in {scalar_owners[key]}"
                        )
                    scalar_owners[key] = part
                    merged[key] = node.value
                else:
                    cls._claim_identifiers(key, node, part, identifier_owners.get(key, {}))
                    lists.setdefault(key, []).extend(item.value for item in node.items())
        if form_selections:
            lists.setdefault("capabilities", [])  # the default form may have none beside the others
        try:
            return cls._manifest(
                YamlNode.root({**merged, **lists}, "manifest"),
                lambda default: tuple(
                    cls._form(name, selections, declarations, default)
                    for name, selections in form_selections.items()
                ),
            )
        except (InvalidManifestError, YamlShapeError) as exc:
            raise InvalidManifestError(f"{folder}: {exc}") from exc

    @classmethod
    def _join_form(
        cls,
        part: Path,
        contents: dict[str, YamlNode],
        form_selections: dict[str, list[CapabilitySelection]],
        declarations: dict[str, tuple[Path, _Declaration]],
    ) -> None:
        """Give the `capabilities` of a part with a `form:` key to its form, noting its declaration.

        Takes `form` and `capabilities` out of `contents`; a second part declaring the exports of
        a form is rejected, naming the part that did.
        """
        name, declared = cls._form_header(contents.pop("form"))
        if contents.keys() & set(_IDENTIFIER_LISTS):
            raise InvalidManifestError(
                f"{part}: form {name!r}: inputs are derived and exports are declared in the "
                "form: block, so the part takes no `inputs` or `outputs`"
            )
        chosen = form_selections.setdefault(name, [])
        if declared is not None:
            if name in declarations:
                raise InvalidManifestError(
                    f"{part}: form {name!r}: exports are already declared in "
                    f"{declarations[name][0]}"
                )
            declarations[name] = (part, declared)
        if "capabilities" in contents:
            chosen.extend(cls._selection(entry) for entry in contents.pop("capabilities").items())

    @staticmethod
    def _form(
        name: str,
        selections: list[CapabilitySelection],
        declarations: dict[str, tuple[Path, _Declaration]],
        default: str,
    ) -> Form:
        """The form `name` of the selections of all its parts and its one declaration."""
        if name not in declarations:
            raise InvalidManifestError(f"form {name!r}: no part declares its exports")
        part, declared = declarations[name]
        if name == default:
            raise InvalidManifestError(
                f"{part}: form {name!r}: the name is reserved for the parts without a `form:` key"
            )
        return declared.form(name, tuple(selections))

    @classmethod
    def _form_header(cls, node: YamlNode) -> tuple[str, _Declaration | None]:
        """The name of a part's form and, if it declares them, its instances, exports and limits."""
        node.require_mapping(_FORM_KEYS, optional=_OPTIONAL_FORM_KEYS)
        name = node.field("name").require_non_empty_string()
        Form.check_identifier("name", name)
        instances = node.optional_field("instances")
        exports = node.optional_field("exports")
        maximum = node.optional_field("max_instances")
        minimum = node.optional_field("min_instances")
        group = node.optional_field("exclusive_group")
        required = node.optional_field("required")
        required_when = node.optional_field("required_when")
        basis = node.optional_field("basis")
        fields = node.optional_field("fields")
        if exports is None:
            if instances is not None:
                raise InvalidManifestError(
                    f"form {name!r}: instances must be declared with exports"
                )
            for key, limit in (
                ("max_instances", maximum),
                ("min_instances", minimum),
                ("exclusive_group", group),
                ("required", required),
                ("required_when", required_when),
                ("basis", basis),
                ("fields", fields),
            ):
                if limit is not None:
                    raise InvalidManifestError(
                        f"form {name!r}: {key} belongs to the part that declares exports"
                    )
            return name, None
        if required is None:
            raise InvalidManifestError(f"form {name!r}: required must be declared true or false")
        cls._identifiers(exports)
        declared = _Declaration(
            instances=None if instances is None else instances.require_non_empty_string(),
            exports=tuple(item.require_string() for item in exports.items()),
            max_instances=None if maximum is None else maximum.require_integer(),
            min_instances=None if minimum is None else minimum.require_integer(),
            exclusive_group=None if group is None else group.require_non_empty_string(),
            required=required.require_boolean(),
            required_when=None
            if required_when is None
            else required_when.require_non_empty_string(),
            basis=None if basis is None else basis.require_non_empty_string(),
            fields=() if fields is None else cls._declarations(fields),
        )
        # Built to check the declaration; the form's selections are added when the parts merge.
        declared.form(name, ())
        return name, declared

    @classmethod
    def _part(cls, part: Path) -> dict[str, YamlNode]:
        """The keys a part carries, each checked on its own; errors name the part."""
        try:
            doc = YamlNode.load(part, "manifest").require_mapping(frozenset(), optional=_PART_KEYS)
            contents = dict(doc.fields())
            if "form" in contents:
                cls._form_header(contents["form"])
            if "jurisdiction" in contents:
                cls._code(contents["jurisdiction"])
            for key in ("version", "valid_from_tax_year"):
                if key in contents:
                    contents[key].require_integer()
            if "inputs" in contents:
                cls._declarations(contents["inputs"])
            if "outputs" in contents:
                cls._identifiers(contents["outputs"])
            if "capabilities" in contents:
                for entry in contents["capabilities"].items():
                    cls._selection(entry)
        except (OSError, yaml.YAMLError, InvalidManifestError, YamlShapeError) as exc:
            raise InvalidManifestError(f"{part}: {exc}") from exc
        return contents

    @staticmethod
    def _claim_identifiers(key: str, node: YamlNode, part: Path, owners: dict[str, Path]) -> None:
        """Record the part's identifiers under `key`, refusing one an earlier part listed."""
        if key not in _IDENTIFIER_LISTS:
            return
        for index, item in enumerate(node.items()):
            identifier = (
                item.field("name").require_string() if key == "inputs" else item.require_string()
            )
            if identifier in owners:
                raise InvalidManifestError(
                    f"{part}: {key}[{index}]: {identifier!r} is already listed in "
                    f"{owners[identifier]}"
                )
            owners[identifier] = part

    @classmethod
    def _manifest(
        cls,
        document: YamlNode,
        forms_beside: Callable[[str], tuple[Form, ...]] = lambda _: (),
    ) -> Manifest:
        """The manifest of `document`, whose selections and `outputs` are the default form's.

        `forms_beside` gives the other forms, from the name the default form takes.
        """
        doc = document.require_mapping(_MANIFEST_KEYS)
        code = cls._code(doc.field("jurisdiction"))
        inputs = cls._declarations(doc.field("inputs"))
        outputs = cls._identifiers(doc.field("outputs"))
        if not outputs:
            raise InvalidManifestError("outputs must name at least one artifact")
        Form.check_exports("outputs", sorted(outputs))
        default = code.namespace.identifier(_DEFAULT_FORM)
        return Manifest(
            jurisdiction=code,
            version=doc.field("version").require_integer(),
            valid_from_tax_year=doc.field("valid_from_tax_year").require_integer(),
            inputs={declaration.name: declaration for declaration in inputs},
            forms=(
                Form(
                    name=default,
                    instances=None,
                    exports=tuple(sorted(outputs)),
                    capabilities=tuple(
                        cls._selection(entry) for entry in doc.field("capabilities").items()
                    ),
                    required=True,
                ),
                *forms_beside(default),
            ),
        )

    @staticmethod
    def _identifiers(node: YamlNode) -> frozenset[str]:
        """A list of non-empty identifiers, none repeated; an empty list is Manifest's check."""
        identifiers: set[str] = set()
        for item in node.items():
            identifier = item.require_string()
            if not identifier:
                raise YamlShapeError(f"{item.where} must not be empty")
            if identifier in identifiers:
                raise YamlShapeError(f"{item.where}: {identifier!r} is listed more than once")
            identifiers.add(identifier)
        return frozenset(identifiers)

    @classmethod
    def _declarations(cls, node: YamlNode) -> tuple[InputDeclaration, ...]:
        """A list of input declarations, none repeated; an empty list is Manifest's check."""
        declarations = tuple(cls._declaration(entry) for entry in node.items())
        names: set[str] = set()
        for entry, declaration in zip(node.items(), declarations, strict=True):
            if declaration.name in names:
                raise YamlShapeError(
                    f"{entry.where}: {declaration.name!r} is listed more than once"
                )
            names.add(declaration.name)
        return declarations

    @classmethod
    def _declaration(cls, entry: YamlNode) -> InputDeclaration:
        """One input or field: its `name`, whether it is `required`, and for an optional one its
        `default` (written as the value, `null` for blank) and the printed `basis`."""
        fields = entry.require_mapping(
            frozenset({"name"}), optional=_OPTIONAL_INPUT_KEYS | {"required"}
        )
        name = fields.field("name").require_non_empty_string()
        required = fields.optional_field("required")
        if required is None:
            raise InvalidManifestError(f"input {name!r}: required must be declared true or false")
        default = fields.optional_field("default")
        basis = fields.optional_field("basis")
        return InputDeclaration(
            name=name,
            required=required.require_boolean(),
            default=None if default is None else cls._default(default),
            basis=None if basis is None else basis.require_non_empty_string(),
        )

    @staticmethod
    def _default(node: YamlNode) -> Default:
        """`null`, a quoted string or an empty list, as the value the default is."""
        value = node.value
        if value is None:
            return Default(None)
        if isinstance(value, str):
            return Default(value)
        if isinstance(value, list) and not value:
            return Default(())
        raise YamlShapeError(
            f"{node.where} must be null, a quoted string or [], got {type(value).__name__}"
        )

    @classmethod
    def _selection(cls, entry: YamlNode) -> CapabilitySelection:
        fields = entry.require_mapping(_CAPABILITY_KEYS, optional=_OPTIONAL_CAPABILITY_KEYS)
        return CapabilitySelection(
            name=fields.field("name").require_string(),
            params=cls._bindings(fields.optional_field("params")),
            consumes=cls._consumed(fields.optional_field("consumes")),
            produces=cls._produced(fields.field("produces")),
            blank=cls._bindings(fields.optional_field("blank")),
        )

    @classmethod
    def _produced(cls, node: YamlNode) -> dict[str, str]:
        bindings = cls._bindings(node)
        if not bindings:
            raise YamlShapeError(f"{node.where} must name at least one slot")
        return bindings

    @staticmethod
    def _bindings(node: YamlNode | None) -> dict[str, str]:
        return {} if node is None else node.string_mapping()

    @classmethod
    def _consumed(cls, node: YamlNode | None) -> dict[str, str | tuple[str, ...]]:
        """Consumed slots, each bound to one identifier or to a list of them, in order."""
        if node is None:
            return {}
        return {slot: cls._identifier_or_list(value) for slot, value in node.fields()}

    @staticmethod
    def _identifier_or_list(node: YamlNode) -> str | tuple[str, ...]:
        """A non-empty identifier, or a list of them as a tuple; repeats are the builder's check."""
        if node.is_list():
            return tuple(item.require_non_empty_string() for item in node.items())
        if not isinstance(node.value, str):
            raise YamlShapeError(
                f"{node.where} must be a string or a list of strings, "
                f"got {type(node.value).__name__}"
            )
        return node.require_non_empty_string()

    @staticmethod
    def _code(node: YamlNode) -> JurisdictionCode:
        try:
            return JurisdictionCode(node.require_string())
        except InvalidJurisdictionCodeError as exc:
            raise InvalidManifestError(f"{node.where}: {exc}") from exc
