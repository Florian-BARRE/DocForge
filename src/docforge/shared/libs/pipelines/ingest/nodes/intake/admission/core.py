# ====== Code Summary ======
# AdmissionNode — the fail-fast gate of the pipeline: validates the uploaded source against the
# CollectionContract BEFORE anything expensive is spent on it. The format check runs on the PROBED
# format (what the bytes really are), so a spoofed extension can never smuggle content in; empty
# uploads, the size cap and the metadata schema are checked too. A rejection raises with every
# violation listed at once; an accepted source passes through with its metadata cleaned.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import (
    CollectionContract,
    SourceDocument,
    SourceProbe,
    UnknownFieldPolicy,
)

# ====== Local Project Imports ======
from .helpers import AdmissionHelpers


class AdmissionConfig(NodeConfig):
    """Behaviour knobs of the admission gate."""

    unknown_field_policy: UnknownFieldPolicy = Field(
        default=UnknownFieldPolicy.REJECT,
        description="Reject the upload on an unknown metadata field, or silently drop the field.",
    )


class AdmissionConsumes(NodeInput):
    """The uploaded source, what its bytes really are, and the contract to validate against."""

    source: SourceDocument = Field(description="The uploaded document to admit.")
    probe: SourceProbe = Field(description="The detected format the contract is checked against.")
    contract: CollectionContract = Field(description="The collection contract to validate against.")


class AdmissionProduces(NodeOutput):
    """The admitted source — metadata cleaned, ready for the rest of the stage."""

    source: SourceDocument = Field(
        description="The ADMITTED document, its declared metadata validated and cleaned."
    )


@NodeRegistry.register("intake")
class AdmissionNode(ActionNode):
    """
    Validate the upload against the collection contract before any processing cost.

    Checks the file format (extension allow-list), the size cap, and the declared metadata
    (required fields, unknown fields per policy, value types, enum membership). All violations
    are reported together in one failure.
    """

    KIND = "admission"
    UNIQUE_IN_GRAPH = True
    NAME = "Admission gate"
    SUMMARY = "Validate the upload against the collection contract, fail-fast."
    HOW_IT_WORKS = (
        "Checks the PROBED format (what the bytes really are — a spoofed extension cannot pass) "
        "against the accepted formats, rejects empty uploads, enforces the size cap, and checks "
        "every declared metadata value against the schema (required / unknown-policy / type / "
        "enum). Rejection lists all violations at once."
    )
    Config = AdmissionConfig

    Consumes = AdmissionConsumes
    Produces = AdmissionProduces

    async def run(self, data: AdmissionConsumes) -> AdmissionProduces:
        """
        Validate and pass the source through (with cleaned metadata).

        Raises:
            ValueError: When the upload violates the contract (all violations listed).
        """
        source, contract = data.source, data.contract
        config: AdmissionConfig = self.config
        errors: list[str] = []

        # 1. Empty uploads carry nothing to ingest.
        if not source.content:
            errors.append("file is empty")

        # 2. Format allow-list on the DETECTED format — content truth, never the extension. The
        #    claimed extension is quoted when it disagrees, so the rejection is self-explanatory.
        if data.probe.format not in contract.supported_formats:
            claimed = AdmissionHelpers.extension(source.filename)
            message = (
                f"detected format '{data.probe.format}' is not accepted "
                f"(allowed: {contract.supported_formats})"
            )
            if claimed and claimed != data.probe.format:
                message += f" — the filename claims '{claimed}'"
            errors.append(message)

        # 3. Size cap.
        if len(source.content) > contract.max_file_size_bytes:
            errors.append(
                f"file is {len(source.content)} bytes, over the {contract.max_file_size_bytes} cap"
            )

        # 4. Metadata against the schema.
        cleaned, meta_errors = AdmissionHelpers.validate_metadata(
            source.declared_meta, contract.fields, config.unknown_field_policy
        )
        errors.extend(meta_errors)

        # 5. One loud failure carrying every violation, or the cleaned pass-through.
        if errors:
            self.logger.error(f"Upload '{source.filename}' rejected: {'; '.join(errors)}")
            raise ValueError(f"Upload rejected: {'; '.join(errors)}")
        return AdmissionProduces(
            source=SourceDocument(
                filename=source.filename, content=source.content, declared_meta=cleaned
            )
        )


__all__ = ["AdmissionNode", "AdmissionConfig"]
