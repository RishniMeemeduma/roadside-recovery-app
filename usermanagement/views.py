from django.shortcuts import render

# Create your views here.

def home(request):
    cards = [
        {"title": "Towing", "price": "$0", "text": "Body text."},
        {"title": "Battery", "price": "$0", "text": "Body text."},
        {"title": "Lockout", "price": "$0", "text": "Body text."},
        {"title": "Fuel", "price": "$0", "text": "Body text."},
    ]
    return render(request, "usermanagement/home.html", {"cards": cards})
