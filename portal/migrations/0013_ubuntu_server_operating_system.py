from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("portal", "0012_customer_accounts")]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="operating_system",
            field=models.CharField(
                choices=[
                    ("Ubuntu 26.04", "Ubuntu Desktop 26.04 LTS"),
                    ("Ubuntu Server 26.04", "Ubuntu Server 26.04 LTS"),
                    ("Debian 13", "Debian 13"),
                    ("Windows 11", "Windows 11"),
                ],
                default="Ubuntu 26.04",
                max_length=50,
            ),
        ),
    ]
