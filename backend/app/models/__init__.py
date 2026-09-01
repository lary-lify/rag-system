"""ORM 模型包。

模型之间通过 relationship 双向互相引用：User 引用 LoginLog / AuditLog /
KnowledgeBase / Document / Conversation，反过来这些模型又都引用 User，
KnowledgeBase ↔ Document ↔ Chunk 之间同样互引。SQLAlchemy 要求所有相关类
都注册完毕后才能配置 mapper。

此前本文件是空的，调用方只能单独导入某一个模型文件。一旦先导入的模型
引用了尚未注册的另一个，就会在首次使用 mapper 时抛出：

    InvalidRequestError: expression 'User' failed to locate a name ('User')

是否报错取决于模块导入顺序，也就是取决于「这次请求恰好先碰了哪个模型」，
属于典型的偶发故障。这里集中导入全部模型，调用方导入任意一个模型时都会
先把整张关系网注册完整。
"""
from app.models.audit_log import AuditLog
from app.models.chunk import Chunk
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.kb_permission import KBPermission
from app.models.knowledge_base import KnowledgeBase
from app.models.login_log import LoginLog
from app.models.message import Message
from app.models.token_usage import TokenUsage
from app.models.user import User

__all__ = [
    "AuditLog",
    "Chunk",
    "Conversation",
    "Document",
    "KBPermission",
    "KnowledgeBase",
    "LoginLog",
    "Message",
    "TokenUsage",
    "User",
]
