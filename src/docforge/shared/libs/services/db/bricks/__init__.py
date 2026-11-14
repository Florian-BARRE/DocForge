# ====== Code Summary ======
# Shared bricks of the data layer's facades — one copy of each helper the facades used to repeat:
# ConstraintViolation (the "IntegrityError -> violated constraint name" decoder) and
# VectorSpaceProvisioner (ensure the Qdrant vector space from the schema + embed layout). Import from
# this facade.

from .constraint_violation import ConstraintViolation
from .vector_space_provisioner import VectorSpaceProvisioner

__all__ = ["ConstraintViolation", "VectorSpaceProvisioner"]
