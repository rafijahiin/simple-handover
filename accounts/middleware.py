class OrganisationMiddleware:
    """
    Attaches org shortcuts to every request so views and permission classes
    don't need to repeat request.user.organisation / role checks.
    Must sit after AuthenticationMiddleware in MIDDLEWARE.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            request.organisation = request.user.organisation
            request.user_role = request.user.role
            request.can_see_all_orgs = request.user.can_see_all_orgs
        else:
            request.organisation = None
            request.user_role = None
            request.can_see_all_orgs = False
        return self.get_response(request)
