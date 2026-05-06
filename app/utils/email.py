"""
Email service for sending transactional emails.
"""
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def send_email(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
) -> bool:
    """
    Send an email asynchronously.
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        html_content: HTML email content
        text_content: Optional plain text content
        
    Returns:
        True if email was sent successfully, False otherwise
    """
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning("SMTP credentials not configured. Email not sent.")
        logger.info(f"Would send email to {to_email} with subject: {subject}")
        return False
    
    try:
        # Create message
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
        message["To"] = to_email
        
        # Add text and HTML parts
        if text_content:
            text_part = MIMEText(text_content, "plain")
            message.attach(text_part)
        
        html_part = MIMEText(html_content, "html")
        message.attach(html_part)
        
        # Send email
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            start_tls=True,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
        )
        
        logger.info(f"Email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {str(e)}")
        return False


def create_verification_email_template(email: str, token: str) -> tuple[str, str, str]:
    """
    Create email verification email template.
    
    Args:
        email: User email address
        token: Verification token
        
    Returns:
        Tuple of (subject, html_content)
    """
    verification_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    
    subject = "Verify your email address"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .button {{ display: inline-block; padding: 12px 24px; background-color: #4F46E5; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
            .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Verify Your Email Address</h1>
            <p>Hello,</p>
            <p>Thank you for signing up for 1ne.ai! Please verify your email address by clicking the button below:</p>
            <p><a href="{verification_url}" class="button">Verify Email Address</a></p>
            <p>Or copy and paste this link into your browser:</p>
            <p>{verification_url}</p>
            <p>This link will expire in 60 minutes.</p>
            <div class="footer">
                <p>If you didn't create an account, please ignore this email.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    text_content = f"""
    Verify Your Email Address
    
    Hello,
    
    Thank you for signing up for 1ne.ai! Please verify your email address by visiting:
    
    {verification_url}
    
    This link will expire in 60 minutes.
    
    If you didn't create an account, please ignore this email.
    """
    
    return subject, html_content, text_content


def create_password_reset_email_template(email: str, token: str) -> tuple[str, str, str]:
    """
    Create password reset email template.
    
    Args:
        email: User email address
        token: Password reset token
        
    Returns:
        Tuple of (subject, html_content, text_content)
    """
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    
    subject = "Reset your password"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .button {{ display: inline-block; padding: 12px 24px; background-color: #4F46E5; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
            .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Reset Your Password</h1>
            <p>Hello,</p>
            <p>You requested to reset your password for your 1ne.ai account. Click the button below to reset it:</p>
            <p><a href="{reset_url}" class="button">Reset Password</a></p>
            <p>Or copy and paste this link into your browser:</p>
            <p>{reset_url}</p>
            <p>This link will expire in 60 minutes.</p>
            <p>If you didn't request a password reset, please ignore this email and your password will remain unchanged.</p>
            <div class="footer">
                <p>For security reasons, please do not share this link with anyone.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    text_content = f"""
    Reset Your Password
    
    Hello,
    
    You requested to reset your password for your 1ne.ai account. Visit the link below to reset it:
    
    {reset_url}
    
    This link will expire in 60 minutes.
    
    If you didn't request a password reset, please ignore this email and your password will remain unchanged.
    """
    
    return subject, html_content, text_content


def create_invitation_email_template(
    email: str,
    invited_by: str,
    organization_name: str,
    token: Optional[str] = None,
) -> tuple[str, str, str]:
    """
    Create invitation email template for admin-created users.
    
    Args:
        email: User email address
        invited_by: Name of person who sent the invitation
        organization_name: Name of organization/school
        token: Optional invitation token (if user needs to set password)
        
    Returns:
        Tuple of (subject, html_content, text_content)
    """
    subject = f"Welcome to {organization_name} on 1ne.ai"
    
    if token:
        setup_url = f"{settings.FRONTEND_URL}/setup-account?token={token}"
        setup_link = f'<p><a href="{setup_url}" class="button">Set Up Your Account</a></p>'
        setup_text = f"Set up your account: {setup_url}"
    else:
        setup_link = '<p>You can now log in to your account.</p>'
        setup_text = "You can now log in to your account."
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .button {{ display: inline-block; padding: 12px 24px; background-color: #4F46E5; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
            .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Welcome to 1ne.ai</h1>
            <p>Hello,</p>
            <p>You've been invited by {invited_by} to join {organization_name} on 1ne.ai.</p>
            {setup_link}
            <p>Log in at: <a href="{settings.FRONTEND_URL}/login">{settings.FRONTEND_URL}/login</a></p>
            <div class="footer">
                <p>If you have any questions, please contact your administrator.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    text_content = f"""
    Welcome to 1ne.ai
    
    Hello,
    
    You've been invited by {invited_by} to join {organization_name} on 1ne.ai.
    
    {setup_text}
    
    Log in at: {settings.FRONTEND_URL}/login
    
    If you have any questions, please contact your administrator.
    """
    
    return subject, html_content, text_content

