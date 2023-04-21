import logging
from dataclasses import dataclass
from typing import ClassVar

from pants.core.goals.tailor import (
    AllOwnedSources,
    PutativeTarget,
    PutativeTargets,
    PutativeTargetsRequest,
)
from pants.core.target_types import FileSourceField
from pants.engine.fs import PathGlobs, Paths
from pants.engine.rules import Get, collect_rules, rule
from pants.engine.target import (
    COMMON_TARGET_FIELDS,
    Dependencies,
    MultipleSourcesField,
    OverridesField,
    Target,
    TargetFilesGenerator,
    generate_file_based_overrides_field_help_message,
    generate_multiple_sources_field_help_message,
)
from pants.engine.unions import UnionRule
from pants.option.option_types import BoolOption
from pants.option.subsystem import Subsystem
from pants.util.dirutil import group_by_dir
from pants.util.logging import LogLevel
from pants.util.strutil import softwrap

logger = logging.getLogger(__name__)


class TomlSetup(Subsystem):
    options_scope = "toml-setup"
    help = "Options for Pants's TOML support."

    tailor = BoolOption(
        default=True,
        help=softwrap(
            """
            If true, add `toml_sources` targets with the `tailor` goal.
            """
        ),
        advanced=True,
    )


class TomlSourceField(FileSourceField):
    expected_file_extensions: ClassVar[tuple[str, ...]] = (".toml",)


class TomlDependenciesField(Dependencies):
    pass


class TomlSourceTarget(Target):
    alias = "toml_source"
    core_fields = (*COMMON_TARGET_FIELDS, TomlDependenciesField, TomlSourceField)
    help = "A single TOML file"


class TomlSourcesGeneratingSourcesField(MultipleSourcesField):
    default = ("*.toml",)
    uses_source_roots = False
    expected_file_extensions: ClassVar[tuple[str, ...]] = (".toml",)
    help = generate_multiple_sources_field_help_message(
        "Example: `sources=['pyproject.toml', 'config.toml']`"
    )


class TomlSourcesOverridesField(OverridesField):
    help = generate_file_based_overrides_field_help_message(
        TomlSourceTarget.alias,
        """
        overrides={
            "foo.toml": {"skip_taplo": True]},
        }
        """,
    )


class TomlSourcesGeneratorTarget(TargetFilesGenerator):
    alias = "toml_sources"
    core_fields = (
        *COMMON_TARGET_FIELDS,
        TomlSourcesGeneratingSourcesField,
        TomlSourcesOverridesField,
    )
    generated_target_cls = TomlSourceTarget
    copied_fields = COMMON_TARGET_FIELDS
    moved_fields = (TomlDependenciesField,)
    help = "Generate a `toml_source` target for each file in the `sources` field."


@dataclass(frozen=True)
class PutativeTomlTargetsRequest(PutativeTargetsRequest):
    pass


@rule(level=LogLevel.DEBUG, desc="Determine candidate TOML targets to create")
async def find_putative_targets(
    req: PutativeTomlTargetsRequest,
    all_owned_sources: AllOwnedSources,
    toml_setup: TomlSetup,
) -> PutativeTargets:
    if not toml_setup.tailor:
        return PutativeTargets()
    all_toml_files = await Get(Paths, PathGlobs, req.path_globs("*.toml"))
    unowned_toml_files = set(all_toml_files.files) - set(all_owned_sources)
    logger.debug(unowned_toml_files)
    pts = []
    for paths in unowned_toml_files:
        for dirname, filenames in group_by_dir(paths).items():
            pts.append(
                PutativeTarget.for_target_type(
                    TomlSourcesGeneratorTarget,
                    path=dirname,
                    name=None,
                    triggering_sources=sorted(filenames),
                )
            )
    return PutativeTargets(pts)


def rules():
    return [
        *collect_rules(),
        UnionRule(PutativeTargetsRequest, PutativeTomlTargetsRequest),
    ]
