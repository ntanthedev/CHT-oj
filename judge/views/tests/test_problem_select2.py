from django.test import TestCase, override_settings
from django.urls import reverse

from judge.models.tests.util import create_contest, create_organization, create_problem, create_user


class ProblemSelect2ViewTestCase(TestCase):
    fixtures = ['language_all.json', 'navbar.json']

    @classmethod
    def setUpTestData(cls):
        cls.viewer = create_user(username='select2_viewer')
        cls.org_admin = create_user(username='select2_org_admin')
        cls.org = create_organization(name='Alpha', admins=('select2_org_admin',))
        cls.other_org = create_organization(name='Beta', admins=('select2_org_admin',))

        cls.public_problem = create_problem(code='pubprob', name='Public Problem', is_public=True)
        cls.org_problem = create_problem(
            code='orgprob',
            name='Org Problem',
            is_public=True,
            is_organization_private=True,
            organizations=('Alpha',),
        )
        cls.other_org_problem = create_problem(
            code='betaprob',
            name='Beta Problem',
            is_public=True,
            is_organization_private=True,
            organizations=('Beta',),
        )

    def _results(self, url, term=''):
        response = self.client.get(url, {'term': term})
        self.assertEqual(response.status_code, 200)
        return response.json()['results']

    def _texts(self, url, term=''):
        return [r['text'] for r in self._results(url, term)]

    # --- [CODE] Name rendering ------------------------------------------

    def test_general_picker_shows_code_and_name(self):
        self.client.force_login(self.viewer)
        texts = self._texts(reverse('problem_select2'), 'pubprob')
        self.assertIn('[pubprob] Public Problem', texts)

    def test_public_picker_shows_code_and_name(self):
        self.client.force_login(self.viewer)
        texts = self._texts(reverse('public_problem_select2'), 'pubprob')
        self.assertIn('[pubprob] Public Problem', texts)

    def test_org_picker_shows_code_and_name(self):
        self.client.force_login(self.org_admin)
        texts = self._texts(reverse('org_problem_select2', args=[self.org.id]), 'orgprob')
        self.assertIn('[orgprob] Org Problem', texts)

    # --- search by code or name -----------------------------------------

    def test_search_matches_code(self):
        self.client.force_login(self.viewer)
        self.assertIn('[pubprob] Public Problem', self._texts(reverse('problem_select2'), 'pubpro'))

    def test_search_matches_name(self):
        self.client.force_login(self.viewer)
        self.assertIn('[pubprob] Public Problem', self._texts(reverse('problem_select2'), 'Public Prob'))

    # --- the public endpoint must not leak organization-private problems --

    def test_public_endpoint_excludes_organization_private_problems(self):
        self.client.force_login(self.org_admin)
        texts = self._texts(reverse('public_problem_select2'))
        self.assertIn('[pubprob] Public Problem', texts)
        self.assertNotIn('[orgprob] Org Problem', texts)
        self.assertNotIn('[betaprob] Beta Problem', texts)

    def test_public_endpoint_excludes_org_private_problems_for_anonymous(self):
        texts = self._texts(reverse('public_problem_select2'))
        self.assertNotIn('[orgprob] Org Problem', texts)

    # --- the organization endpoint is scoped and permission-checked -------

    def test_org_endpoint_returns_only_that_organizations_private_problems(self):
        self.client.force_login(self.org_admin)
        texts = self._texts(reverse('org_problem_select2', args=[self.org.id]))
        self.assertIn('[orgprob] Org Problem', texts)
        self.assertNotIn('[betaprob] Beta Problem', texts)
        self.assertNotIn('[pubprob] Public Problem', texts)

    def test_org_endpoint_respects_user_visibility(self):
        """A user outside the organization cannot enumerate its private problems."""
        hidden = create_problem(
            code='hiddenprob',
            name='Hidden Problem',
            is_public=False,
            is_organization_private=True,
            organizations=('Alpha',),
        )
        self.client.force_login(self.viewer)
        texts = self._texts(reverse('org_problem_select2', args=[self.org.id]))
        self.assertNotIn('[%s] %s' % (hidden.code, hidden.name), texts)

    def test_org_endpoint_does_not_duplicate_multi_org_problems(self):
        """The m2m join must not emit a problem once per matching organization."""
        create_problem(
            code='sharedprob',
            name='Shared Problem',
            is_public=True,
            is_organization_private=True,
            organizations=('Alpha', 'Beta'),
        )
        self.client.force_login(self.org_admin)
        texts = self._texts(reverse('org_problem_select2', args=[self.org.id]), 'sharedprob')
        self.assertEqual(texts.count('[sharedprob] Shared Problem'), 1)


