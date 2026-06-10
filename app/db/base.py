"""
SQLAlchemy base class for all models.
"""
from app.db.base_class import Base


# Import all models here so Alembic can discover them
from app.models.template import Template  # noqa: F401, E402
from app.models.template_version import TemplateVersion  # noqa: F401, E402
from app.models.template_execution import TemplateExecution  # noqa: F401, E402

# Import auth models
from app.domains.auth.models import (  # noqa: F401, E402
    Tenant,
    User,
    Role,
    Permission,
    RolePermission,
    UserRole,
    RefreshToken,
    PasswordResetToken,
    EmailVerificationToken,
    ParentStudentLink,
    Institution,
    PersonalWorkspace,
    UserMembership,
    Invite,
    AuditLog,
    TeacherProfileContext,
)

# Import subscription models
from app.domains.subscriptions.models import (  # noqa: F401, E402
    SubscriptionTierModel,
    SubscriptionTierFeature,
    UserSubscription,
    SubscriptionHistory,
    UserUsageQuota,
    UserUsageLog,
)

# Import chatbot models
from app.domains.chatbots.models import (  # noqa: F401, E402
    Chatbot,
    ChatbotModelAssignment,
    ChatbotCapability,
    ChatbotConversation,
    ChatbotMessage,
    ChatbotModelUsage,
    UserCapabilityProgress,
)

# Import pixgen models
from app.domains.pixgen.models import PixGenGeneration  # noqa: F401, E402

# Import youtube quiz models
from app.domains.youtube_quiz.models import YoutubeQuizGeneration  # noqa: F401, E402

# Import history annotation models
from app.domains.user_history.models import (  # noqa: F401, E402
    UserContentPin,
    UserContentFeedback,
)

# Import content ingestion models
from app.domains.content_ingestion.models import (  # noqa: F401, E402
    ContentPack,
    Document,
    PageText,
    Chunk,
    DocumentTopic,
    DocumentProcessingRun,
    QAValidation,
    WorksheetCache,
    WorksheetQuestionHash,
)

# Import teacher quiz models
from app.domains.teacher_quiz.models import (  # noqa: F401, E402
    TeacherQuiz,
    TeacherQuizQuestion,
    TeacherQuizGenerationRun,
)

from app.domains.teacher_exam.models import (  # noqa: F401, E402
    TeacherExam,
    TeacherExamSection,
    TeacherExamQuestion,
    TeacherExamGenerationRun,
)

from app.domains.teacher_assignment.models import (  # noqa: F401, E402
    TeacherAssignment,
    TeacherAssignmentGenerationRun,
)

from app.domains.teacher_worksheet.models import (  # noqa: F401, E402
    TeacherWorksheet,
    TeacherWorksheetBlock,
    TeacherWorksheetGenerationRun,
    TeacherWorksheetSession,
)

# Import teacher identity models
from app.domains.teacher_identity.models import (  # noqa: F401, E402
    TeacherExperience,
    TeacherEducation,
    TeacherCertification,
    TeacherAchievement,
    TeacherCareerDocument,
)

# Import teacher intelligence models
from app.domains.teacher_intelligence.models import (  # noqa: F401, E402
    TeacherFeatureSnapshot,
    MLOutput,
    PipelineRun,
)

# Import content registry models
from app.domains.content_registry.models import ContentRegistryItem  # noqa: F401, E402

# Import content factory models
from app.domains.content_factory.models import (  # noqa: F401, E402
    ContentGenerationJob,
    ContentGenerationReview,
)

# Import learning progress models
from app.domains.learning_progress.models import (  # noqa: F401, E402
    LearningSession,
    LearningEvent,
    RecommendationEvent,
    ContentFeedback,
)

# Import recommendation analytics models
from app.domains.recommendation_analytics.models import (  # noqa: F401, E402
    RecommendationPerformanceSnapshot,
)

# Import personalization domain models
from app.domains.personalization.models import (  # noqa: F401, E402
    UserPersonalizationProfile,
    ProfileVersion,
    PersonalizationSnapshot,
    PersonalizationJob,
    PersonalizedContentAssignment,
    RecommendationSlate,
    RecommendationSlateItem,
    UnlockRule,
    SectionInventoryConfig,
    UnlockState,
    UnlockEvent,
    UserActivityEvent,
    SectionReadiness,
)
