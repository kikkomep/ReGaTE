from enum import Enum

REGATE_SEPARATOR = "_____"
TOOLSHED_PREFIX_ID = "biotools:toolshed"
REGATE_DATA_FILE = "regate_data_file"


class _RESOURCE_TYPE(Enum):
    ALL = "all"
    TOOL = "tool"
    WORKFLOW = "workflow"

    @staticmethod
    def values():
        return [o.value for o in _RESOURCE_TYPE]


class _ALLOWED_SOURCES(Enum):
    GALAXY = "galaxy"
    BIOTOOLS = "biotools"

    @staticmethod
    def values():
        return [o.value for o in _ALLOWED_SOURCES]


class _ALLOWED_COMMANDS(Enum):
    EXPORT = "export"
    PUSH = "push"
    TEMPLATE = "template"

    @staticmethod
    def values():
        return [o.value for o in _ALLOWED_COMMANDS]


REGATE_PREFIX_ID = "biotools:regate"