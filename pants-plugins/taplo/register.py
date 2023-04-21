from .taplo_fmt import rules as fmt_rules
from .toml_sources import TomlSourcesGeneratorTarget, TomlSourceTarget
from .toml_sources import rules as toml_rules


def rules():
    return (*fmt_rules(), *toml_rules())


def target_types():
    return (TomlSourcesGeneratorTarget, TomlSourceTarget)
