"""SQLAlchemy models. Importing this package registers every table on Base."""

from app.models.class_profile import ClassProfile
from app.models.concept import Concept, ConceptAlias
from app.models.connection import Connection, ConnectionStatus
from app.models.forum import ForumPost, ForumTopic
from app.models.message import Conversation, ConversationParticipant, Message
from app.models.profile import TeacherProfile
from app.models.rating import Rating
from app.models.recommendation import RecommendationEvent, RecommendationFeedback
from app.models.resource import Resource
from app.models.technique import RatingLink, Technique, TechniqueConcept, TechniqueRating
from app.models.user import User
from app.models.verification_token import StudentVerificationToken

__all__ = [
    "ClassProfile",
    "Concept",
    "ConceptAlias",
    "Connection",
    "ConnectionStatus",
    "Conversation",
    "ConversationParticipant",
    "ForumPost",
    "ForumTopic",
    "Message",
    "Rating",
    "RatingLink",
    "RecommendationEvent",
    "RecommendationFeedback",
    "Resource",
    "StudentVerificationToken",
    "TeacherProfile",
    "Technique",
    "TechniqueConcept",
    "TechniqueRating",
    "User",
]
