from typing import Optional
from fastapi import Form
from pydantic import BaseModel, EmailStr
from datetime import date


class PostPublish(BaseModel):
    title: str
    content: str

    @classmethod
    def as_form(
            cls,
            title: str = Form(),
            content: str = Form()):
        return cls(title=title,content=content)


class PostBase(BaseModel):
    title: str
    content: str
    user_id: int
    image:str

    class Config:
        from_attributes = True



class PostCreate(PostBase):
    pass


class PostRead(PostBase):
    id: int
    user_id: int

class PostPartialUpdate(BaseModel):
    title: str
    content: str


class UserBase(BaseModel):
    email: EmailStr
    username:str
    hashed_password:str
    firstname:Optional[str]
    lastname: Optional[str]
    phone:str
    birthday:date
    photo:str


    class Config:
        from_attributes = True




class UserPartialUpdate(BaseModel):
    lastname: str | None = None


class UserCreate(BaseModel):
    pass


class UserRead(UserBase):
    id: int
    posts: list[PostRead]


class UserLogin(BaseModel):
    username: str
    password: str

    @classmethod
    def as_form(
            cls,
            username: str = Form(),
            password: str = Form()):
        return cls(username=username, password=password)


class UserRegistration(BaseModel):
    email: EmailStr
    username: str
    hashed_password: str
    firstname: Optional[str]
    lastname: Optional[str]
    phone: str
    birthday: date

    @classmethod
    def as_form(cls, email: EmailStr = Form(),
                username: str = Form(),
                hashed_password: str = Form(),
                firstname: Optional[str] = Form(None),
                lastname: Optional[str] = Form(None),
                phone: str = Form(),
                birthday: date = Form()
                ): return cls(email=email, username=username, hashed_password=hashed_password, firstname=firstname,
                              lastname=lastname, phone=phone, birthday=birthday)
