from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.db.models import Count, Q
from django.forms import Form, modelformset_factory
from django.http import Http404, HttpResponsePermanentRedirect, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext as _, gettext_lazy, ungettext
from django.views.generic import CreateView, DetailView, FormView, ListView, UpdateView, View
from django.views.generic.detail import SingleObjectMixin, SingleObjectTemplateResponseMixin
from reversion import revisions

from judge.forms import OrganizationForm
from judge.models import BlogPost, Comment, Contest, Language, Organization, OrganizationRequest, Problem, Profile
from judge.utils.ranker import ranker
from judge.utils.views import QueryStringSortMixin, TitleMixin, generic_message
from judge.views.blog import BlogPostCreate, PostListBase
from judge.views.contests import ContestList, CreateContest
from judge.views.problem import ProblemCreate, ProblemList
from judge.views.submission import AllSubmissions

__all__ = ['OrganizationList', 'OrganizationHome', 'OrganizationUsers', 'OrganizationMembershipChange',
           'JoinOrganization', 'LeaveOrganization', 'EditOrganization', 'RequestJoinOrganization',
           'OrganizationRequestDetail', 'OrganizationRequestView', 'OrganizationRequestLog',
           'KickUserWidgetView']


class OrganizationMixin(object):
    context_object_name = 'organization'
    model = Organization

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['logo_override_image'] = self.object.logo_override_image
        context['meta_description'] = self.object.about[:settings.DESCRIPTION_MAX_LENGTH]
        return context

    def dispatch(self, request, *args, **kwargs):
        try:
            return super(OrganizationMixin, self).dispatch(request, *args, **kwargs)
        except Http404:
            key = kwargs.get(self.slug_url_kwarg, None)
            if key:
                return generic_message(request, _('No such organization'),
                                       _('Could not find an organization with the key "%s".') % key)
            else:
                return generic_message(request, _('No such organization'),
                                       _('Could not find such organization.'))

    def can_edit_organization(self, org=None):
        if org is None:
            org = self.object
        if not self.request.user.is_authenticated:
            return False
        profile_id = self.request.profile.id
        return org.admins.filter(id=profile_id).exists()


class OrganizationDetailView(OrganizationMixin, DetailView):
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.slug != kwargs['slug']:
            return HttpResponsePermanentRedirect(reverse('organization_home', args=(self.object.id, self.object.slug)))
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)


class OrganizationList(TitleMixin, ListView):
    model = Organization
    context_object_name = 'organizations'
    template_name = 'organization/list.html'
    title = gettext_lazy('Organizations')

    def get_queryset(self):
        return Organization.objects.filter(is_unlisted=False)


class OrganizationUsers(QueryStringSortMixin, OrganizationDetailView):
    template_name = 'organization/users.html'
    all_sorts = frozenset(('points', 'problem_count', 'rating', 'performance_points'))
    default_desc = all_sorts
    default_sort = '-performance_points'

    def get_context_data(self, **kwargs):
        context = super(OrganizationUsers, self).get_context_data(**kwargs)
        context['title'] = self.object.name
        context['users'] = \
            ranker(self.object.members.filter(is_unlisted=False).order_by(self.order)
                   .select_related('user').defer('about', 'user_script', 'notes'))
        context['partial'] = True
        context['is_admin'] = self.can_edit_organization()
        context['kick_url'] = reverse('organization_user_kick', args=[self.object.id, self.object.slug])
        context.update(self.get_sort_context())
        return context


class OrganizationMembershipChange(LoginRequiredMixin, OrganizationMixin, SingleObjectMixin, View):
    def post(self, request, *args, **kwargs):
        org = self.get_object()
        response = self.handle(request, org, request.profile)
        if response is not None:
            return response
        return HttpResponseRedirect(org.get_absolute_url())

    def handle(self, request, org, profile):
        raise NotImplementedError()


