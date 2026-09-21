from enum import Enum


class RelationType(str, Enum):
    def __str__(self) -> str:
        return str(self.value)

    CONTAINS = "CONTAINS"
    CALLS = "CALLS"
    RETURNS = "RETURNS"
    PRODUCES = "PRODUCES"
    CONSUMES = "CONSUMES"
    DERIVED_FROM = "DERIVED_FROM"
    TRANSFORMS = "TRANSFORMS"
    EXTRACTS = "EXTRACTS"
    USED_IN = "USED_IN"
    ATTACHES_TO = "ATTACHES_TO"
    STORES_IN = "STORES_IN"
    READS_FROM = "READS_FROM"
    PRECEDES = "PRECEDES"
    ASSOCIATED_WITH = "ASSOCIATED_WITH"