from django.shortcuts import render
from django.templatetags.static import static
from services.models import Service


# Map service name keywords to locally-stored images under core/static/core/images/services/
SERVICE_IMAGES = {
    'towing': static('core/images/services/towing.jpg'),
    'tow': static('core/images/services/towing.jpg'),
    'battery': static('core/images/services/battery.jpg'),
    'jump start': static('core/images/services/battery.jpg'),
    'lockout': static('core/images/services/lockout.jpg'),
    'lock': static('core/images/services/lockout.jpg'),
    'fuel': static('core/images/services/fuel.jpg'),
    'tyre': static('core/images/services/tyre.jpg'),
    'tire': static('core/images/services/tyre.jpg'),
    'winch': static('core/images/services/winch.jpg'),
    'recovery': static('core/images/services/winch.jpg'),
    'diagnostics': static('core/images/services/diagnostics.jpg'),
    'diagnostic': static('core/images/services/diagnostics.jpg'),
    'member': static('core/images/services/member.jpg'),
    'driver': static('core/images/services/driver.jpg'),
    'assist': static('core/images/services/assist.jpg'),
}

# Pool of unique fallback images — no two unmatched services will share a photo
FALLBACK_IMAGES = [
    static('core/images/services/fallback-1.jpg'),
    static('core/images/services/fallback-2.jpg'),
    static('core/images/services/fallback-3.jpg'),
    static('core/images/services/fallback-4.jpg'),
]


def _get_image(service_name, index):
    """Return a unique photo URL based on the service name, falling back to index."""
    name_lower = service_name.lower().strip()
    for key, url in SERVICE_IMAGES.items():
        if key in name_lower:
            return url
    # Fallback: pick from the pool by index so each card gets a different image
    return FALLBACK_IMAGES[index % len(FALLBACK_IMAGES)]


def home(request):
    services = Service.objects.filter(active=True).order_by('name')
    cards = []
    used_images = set()
    for i, s in enumerate(services):
        image = _get_image(s.name, i)
        # Ensure no duplicate images across cards
        if image in used_images:
            for fb in FALLBACK_IMAGES:
                if fb not in used_images:
                    image = fb
                    break
        used_images.add(image)
        cards.append({
            "title": s.name,
            "price": f"£{s.price}" if s.price and not s.price.startswith('£') else (s.price or 'Call'),
            "text": s.description or "Professional roadside assistance when you need it most.",
            "duration": s.estimated_duration,
            "image": image,
        })
    return render(request, "core/home.html", {"cards": cards})
