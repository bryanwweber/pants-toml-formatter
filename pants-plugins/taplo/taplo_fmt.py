from __future__ import annotations

import os.path
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from pants.core.goals.fmt import (
    FmtResult,
    FmtTargetsRequest,
    FmtFilesRequest,
    Partitions,
)
from pants.core.util_rules.config_files import ConfigFiles, ConfigFilesRequest
from pants.core.util_rules.external_tool import (
    DownloadedExternalTool,
    ExternalToolRequest,
    TemplatedExternalTool,
)
from pants.core.util_rules.partitions import PartitionerType
from pants.engine.fs import Digest, MergeDigests
from pants.engine.platform import Platform
from pants.engine.process import Process, ProcessResult
from pants.engine.rules import Get, MultiGet, collect_rules, rule
from pants.engine.target import BoolField, FieldSet, Target
from pants.option.option_types import ArgsListOption, BoolOption, SkipOption
from pants.util.logging import LogLevel
from pants.util.memo import memoized
from pants.util.strutil import pluralize, softwrap

from .toml_sources import TomlSourceField, TomlSourcesGeneratorTarget, TomlSourceTarget


class Taplo(TemplatedExternalTool):
    help = "An autoformatter for TOML files (https://taplo.tamasfe.dev/)"

    options_scope = "taplo"
    name = "Taplo"
    default_version = "0.8.0"
    default_known_versions = [
        "0.8.0|macos_arm64|79c1691c3c46be981fa0cec930ec9a6d6c4ffd27272d37d1885514ce59bd8ccf|3661689",
        "0.8.0|macos_x86_64|a1917f1b9168cb4f7d579422dcdf9c733028d873963d8fa3a6f499e41719c502|3926263",
        "0.8.0|linux_arm64|a6a94482f125c21090593f94cad23df099c4924f5b9620cda4a8653527c097a1|3995383",
        "0.8.0|linux_x86_64|3703294fac37ca9a9f76308f9f98c3939ccb7588f8972acec68a48d7a10d8ee5|4123593",
    ]
    default_url_template = "https://github.com/tamasfe/taplo/releases/download/{version}/taplo-{platform}.gz"
    default_url_platform_mapping = {
        "macos_arm64": "darwin-aarch64",
        "macos_x86_64": "darwin-x86_64",
        "linux_arm64": "linux-aarch64",
        "linux_x86_64": "linux-x86_64",
    }

    skip = SkipOption("fmt", "lint")
    args = ArgsListOption(example="--option align_entries=false")
    config_discovery = BoolOption(
        default=True,
        advanced=True,
        help=softwrap(
            """
            If true, Pants will include all relevant `taplo.toml` files during runs.
            """
        ),
    )

    def generate_exe(self, plat: Platform) -> str:
        return f"./{self.generate_url(plat).rsplit('/', 1)[-1].removesuffix('.gz')}"

    def config_request(self, dirs: Iterable[str]) -> ConfigFilesRequest:
        candidates = [os.path.join(d, ".taplo.toml") for d in ("", *dirs)]
        candidates.extend(os.path.join(d, "taplo.toml") for d in ("", *dirs))
        return ConfigFilesRequest(
            discovery=self.config_discovery,
            check_existence=candidates,
        )

    def pyproject_checker(self, filepaths: Sequence[str]) -> list[str]:
        paths = set(filepaths)
        return [f for f in paths if "pyproject.toml" in f]


class SkipTaploField(BoolField):
    alias = "skip_taplo"
    default = False
    help = "If true, don't run taplo on this target's code."


@dataclass(frozen=True)
class TaploFieldSet(FieldSet):
    required_fields = (TomlSourceField,)

    sources: TomlSourceField

    @classmethod
    def opt_out(cls, tgt: Target) -> bool:
        return tgt.get(SkipTaploField).value


class TaploFmtRequest(FmtTargetsRequest):
    field_set_type = TaploFieldSet
    tool_subsystem = Taplo
    name = Taplo.options_scope
    partitioner_type = PartitionerType.DEFAULT_SINGLE_PARTITION


@rule(desc="Format with taplo", level=LogLevel.DEBUG)
async def taplo_fmt(
    request: TaploFmtRequest.Batch, taplo: Taplo, platform: Platform
) -> FmtResult:
    download_taplo_get = Get(
        DownloadedExternalTool,
        ExternalToolRequest,
        taplo.get_request(platform),
    )
    config_files_get = Get(
        ConfigFiles, ConfigFilesRequest, taplo.config_request(request.snapshot.dirs)
    )
    downloaded_taplo, config_digest = await MultiGet(
        download_taplo_get, config_files_get
    )
    input_digest = await Get(
        Digest,
        MergeDigests(
            (
                request.snapshot.digest,
                downloaded_taplo.digest,
                config_digest.snapshot.digest,
            )
        ),
    )

    argv = [
        downloaded_taplo.exe,
        "fmt",
        *taplo.args,
        *request.files,
    ]
    process = Process(
        argv=argv,
        input_digest=input_digest,
        output_files=request.files,
        description=f"Run taplo on {pluralize(len(request.files), 'file')}.",
        level=LogLevel.DEBUG,
    )

    result = await Get(ProcessResult, Process, process)
    return await FmtResult.create(request, result)


class PyprojectFmtRequest(FmtFilesRequest):
    tool_subsystem = Taplo


@rule
async def partition_pyprojects(
    request: PyprojectFmtRequest.PartitionRequest, taplo: Taplo
) -> Partitions[Any]:
    if taplo.skip:
        return Partitions()

    return Partitions.single_partition(sorted(taplo.pyproject_checker(request.files)))


@rule(desc="Format pyproject.toml files", level=LogLevel.DEBUG)
async def pyproject_toml_fmt(
    request: PyprojectFmtRequest.Batch, taplo: Taplo, platform: Platform
) -> FmtResult:
    download_taplo_get = Get(
        DownloadedExternalTool,
        ExternalToolRequest,
        taplo.get_request(platform),
    )
    config_files_get = Get(
        ConfigFiles, ConfigFilesRequest, taplo.config_request(request.snapshot.dirs)
    )
    downloaded_taplo, config_digest = await MultiGet(
        download_taplo_get, config_files_get
    )
    input_digest = await Get(
        Digest,
        MergeDigests(
            (
                request.snapshot.digest,
                downloaded_taplo.digest,
                config_digest.snapshot.digest,
            )
        ),
    )

    argv = [
        downloaded_taplo.exe,
        "fmt",
        *taplo.args,
        *request.files,
    ]
    process = Process(
        argv=argv,
        input_digest=input_digest,
        output_files=request.files,
        description=f"Run taplo on {pluralize(len(request.files), 'file')}.",
        level=LogLevel.DEBUG,
    )

    result = await Get(ProcessResult, Process, process)
    return await FmtResult.create(request, result)


def rules():
    return [
        *collect_rules(),
        *TaploFmtRequest.rules(),
        *PyprojectFmtRequest.rules(),
        TomlSourceTarget.register_plugin_field(SkipTaploField),
        TomlSourcesGeneratorTarget.register_plugin_field(SkipTaploField),
    ]
