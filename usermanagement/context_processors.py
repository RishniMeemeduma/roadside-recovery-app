from recovery.models import RecoveryRequest


def pending_requests_count(request):
    if request.user.is_authenticated and request.user.role == 'ADMIN':
        qs = RecoveryRequest.objects.filter(status='PENDING').select_related('member', 'service').order_by('-created_at')
        return {
            'pending_request_count': qs.count(),
            'pending_requests_preview': qs[:5],
        }
    return {'pending_request_count': 0, 'pending_requests_preview': []}
