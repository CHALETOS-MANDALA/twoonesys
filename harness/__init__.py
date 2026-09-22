"""CASCADE — System One Harness.

Runtime: riceve una proposta, la passa da evidenza e policy, autorizza o
blocca, osserva l'esito, conserva la ricevuta firmata.
"""

from .guarded import ActionDenied, guarded
from .receipt import ActionReceipt, verify_receipt

__version__ = "0.3.0"
__all__ = ["ActionDenied", "ActionReceipt", "guarded", "verify_receipt"]
