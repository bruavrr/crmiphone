"""Extension contract. No provider is configured, no fabricated AI responses."""
from typing import Protocol
from django.core.exceptions import ValidationError
class AIProvider(Protocol):
    def summarize(self,*,customer_id:str,redacted_context:dict)->str: ...
    def suggest_reply(self,*,conversation_id:str,redacted_context:dict)->str: ...
def provider()->AIProvider:
    raise ValidationError('IA não configurada. Implemente um provedor e avaliação de privacidade antes de ativar.')
