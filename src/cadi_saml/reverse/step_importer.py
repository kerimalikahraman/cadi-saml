"""Public STEP inspection API."""
from .inspection import inspect_step

class STEPReverseEngineer:
    inspect_and_to_saml = staticmethod(inspect_step)
