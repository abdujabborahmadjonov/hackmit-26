"""SQLAlchemy models. Importing this package registers every table on Base."""

from app.models.connection import Connection, ConnectionStatus
from app.models.message import Conversation, ConversationParticipant, Message
from app.models.profile import TeacherProfile
from app.models.rating import Rating
from app.models.recommendation import RecommendationEvent, RecommendationFeedback
from app.models.resource import Resource
from app.models.user import User

__all__ = [
    "Connection",
    "ConnectionStatus",
    "Conversation",
    "ConversationParticipant",
    "Message",
    "Rating",
    "RecommendationEvent",
    "RecommendationFeedback",
    "Resource",
    "TeacherProfile",
    "User",
]
