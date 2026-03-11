from django.conf import settings
from django.http import HttpResponsePermanentRedirect


class CanonicalHostMiddleware:
    """
    Redirect requests to a single canonical host to avoid CSRF/session issues
    caused by switching between localhost and 127.0.0.1.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        canonical_host = getattr(settings, "CANONICAL_HOST", "").strip()
        if canonical_host:
            request_host = request.get_host()
            if request_host.lower() != canonical_host.lower():
                canonical_scheme = getattr(settings, "CANONICAL_SCHEME", "").strip().lower()
                if canonical_scheme in {"http", "https"}:
                    scheme = canonical_scheme
                else:
                    scheme = "https" if request.is_secure() else "http"
                target = f"{scheme}://{canonical_host}{request.get_full_path()}"
                return HttpResponsePermanentRedirect(target)
        return self.get_response(request)
