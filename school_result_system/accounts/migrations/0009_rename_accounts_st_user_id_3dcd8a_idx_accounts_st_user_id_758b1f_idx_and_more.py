from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_staffnotification"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="staffnotification",
            new_name="accounts_st_user_id_758b1f_idx",
            old_name="accounts_st_user_id_3dcd8a_idx",
        ),
        migrations.RenameIndex(
            model_name="staffnotification",
            new_name="accounts_st_categor_4ab12f_idx",
            old_name="accounts_st_category_4e8c73_idx",
        ),
    ]
