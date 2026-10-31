"""Tax computation: a jurisdiction's manifest for a tax year built into a set of forms, run.

The service does the I/O only: it reads the jurisdiction through its port, asks it for the
manifest of the tax year, resolves each selection's capability class and datasets and the
manifest's input and output kinds through the ports and registries it was given, and hands them
with the artifact registry to the domain (`CapabilityBuilder`, which resolves the selection's
artifact kinds, and `FormSet`, which wires every form), which decides. Resolution errors
propagate unchanged. Composed on the first call for a jurisdiction and tax year, then shared.

A manifest is a flat set of forms, peers that together are the return. Each form exports the
`<form>.<export>` kinds that every form reads. Those kinds are registered into the artifact
registry before any selection is built. `compose` returns the wired `FormSet`; `compute` runs it
and returns each form's worksheets by form name: one per instance, in instance order.

The composed `FormSet` is kept per (jurisdiction code, tax year). Sharing it is safe because
`FormSet.compute` builds its own store and worksheets and never writes to the forms; nothing
invalidates it because manifests and datasets are static files. A lock guards the cache because
Connexion runs synchronous handlers in a thread pool. The lock is held for a whole compose, so a
cold (jurisdiction, tax year) makes concurrent callers wait.
"""

from __future__ import annotations

from threading import Lock
from typing import Any

from tax_engine.application.ports.jurisdiction_source import JurisdictionSource
from tax_engine.application.ports.parameter_source import ParameterSource
from tax_engine.domain.artifact import Artifact, ArtifactRegistry
from tax_engine.domain.capability import Capability, CapabilityRegistry
from tax_engine.domain.capability_builder import CapabilityBuilder
from tax_engine.domain.form import FormComposition, FormSet
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection
from tax_engine.domain.parameters.datasets import ParameterDataset
from tax_engine.domain.worksheet import Worksheet


class TaxComputationService:
    """Builds and runs the set of forms (a `FormSet`) a manifest describes for a tax year."""

    def __init__(
        self,
        jurisdictions: JurisdictionSource,
        parameters: ParameterSource,
        capabilities: CapabilityRegistry,
        artifacts: ArtifactRegistry,
    ) -> None:
        """Resolve manifests, datasets, capability classes and artifact kinds through these."""
        self._jurisdictions = jurisdictions
        self._parameters = parameters
        self._capabilities = capabilities
        self._artifacts = artifacts
        self._builder = CapabilityBuilder()
        self._composed: dict[tuple[JurisdictionCode, int], FormSet] = {}
        self._lock = Lock()

    def compose(self, code: JurisdictionCode, tax_year: int) -> FormSet:
        """The forms of the manifest that applies to `tax_year` in `code`, wired.

        The same `FormSet` is returned on every call for the same `code` and `tax_year`.
        """
        with self._lock:
            key = (code, tax_year)
            if key not in self._composed:
                self._composed[key] = self._compose(code, tax_year)
            return self._composed[key]

    def _compose(self, code: JurisdictionCode, tax_year: int) -> FormSet:
        manifest = self._jurisdictions.get_jurisdiction(code).manifest_for(tax_year)
        exports = {
            form.name: [self._artifacts.kind(identifier) for identifier in form.exports]
            for form in manifest.forms
        }
        for form in manifest.forms:
            for kind in FormComposition.derive(form.name, exports[form.name]):
                self._artifacts.register_kind(kind)
        # Resolved before any capability is built, so a bad identifier is reported first.
        inputs = frozenset(self._artifacts.kind(name) for name in manifest.inputs)
        manifest.check_artifacts(self._artifacts)
        return FormSet(
            [
                FormComposition(
                    form.name,
                    [self._capability(selection, tax_year) for selection in form.capabilities],
                    exports=exports[form.name],
                    instances=None
                    if form.instances is None
                    else self._artifacts.kind(form.instances),
                    starting=inputs,
                    max_instances=form.max_instances,
                    min_instances=form.min_instances,
                    exclusive_group=form.exclusive_group,
                )
                for form in manifest.forms
            ],
            inputs=inputs,
        )

    def compute(
        self, code: JurisdictionCode, tax_year: int, *artifacts: Artifact[Any]
    ) -> dict[str, tuple[Worksheet, ...]]:
        """The worksheets of every form, by form name, from `artifacts`.

        `artifacts` are the starting artifacts of the manifest: one of each declared input kind,
        among them each form's instances. A form's worksheets are one per instance, in instance
        order; a form without an instances list has one instance.
        """
        return self.compose(code, tax_year).compute(*artifacts)

    def _capability(self, selection: CapabilitySelection, tax_year: int) -> Capability:
        cls = self._capabilities.get(selection.name)
        # Only slots the class declares are fetched; the builder reports any other key.
        datasets: dict[str, ParameterDataset[Any]] = {
            slot: self._parameters.get(family, tax_year, cls.PARAMETERS[slot])
            for slot, family in selection.params.items()
            if slot in cls.PARAMETERS
        }
        return self._builder.build(selection, cls, datasets, self._artifacts)
