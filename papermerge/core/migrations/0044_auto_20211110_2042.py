# Generated by Django 3.2.7 on 2021-11-10 19:42

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0043_auto_20211026_0822'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='document',
            name='file_name',
        ),
        migrations.RemoveField(
            model_name='document',
            name='notes',
        ),
        migrations.RemoveField(
            model_name='document',
            name='page_count',
        ),
        migrations.RemoveField(
            model_name='document',
            name='size',
        ),
        migrations.RemoveField(
            model_name='document',
            name='text',
        ),
        migrations.RemoveField(
            model_name='document',
            name='version',
        ),
        migrations.RemoveField(
            model_name='page',
            name='document',
        ),
        migrations.RemoveField(
            model_name='page',
            name='hocr_step_0',
        ),
        migrations.RemoveField(
            model_name='page',
            name='hocr_step_1',
        ),
        migrations.RemoveField(
            model_name='page',
            name='hocr_step_2',
        ),
        migrations.RemoveField(
            model_name='page',
            name='hocr_step_3',
        ),
        migrations.RemoveField(
            model_name='page',
            name='user',
        ),
        migrations.AddField(
            model_name='document',
            name='ocr',
            field=models.BooleanField(default=True),
        ),
        migrations.CreateModel(
            name='DocumentVersion',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('number', models.IntegerField(default=1, verbose_name='Version number')),
                ('file_name', models.CharField(default='', max_length=1024)),
                ('size', models.BigIntegerField(help_text='Size of file_orig attached. Size is in Bytes')),
                ('page_count', models.IntegerField(default=1)),
                ('text', models.TextField(blank=True)),
                ('document', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='versions', to='core.document', verbose_name='Document')),
            ],
            options={
                'verbose_name': 'Document version',
                'verbose_name_plural': 'Document versions',
                'ordering': ('number',),
            },
        ),
        migrations.AddField(
            model_name='page',
            name='document_version',
            field=models.ForeignKey(default='', on_delete=django.db.models.deletion.CASCADE, related_name='version_pages', to='core.documentversion'),
            preserve_default=False,
        ),
    ]