@override_settings(MOSS_API_KEY=None)
class ContestEditProblemPickerTestCase(TestCase):
    fixtures = ['language_all.json', 'navbar.json']

    @classmethod
    def setUpTestData(cls):
        cls.editor = create_user(
            username='picker_editor',
            user_permissions=('edit_own_contest',),
        )
        cls.org = create_organization(name='Gamma', admins=('picker_editor',))
        cls.other_org = create_organization(name='Delta', admins=('picker_editor',))

    def _edit_page(self, contest):
        self.client.force_login(self.editor)
        response = self.client.get(reverse('contest_edit', args=[contest.key]))
        self.assertEqual(response.status_code, 200)
        return response

    def test_single_organization_contest_gets_split_picker(self):
        contest = create_contest(
            key='org_contest',
            authors=('picker_editor',),
            is_organization_private=True,
            organizations=('Gamma',),
        )
        response = self._edit_page(contest)
        self.assertContains(response, 'data-problem-src')
        self.assertContains(response, 'Organization problems')
        self.assertContains(response, 'Public problems')
        self.assertContains(response, reverse('org_problem_select2', args=[self.org.id]))
        self.assertContains(response, reverse('public_problem_select2'))

    def test_global_contest_keeps_the_normal_picker(self):
        contest = create_contest(key='global_contest', authors=('picker_editor',))
        response = self._edit_page(contest)
        self.assertNotContains(response, 'data-problem-src')
        self.assertNotContains(response, 'Organization problems')

    def test_multi_organization_contest_falls_back_to_normal_picker(self):
        """Never silently pick organizations.first() when the context is ambiguous."""
        contest = create_contest(
            key='multi_org_contest',
            authors=('picker_editor',),
            is_organization_private=True,
            organizations=('Gamma', 'Delta'),
        )
        response = self._edit_page(contest)
        self.assertEqual(contest.organizations.count(), 2)
        self.assertNotContains(response, 'data-problem-src')
        self.assertNotContains(response, 'Organization problems')


@override_settings(MOSS_API_KEY=None)
class ContestEditPickerInitialTabTestCase(TestCase):
    fixtures = ['language_all.json', 'navbar.json']

    @classmethod
    def setUpTestData(cls):
        cls.editor = create_user(
            username='tab_editor',
            user_permissions=('edit_own_contest',),
        )
        cls.org = create_organization(name='Epsilon', admins=('tab_editor',))
        cls.contest = create_contest(
            key='tab_contest',
            authors=('tab_editor',),
            is_organization_private=True,
            organizations=('Epsilon',),
        )

    def _edit_html(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse('contest_edit', args=[self.contest.key]))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_selected_organization_problem_initializes_on_org_tab(self):
        from judge.models.tests.util import create_contest_problem
        problem = create_problem(
            code='epsprob',
            name='Epsilon Problem',
            is_public=True,
            is_organization_private=True,
            organizations=('Epsilon',),
        )
        create_contest_problem(contest=self.contest, problem=problem, order=1)

        html = self._edit_html()
        self.assertIn('data-problem-src="org"', html)
        self.assertIn('[epsprob] Epsilon Problem', html)

    def test_selected_public_problem_initializes_on_public_tab(self):
        from judge.models.tests.util import create_contest_problem
        problem = create_problem(code='plainprob', name='Plain Problem', is_public=True)
        create_contest_problem(contest=self.contest, problem=problem, order=1)

        html = self._edit_html()
        self.assertIn('data-problem-src="public"', html)
        self.assertIn('[plainprob] Plain Problem', html)
