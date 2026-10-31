"""Strict YAML reading shared by the YAML adapters.

`YamlNode` wraps a parsed value with its location in the document, so every
check names exactly where it failed ("brackets[0].rate is not a decimal").
Unknown, missing and duplicate keys and wrongly typed values are rejected,
never coerced or ignored. Shape problems raise YamlShapeError; each adapter
re-raises them as its own domain error with the file named.
"""

from __future__ import annotations

import re
from collections.abc import Hashable
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode

from tax_engine.domain.parameters.rounding import (
    NO_ROUNDING,
    RoundingMode,
    RoundingRule,
    RoundTo,
)

# A whole number's one spelling: ASCII decimal digits, no sign, no leading zero.
_WHOLE_NUMBER = re.compile(r"0|[1-9][0-9]*")
_ROUNDING_KEYS = frozenset({"increment", "mode"})


class YamlShapeError(ValueError):
    """A YAML document does not have the expected shape."""


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys instead of keeping the last one."""

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[Hashable, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise ConstructorError(None, None, f"duplicate key {key!r}", key_node.start_mark)
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


class YamlNode:
    """A parsed YAML value and where it sits in its document.

    The root is labelled (e.g. "manifest") for its own errors; locations below
    it start fresh, so a top-level field is "version", not "manifest.version".
    """

    def __init__(self, value: object, where: str, *, is_root: bool = False) -> None:
        """Wrap `value`, found at location `where` in its document.

        Normally created by `load`, `root`, `field` or `items` rather than directly.
        """
        self._value = value
        self._where = where
        self._is_root = is_root

    @classmethod
    def root(cls, value: object, label: str) -> YamlNode:
        """Wrap an already-parsed document as its root node, named `label` in errors.

        Fields of the root are named on their own ("version"), not "label.version".
        """
        return cls(value, label, is_root=True)

    @classmethod
    def load(cls, path: Path, label: str) -> YamlNode:
        """Read and parse the YAML file at `path` and return its root node, named `label`.

        Duplicate keys are rejected; raises OSError or yaml.YAMLError on failure.
        """
        return cls.root(yaml.load(path.read_text(encoding="utf-8"), Loader=_StrictLoader), label)

    @property
    def value(self) -> object:
        """The raw parsed value, unchecked: a dict, list, str, int, bool, None, etc."""
        return self._value

    @property
    def where(self) -> str:
        """This node's location in the document, e.g. "brackets[0].rate", for error messages."""
        return self._where

    def require_mapping(
        self, keys: frozenset[str], *, optional: frozenset[str] = frozenset()
    ) -> YamlNode:
        """Check this node is a mapping with all of `keys` and any of `optional`, and return it.

        Raises YamlShapeError naming any unknown or missing keys.
        """
        mapping = self._mapping()
        unknown = set(mapping) - keys - optional
        if unknown:
            raise YamlShapeError(f"{self._where}: unknown keys {sorted(map(str, unknown))}")
        missing = keys - set(mapping)
        if missing:
            raise YamlShapeError(f"{self._where}: missing keys {sorted(missing)}")
        return self

    def field(self, key: str) -> YamlNode:
        """The value under `key` in this mapping, as a node located at "where.key".

        Raises YamlShapeError if this node is not a mapping or has no such key.
        """
        mapping = self._mapping()
        if key not in mapping:
            raise YamlShapeError(f"{self._where}: missing key {key!r}")
        where = key if self._is_root else f"{self._where}.{key}"
        return YamlNode(mapping[key], where)

    def optional_field(self, key: str) -> YamlNode | None:
        """The value under `key` in this mapping as a node, or None if the key is absent.

        Raises YamlShapeError if this node is not a mapping.
        """
        return self.field(key) if key in self._mapping() else None

    def string_mapping(self) -> dict[str, str]:
        """This node's value, which must be a mapping of non-empty strings to non-empty strings.

        Returns a new dict; raises YamlShapeError naming the first key or value that is not one.
        """
        return {key: value.require_non_empty_string() for key, value in self.fields()}

    def fields(self) -> list[tuple[str, YamlNode]]:
        """This mapping's keys, which must be non-empty strings, each with its value as a node.

        Raises YamlShapeError if this node is not a mapping or naming the first bad key.
        """
        result: list[tuple[str, YamlNode]] = []
        for key in self._mapping():
            if not isinstance(key, str):
                raise YamlShapeError(
                    f"{self._where}: key {key!r} must be a string, got {type(key).__name__}"
                )
            if not key:
                raise YamlShapeError(f"{self._where}: keys must not be empty")
            result.append((key, self.field(key)))
        return result

    def is_list(self) -> bool:
        """Whether this node's value is a list."""
        return isinstance(self._value, list)

    def items(self) -> list[YamlNode]:
        """The elements of this list, as nodes located at "where[0]", "where[1]", ...

        Raises YamlShapeError if this node is not a list.
        """
        if not isinstance(self._value, list):
            raise YamlShapeError(f"{self._where} must be a list")
        return [YamlNode(item, f"{self._where}[{i}]") for i, item in enumerate(self._value)]

    def require_string(self) -> str:
        """This node's value, which must be a string.

        Raises YamlShapeError otherwise, naming the type found.
        """
        if not isinstance(self._value, str):
            raise YamlShapeError(f"{self._where} must be a string, got {self._type_name()}")
        return self._value

    def require_non_empty_string(self) -> str:
        """This node's value, which must be a non-empty string.

        Raises YamlShapeError otherwise.
        """
        text = self.require_string()
        if not text:
            raise YamlShapeError(f"{self._where} must not be empty")
        return text

    def require_integer(self) -> int:
        """This node's value, which must be an integer; booleans are rejected.

        Raises YamlShapeError otherwise, naming the type found.
        """
        # bool is an int subclass; `version: yes` must not become 1.
        if not isinstance(self._value, int) or isinstance(self._value, bool):
            raise YamlShapeError(f"{self._where} must be an integer, got {self._type_name()}")
        return self._value

    def require_boolean(self) -> bool:
        """This node's value, which must be a YAML boolean (`true` or `false`).

        Raises YamlShapeError otherwise, naming the type found; text such as "yes" is not one.
        """
        if not isinstance(self._value, bool):
            raise YamlShapeError(f"{self._where} must be true or false, got {self._type_name()}")
        return self._value

    def parse_decimal(self) -> Decimal:
        """This node's value as an exact Decimal, parsed from a YAML string such as "0.145".

        Numbers must be quoted so YAML never turns them into floats; non-strings,
        malformed text, NaN and infinities raise YamlShapeError.
        """
        text = self.require_string()
        try:
            result = Decimal(text)
        except InvalidOperation:
            raise YamlShapeError(f"{self._where} is not a decimal: {text!r}") from None
        if not result.is_finite():
            raise YamlShapeError(f"{self._where} is not a decimal: {text!r}")
        return result

    def parse_whole_number(self) -> int:
        """This node's value as an int, parsed from a YAML string of digits such as "3".

        Numbers must be quoted so YAML never reads them itself; the text must be ASCII decimal
        digits with no sign and no leading zero, so each number has one spelling. Non-strings,
        any other text and digits too many for `int` raise YamlShapeError.
        """
        text = self.require_string()
        if not _WHOLE_NUMBER.fullmatch(text):
            raise YamlShapeError(f"{self._where} is not a whole number: {text!r}")
        try:
            return int(text)
        except ValueError:  # more digits than the interpreter's int conversion allows
            raise YamlShapeError(f"{self._where} is not a whole number: {text!r}") from None

    def parse_rounding_rule(self) -> RoundingRule:
        """This node's value as a RoundingRule, parsed from `none` or `{increment, mode}`.

        `none` is NO_ROUNDING; a mapping of a quoted decimal `increment` and a `mode` such as
        `half_up` is a RoundTo. Any other value, unknown or missing keys and an unknown mode
        raise YamlShapeError; an increment that is not positive raises InvalidRoundingRuleError.
        """
        if self._value == "none":
            return NO_ROUNDING
        if not isinstance(self._value, dict):
            raise YamlShapeError(f"{self._where} must be 'none' or a mapping of increment and mode")
        fields = self.require_mapping(_ROUNDING_KEYS)
        mode = fields.field("mode").parse_choice(RoundingMode)
        return RoundTo(increment=fields.field("increment").parse_decimal(), mode=mode)

    def parse_choice[E: Enum](self, choices: type[E]) -> E:
        """This node's value as the member of the enum `choices` whose value is its string.

        Non-strings and a string that is no member's value raise YamlShapeError, the latter
        listing the accepted values, sorted.
        """
        text = self.require_string()
        by_value = {str(member.value): member for member in choices}
        if text not in by_value:
            raise YamlShapeError(f"{self._where} {text!r} is not one of {sorted(by_value)}")
        return by_value[text]

    def _mapping(self) -> dict[object, object]:
        if not isinstance(self._value, dict):
            raise YamlShapeError(f"{self._where} must be a mapping")
        return self._value

    def _type_name(self) -> str:
        return type(self._value).__name__
