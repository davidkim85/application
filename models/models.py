import enum
from datetime import datetime,date
from sqlalchemy import DateTime, Integer, String, func, Enum, ForeignKey, Date, Boolean,event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column,relationship

from hashing import get_password_hash


class Base(DeclarativeBase):
    pass

class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(String(2048), nullable=False)
    image: Mapped[str] = mapped_column(String, nullable=False)
    publication_date: Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
    user: Mapped['User'] = relationship("User", back_populates="posts")

class Role(str,enum.Enum):
    GUEST = "guest"
    USER = "user"
    ADMIN = "admin"




class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True,index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True,index=True)
    username: Mapped[str] = mapped_column(String(255), nullable=False, unique=True,index=True)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    firstname: Mapped[str] = mapped_column(String(255), nullable=True)
    lastname:Mapped[str]=mapped_column(String(255),nullable=True)
    phone: Mapped[str] = mapped_column(String(10), nullable=False)
    role:Mapped[Enum[Role]]=mapped_column(Enum(Role), default=Role.GUEST, nullable=False)
    birthday:Mapped[date]=mapped_column(Date)
    age:Mapped[int]=mapped_column(Integer)
    isVerified:Mapped[bool]=mapped_column(Boolean, nullable=False,default=False)
    isActive:Mapped[bool]=mapped_column(Boolean, nullable=False,default=False)
    photo: Mapped[str]= mapped_column(String, nullable=False)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), nullable=False)
    updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(),onupdate=func.now())
    posts: Mapped[list[Post]] = relationship("Post", cascade="all, delete")


    @staticmethod
    def calculate_age(birthday:datetime)->int:
        today = datetime.today().date()
        age = today.year - birthday.year
        if today.month < birthday.month or (today.month == birthday.month and today.day < birthday.day):
            age -= 1
        return age


@event.listens_for(User, "before_insert")
@event.listens_for(User, "before_update")
def receive_before_insert(mapper, connection, target):
    if target.birthday:
        target.age=target.calculate_age(target.birthday)
    else:
        target.age=None
    if target.hashed_password:
        target.hashed_password=get_password_hash(target.hashed_password)









