from django.http import HttpResponseForbidden
class SecurityMiddleware:
    def __init__(self,get_response): self.get_response=get_response
    def __call__(self,request):
        if request.user.is_authenticated and not request.user.is_active:
            from django.contrib.auth import logout
            logout(request)
            return HttpResponseForbidden('Conta desativada.')
        response=self.get_response(request)
        response['Referrer-Policy']='same-origin'
        response['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
        response['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self' https://wa.me"
        return response
