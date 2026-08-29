from io import StringIO
from unittest.mock import call, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings


class PrepareDevStaticCommandTestCase(SimpleTestCase):
    @override_settings(DEBUG=True, STATIC_ROOT='/configured/static')
    @patch('judge.management.commands.prepare_dev_static.call_command')
    def test_runs_both_static_generators_with_configured_settings(self, generate):
        output = StringIO()

        call_command('prepare_dev_static', verbosity=2, stdout=output)

        self.assertEqual(
            generate.call_args_list,
            [
                call('collectstatic', interactive=False, verbosity=2),
                call('compilejsi18n', verbosity=2),
            ],
        )
        self.assertIn('Development static assets are ready.', output.getvalue())

    @override_settings(DEBUG=False, STATIC_ROOT='/configured/static')
    def test_rejects_non_development_settings(self):
        with self.assertRaisesMessage(CommandError, 'DEBUG=True'):
            call_command('prepare_dev_static', verbosity=0)

    @override_settings(DEBUG=True, STATIC_ROOT='')
    def test_requires_static_root(self):
        with self.assertRaisesMessage(CommandError, 'STATIC_ROOT'):
            call_command('prepare_dev_static', verbosity=0)
