from dataclasses import dataclass
import logging

from django.db.models import QuerySet, Prefetch
from apps.core.models import SupportCategory, SupportArticle
from apps.core.services.users import UsersService

logger = logging.getLogger(__name__)


@dataclass
class UserDocsService(UsersService):
    '''
    service layer for support and user documentation
    '''

    def get_articles_queryset(self) -> QuerySet[SupportArticle]:
        '''
        returns published articles or all articles for staff
        '''
        if getattr(self.user, 'is_staff', False) or getattr(self.user, 'is_superuser', False):
            return SupportArticle.objects.all().order_by('order', 'title')
        return SupportArticle.objects.filter(is_published=True).order_by('order', 'title')

    def get_categories(self) -> QuerySet[SupportCategory]:
        '''
        retrieves active support categories with prefetched articles
        '''
        try:
            articles_qs = self.get_articles_queryset()
            return SupportCategory.objects.filter(is_active=True).prefetch_related(
                Prefetch('articles', queryset=articles_qs)
            ).order_by('order', 'name')
        except Exception as e:
            logger.error("Error fetching SupportCategories: %s", e)
            return SupportCategory.objects.none()

    def get_highlighted_articles(self) -> QuerySet[SupportArticle]:
        '''
        retrieves published and highlighted articles
        '''
        try:
            return self.get_articles_queryset().filter(
                is_highlighted=True,
                category__is_active=True
            ).select_related('category').order_by('order')
        except Exception as e:
            logger.error("Error fetching highlighted articles: %s", e)
            return SupportArticle.objects.none()

    def read_user_docs(self) -> dict:
        '''
        returns main dictionary for documentation and support view
        '''
        return {
            'categories': self.get_categories(),
            'highlighted_articles': self.get_highlighted_articles(),
            'can_manage_docs': self._is_full_access,
        }
