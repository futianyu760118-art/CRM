"""AEOS 跨域契约（CRM 侧落地）。"""

from app.contracts.aeos import (
    EXCEPTION_CONTRACT_VERSION,
    RESULT_CONTRACT_VERSION,
    AeosExceptionContract,
    AeosMetric,
    AeosPeriod,
    AeosResultContract,
    ContractValidationError,
    build_exception_contract,
    build_result_contract,
    to_wire,
    unknown_fields,
    validate_contract,
)

__all__ = [
    "EXCEPTION_CONTRACT_VERSION",
    "RESULT_CONTRACT_VERSION",
    "AeosExceptionContract",
    "AeosMetric",
    "AeosPeriod",
    "AeosResultContract",
    "ContractValidationError",
    "build_exception_contract",
    "build_result_contract",
    "to_wire",
    "unknown_fields",
    "validate_contract",
]