class JoinOrganization(OrganizationMembershipChange):
    def handle(self, request, org, profile):
        if profile.organizations.filter(id=org.id).exists():
            return generic_message(request, _('Joining organization'), _('You are already in the organization.'))

        if not org.is_open:
            return generic_message(request, _('Joining organization'), _('This organization is not open.'))

        max_orgs = settings.DMOJ_USER_MAX_ORGANIZATION_COUNT
        if profile.organizations.filter(is_open=True).count() >= max_orgs:
            return generic_message(
                request, _('Joining organization'),
                _('You may not be part of more than {count} public organizations.').format(count=max_orgs),
            )

        profile.organizations.add(org)
        profile.save()


class LeaveOrganization(OrganizationMembershipChange):
    def handle(self, request, org, profile):
        if not profile.organizations.filter(id=org.id).exists():
            return generic_message(request, _('Leaving organization'), _('You are not in "%s".') % org.short_name)
        profile.organizations.remove(org)


class OrganizationRequestForm(Form):
    reason = forms.CharField(widget=forms.Textarea)


class RequestJoinOrganization(LoginRequiredMixin, SingleObjectMixin, FormView):
    model = Organization
    slug_field = 'key'
    slug_url_kwarg = 'key'
    template_name = 'organization/requests/request.html'
    form_class = OrganizationRequestForm

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super(RequestJoinOrganization, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(RequestJoinOrganization, self).get_context_data(**kwargs)
        if self.object.is_open:
            raise Http404()
        context['title'] = _('Request to join %s') % self.object.name
        return context

    def form_valid(self, form):
        request = OrganizationRequest()
        request.organization = self.get_object()
        request.user = self.request.profile
        request.reason = form.cleaned_data['reason']
        request.state = 'P'
        request.save()
        return HttpResponseRedirect(reverse('request_organization_detail', args=(
            request.organization.id, request.organization.slug, request.id,
        )))


class OrganizationRequestDetail(LoginRequiredMixin, TitleMixin, DetailView):
    model = OrganizationRequest
    template_name = 'organization/requests/detail.html'
    title = gettext_lazy('Join request detail')
    pk_url_kwarg = 'rpk'

    def get_object(self, queryset=None):
        object = super(OrganizationRequestDetail, self).get_object(queryset)
        profile = self.request.profile
        if object.user_id != profile.id and not object.organization.admins.filter(id=profile.id).exists():
            raise PermissionDenied()
        return object


OrganizationRequestFormSet = modelformset_factory(OrganizationRequest, extra=0, fields=('state',), can_delete=True)


class OrganizationRequestBaseView(LoginRequiredMixin, SingleObjectTemplateResponseMixin, SingleObjectMixin, View):
    model = Organization
    slug_field = 'key'
    slug_url_kwarg = 'key'
    tab = None

    def get_object(self, queryset=None):
        organization = super(OrganizationRequestBaseView, self).get_object(queryset)
        if not organization.admins.filter(id=self.request.profile.id).exists():
            raise PermissionDenied()
        return organization

    def get_context_data(self, **kwargs):
        context = super(OrganizationRequestBaseView, self).get_context_data(**kwargs)
        context['title'] = _('Managing join requests for %s') % self.object.name
        context['content_title'] = format_html(_('Managing join requests for %s') %
                                               ' <a href="{1}">{0}</a>', self.object.name,
                                               self.object.get_absolute_url())
        context['tab'] = self.tab
        return context


class OrganizationRequestView(OrganizationRequestBaseView):
    template_name = 'organization/requests/pending.html'
    tab = 'pending'

    def get_context_data(self, **kwargs):
        context = super(OrganizationRequestView, self).get_context_data(**kwargs)
        context['formset'] = self.formset
        return context

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.formset = OrganizationRequestFormSet(
            queryset=OrganizationRequest.objects.filter(state='P', organization=self.object),
        )
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        self.object = organization = self.get_object()
        self.formset = formset = OrganizationRequestFormSet(request.POST, request.FILES)
        if formset.is_valid():
            if organization.slots is not None:
                deleted_set = set(formset.deleted_forms)
                to_approve = sum(form.cleaned_data['state'] == 'A' for form in formset.forms if form not in deleted_set)
                can_add = organization.slots - organization.members.count()
                if to_approve > can_add:
                    messages.error(request, _('Your organization can only receive %d more members. '
                                              'You cannot approve %d users.') % (can_add, to_approve))
                    return self.render_to_response(self.get_context_data(object=organization))

            approved, rejected = 0, 0
            for obj in formset.save():
                if obj.state == 'A':
                    obj.user.organizations.add(obj.organization)
                    approved += 1
                elif obj.state == 'R':
                    rejected += 1
            messages.success(request,
                             ungettext('Approved %d user.', 'Approved %d users.', approved) % approved + '\n' +
                             ungettext('Rejected %d user.', 'Rejected %d users.', rejected) % rejected)
            return HttpResponseRedirect(request.get_full_path())
        return self.render_to_response(self.get_context_data(object=organization))

    put = post


class OrganizationRequestLog(OrganizationRequestBaseView):
    states = ('A', 'R')
    tab = 'log'
    template_name = 'organization/requests/log.html'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super(OrganizationRequestLog, self).get_context_data(**kwargs)
        context['requests'] = self.object.requests.filter(state__in=self.states)
        return context


class CreateOrganization(PermissionRequiredMixin, TitleMixin, CreateView):
    template_name = 'organization/edit.html'
    model = Organization
    form_class = OrganizationForm
    permission_required = 'judge.add_organization'

    def get_title(self):
        return _('Create new organization')

    def form_valid(self, form):
        with revisions.create_revision(atomic=True):
            revisions.set_comment(_('Created on site'))
            revisions.set_user(self.request.user)

            self.object = org = form.save()
            # slug is show in url
            # short_name is show in ranking
            org.short_name = org.slug[:20]
            org.admins.add(self.request.user.profile)
            org.save()

            return HttpResponseRedirect(self.get_success_url())

    def dispatch(self, request, *args, **kwargs):
        if self.has_permission():
            if self.request.user.profile.admin_of.count() >= settings.VNOJ_ORGANIZATION_ADMIN_LIMIT and \
               not self.request.user.has_perm('spam_organization'):
                return render(request, 'organization/create-limit-error.html', {
                    'admin_of': self.request.user.profile.admin_of.all(),
                    'admin_limit': settings.VNOJ_ORGANIZATION_ADMIN_LIMIT,
                    'title': _("Can't create organization"),
                }, status=403)
            return super(CreateOrganization, self).dispatch(request, *args, **kwargs)
        else:
            return generic_message(request, _("Can't create organization"),
                                   _('You are not allowed to create new organizations.'), status=403)


class EditOrganization(LoginRequiredMixin, TitleMixin, OrganizationMixin, UpdateView):
    template_name = 'organization/edit.html'
    model = Organization
    form_class = OrganizationForm

    def get_title(self):
        return _('Editing %s') % self.object.name

    def get_object(self, queryset=None):
        object = super(EditOrganization, self).get_object()
        if not self.can_edit_organization(object):
            raise PermissionDenied()
        return object

    def form_valid(self, form):
        with revisions.create_revision(atomic=True):
            revisions.set_comment(_('Edited from site'))
            revisions.set_user(self.request.user)
            return super(EditOrganization, self).form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        try:
            return super(EditOrganization, self).dispatch(request, *args, **kwargs)
        except PermissionDenied:
            return generic_message(request, _("Can't edit organization"),
                                   _('You are not allowed to edit this organization.'), status=403)


class KickUserWidgetView(LoginRequiredMixin, OrganizationMixin, SingleObjectMixin, View):
    def post(self, request, *args, **kwargs):
        organization = self.get_object()
        if not self.can_edit_organization(organization):
            return generic_message(request, _("Can't edit organization"),
                                   _('You are not allowed to kick people from this organization.'), status=403)

        try:
            user = Profile.objects.get(id=request.POST.get('user', None))
        except Profile.DoesNotExist:
            return generic_message(request, _("Can't kick user"),
                                   _('The user you are trying to kick does not exist!'), status=400)

        if not organization.members.filter(id=user.id).exists():
            return generic_message(request, _("Can't kick user"),
                                   _('The user you are trying to kick is not in organization: %s.') %
                                   organization.name, status=400)

        organization.members.remove(user)
        return HttpResponseRedirect(organization.get_users_url())


# This is almost the same as the OrganizationMixin
# However, I need to write a new class because the
# current mixin is for the DetailView.
class CustomOrganizationMixin(object):
    # If true, all user can view the current page
    # event they are not in the org
    allow_all_users = False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['organization'] = self.organization
        context['logo_override_image'] = self.organization.logo_override_image
        context['meta_description'] = self.organization.about[:settings.DESCRIPTION_MAX_LENGTH]
        return context

    def dispatch(self, request, *args, **kwargs):
        if 'pk' not in kwargs:
            raise ImproperlyConfigured('Must pass a pk')
        self.organization = get_object_or_404(Organization, pk=kwargs['pk'])
        self.object = self.organization
        if not self.allow_all_users and self.request.profile not in self.organization:
            return generic_message(request,
                                   _("Cannot view organization's private data"),
                                   _('You must join the organization to view its private data.'))
        return super(CustomOrganizationMixin, self).dispatch(request, *args, **kwargs)

    def can_edit_organization(self, org=None):
        if org is None:
            org = self.organization
        if not self.request.user.is_authenticated:
            return False
        profile_id = self.request.profile.id
        return org.admins.filter(id=profile_id).exists()


class CustomAdminOrganizationMixin(CustomOrganizationMixin):
    def dispatch(self, request, *args, **kwargs):
        if 'pk' not in kwargs:
            raise ImproperlyConfigured('Must pass a pk')
        self.organization = get_object_or_404(Organization, pk=kwargs['pk'])
        if self.can_edit_organization():
            return super(CustomAdminOrganizationMixin, self).dispatch(request, *args, **kwargs)
        raise PermissionDenied

    def get_form_kwargs(self):
        kwargs = super(CustomAdminOrganizationMixin, self).get_form_kwargs()
        kwargs['org_pk'] = self.organization.pk
        return kwargs


class OrganizationHome(TitleMixin, CustomOrganizationMixin, PostListBase):
    template_name = 'organization/home.html'
    # Need to set this to true so user can view the org's public
    # information like name, request join org, ...
    # However, they cannot see the org blog
    allow_all_users = True

    def get_queryset(self):
        queryset = BlogPost.objects.filter(organization=self.organization)

        if not self.can_edit_organization():
            if self.request.profile in self.object:
                # Normal user can only view public posts
                queryset = queryset.filter(publish_on__lte=timezone.now(), visible=True)
            else:
                # User cannot view organization blog
                # if they are not in the org
                # event if the org is public
                queryset = BlogPost.objects.none()
        else:
            # Org admin can view public posts & their own posts
            queryset = queryset.filter(Q(visible=True) | Q(authors=self.request.profile))

        return queryset.order_by('-sticky', '-publish_on').prefetch_related('authors__user')

    def get_context_data(self, **kwargs):
        context = super(OrganizationHome, self).get_context_data(**kwargs)
        context['first_page_href'] = reverse('organization_home', args=[self.object.pk, self.object.slug])
        context['title'] = self.object.name
        context['can_edit'] = self.can_edit_organization()

        context['post_comment_counts'] = {
            int(page[2:]): count for page, count in
            Comment.objects
                   .filter(page__in=['b:%d' % post.id for post in context['posts']], hidden=False)
                   .values_list('page').annotate(count=Count('page')).order_by()
        }

        if not self.object.is_open:
            context['num_requests'] = OrganizationRequest.objects.filter(
                state='P',
                organization=self.object).count()

        if self.request.profile in self.object:
            context['is_member'] = True
            context['new_problems'] = Problem.objects.filter(
                is_public=True, is_organization_private=True,
                organizations=self.object) \
                .order_by('-date', '-id')[:settings.DMOJ_BLOG_NEW_PROBLEM_COUNT]

            context['new_contests'] = Contest.objects.filter(
                is_visible=True, is_organization_private=True,
                organizations=self.object) \
                .order_by('-end_time', '-id')[:settings.DMOJ_BLOG_NEW_PROBLEM_COUNT]

        return context


class ProblemListOrganization(CustomOrganizationMixin, ProblemList):
    context_object_name = 'problems'
    template_name = 'organization/problem-list.html'

    def get_hot_problems(self):
        return None

    def get_context_data(self, **kwargs):
        context = super(ProblemListOrganization, self).get_context_data(**kwargs)
        context['title'] = self.organization.name
        return context

    def get_filter(self):
        filter = Q()
        if not self.can_edit_organization():
            filter = Q(is_public=True)
            if self.profile is not None:
                filter |= Q(authors=self.profile)
                filter |= Q(curators=self.profile)
                filter |= Q(testers=self.profile)
        return filter & Q(organizations=self.organization)


class ContestListOrganization(CustomOrganizationMixin, ContestList):
    template_name = 'organization/contest-list.html'

    def _get_queryset(self):
        query_set = super(ContestListOrganization, self)._get_queryset()
        query_set = query_set.filter(is_organization_private=True, organizations=self.organization)
        return query_set

    def get_context_data(self, **kwargs):
        context = super(ContestListOrganization, self).get_context_data(**kwargs)
        context['title'] = self.organization.name
        return context


class SubmissionListOrganization(CustomOrganizationMixin, AllSubmissions):
    template_name = 'organization/submission-list.html'

    def _get_queryset(self):
        query_set = super(SubmissionListOrganization, self)._get_queryset()
        query_set = query_set.filter(user__organizations=self.organization, problem__organizations=self.organization)
        return query_set

    def get_context_data(self, **kwargs):
        context = super(SubmissionListOrganization, self).get_context_data(**kwargs)
        context['title'] = self.organization.name
        context['content_title'] = self.organization.name
        context['dynamic_update'] = False
        return context


class ProblemCreateOrganization(CustomAdminOrganizationMixin, ProblemCreate):
    permission_required = 'judge.create_organization_problem'

    def get_initial(self):
        initial = super(ProblemCreateOrganization, self).get_initial()
        initial = initial.copy()
        initial['code'] = ''.join(x for x in self.organization.slug.lower() if x.isalpha()) + '_'
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({
            'user': self.request.user,
        })
        return kwargs

    def form_valid(self, form):
        self.object = problem = form.save()
        problem.authors.add(self.request.user.profile)
        problem.allowed_languages.set(Language.objects.filter(include_in_problem=True))
        problem.partial = True
        # We have to set it to True, even it is private for a org
        problem.is_public = True
        problem.is_organization_private = True
        problem.organizations.add(self.organization)
        problem.date = timezone.now()
        result = self.save_statement(form, problem)
        if result is not None:
            return result
        problem.save()
        return HttpResponseRedirect(self.get_success_url())


class BlogPostCreateOrganization(CustomAdminOrganizationMixin, PermissionRequiredMixin, BlogPostCreate):
    permission_required = 'judge.edit_organization_post'

    def get_initial(self):
        initial = super(BlogPostCreateOrganization, self).get_initial()
        initial = initial.copy()
        initial['publish_on'] = timezone.now()
        return initial

    def form_valid(self, form):
        self.get_object = post = form.save(commit=False)
        post.save()   # Presave to initialize the object id before using Many-to-Many relationship.
        post.authors.add(self.request.user.profile)
        post.slug = ''.join(x for x in self.organization.slug.lower() if x.isalpha())  # Initial post slug
        post.organization = self.organization
        post.save()
        return HttpResponseRedirect(post.get_absolute_url())


class ContestCreateOrganization(CustomAdminOrganizationMixin, CreateContest):
    permission_required = 'judge.create_private_contest'

    def save_contest_form(self, form):
        self.object = form.save()
        self.object.authors.add(self.request.profile)
        self.object.is_organization_private = True
        self.object.organizations.add(self.organization)
        self.object.save()
