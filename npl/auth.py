from django.contrib.auth import login, authenticate
from users.models import User
from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.http import JsonResponse
from sesame.utils import get_token
from allauth.account.utils import setup_user_email
import requests


class MailgunEmailer:
    @staticmethod
    def send_email(to_email, subject, html_content, text_content=None):
        return requests.post(
            f"https://api.mailgun.net/v3/{settings.MAILGUN_DOMAIN_NAME}/messages",
            auth=("api", settings.MAILGUN_API_KEY),
            data={
                "from": f"The NPL <noreply@{settings.MAILGUN_DOMAIN_NAME}>",
                "to": [to_email],
                "subject": subject,
                "html": html_content,
                "text": text_content or html_content
            }
        )


def send_magic_link(request, email):
    """
    Send magic link to existing users only.
    No user creation since admins create accounts manually.
    """
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        messages.error(request, "No account found with this email address. Please contact an administrator.")
        return redirect('account_login')
    
    # Generate token with 30-day expiry
    token = get_token(user)
    magic_link = request.build_absolute_uri(
        reverse('magic_link_verify', kwargs={'token': token})
    )
    
    # Force HTTPS for magic links
    if magic_link.startswith('http://'):
        magic_link = magic_link.replace('http://', 'https://', 1)

    # Send email with magic link
    subject = "Sign in to The NPL"
    html_content = render_to_string('auth/email/magic_link.html', {
        'magic_link': magic_link,
        'user': user,
    })
    
    try:
        MailgunEmailer.send_email(email, subject, html_content)
        messages.success(
            request,
            "We've sent you a magic link! Check your email (including spam folder) to sign in."
        )
    except Exception as e:
        messages.error(
            request,
            "Sorry, we couldn't send the magic link. Please try again or contact an administrator."
        )

    return redirect('account_login')


def login_view(request):
    """Custom login view that only handles magic link requests"""
    if request.method == 'POST':
        # Get email from form - handle both 'email' and 'username' fields for compatibility
        email = request.POST.get('email') or request.POST.get('username')
        
        if email:
            return send_magic_link(request, email)
        else:
            messages.error(request, "Please enter your email address.")
    
    return render(request, 'registration/login.html')


def magic_link_view(request):
    """API endpoint for magic link requests"""
    if request.method == 'POST':
        email = request.POST.get('email')
        return send_magic_link(request, email)
    return redirect('account_login')


def magic_link_verify_view(request, token):
    """Verify magic link token and log user in"""
    from sesame.utils import get_user
    
    user = get_user(token)
    
    if user is not None:
        login(request, user)
        messages.success(request, "You've been signed in successfully!")
        return redirect('index')
    
    messages.error(request, "This magic link is invalid or has expired. Please request a new one.")
    return redirect('account_login') 