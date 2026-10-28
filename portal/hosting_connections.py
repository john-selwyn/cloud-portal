"""Customer-facing access information; never stores or retrieves passwords."""
from django.conf import settings


def connection_details(account):
    username = account.username
    host = settings.HOSTING_ACCESS_HOST
    port = settings.HOSTING_ACCESS_PORT
    return {
        'account': account, 'host': host, 'port': port,
        'fingerprint': settings.HOSTING_ACCESS_FINGERPRINT,
        'username': username,
        'website_root': f'/home/{username}/web/{account.domain}/public_html',
        'ssh_enabled': account.shell == 'jailbash',
        'ssh_command': f'ssh -p {port} {username}@{host}',
        'sftp_command': f'sftp -P {port} {username}@{host}',
    }
