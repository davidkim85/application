from typing import Annotated
import jwt
from fastapi import APIRouter, Request, status, Depends, Form, Cookie
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.templating import Jinja2Templates
from fastapi.responses import RedirectResponse,HTMLResponse
from app.configurations.config import DOMAIN, SECRET_KEY,ALGORITHM
from app.configurations.database import get_async_session
from app.configurations.google_config import get_google_login_url, get_google_user_info
from app.models.models import User
from app.schemas.schemas import UserLogin, UserRegistration, UserPasswordConfirm
from app.broker.tasks import send_email
from app.utils.hashing import verify_password, confirm_password, get_password_hash
from app.utils.jwtConfig import create_access_token, create_email_token, verify_email_token


templates = Jinja2Templates(directory="app/templates")
auth_router = APIRouter(tags=["Registration"],include_in_schema=False)
async def find_user_by_email(email: str, session: AsyncSession = Depends(get_async_session)):
    select_query = select(User).where(User.email == email).options(selectinload(User.address),selectinload(User.reports))
    result = await session.execute(select_query)
    user = result.scalar_one_or_none()
    return user


@auth_router.get("/register",include_in_schema=False)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@auth_router.post("/register", response_class=HTMLResponse,include_in_schema=False)
async def register(request: Request, register_user: Annotated[UserRegistration, Depends(UserRegistration.as_form)],
                   session: AsyncSession = Depends(get_async_session)):
    existing_user = await find_user_by_email(register_user.email, session)
    if not confirm_password(register_user.hashed_password,register_user.confirm_password):
        msg = "Passwords do not match"
        return templates.TemplateResponse("register.html", {"request": request, "msg": msg})
    if existing_user and existing_user.hashed_password:
        msg = "User already exists with same email"
        return templates.TemplateResponse("register.html", {"request": request, "msg": msg})
    if existing_user and existing_user.hashed_password is None:
        existing_user.hashed_password = get_password_hash(register_user.confirm_password)
        await session.commit()
        msg = "registered"
        return templates.TemplateResponse("login.html", {"request": request, "msg": msg})
    html_message = await prepare_email_with_token("verify", register_user.email)
    send_email.apply_async(args=[[register_user.email], "Verify your email", html_message])
    msg = "sent"
    register_user.hashed_password=get_password_hash(register_user.confirm_password)
    user = User(**register_user.model_dump())
    session.add(user)
    await session.commit()
    return templates.TemplateResponse("login.html", {"request": request, "msg": msg})

@auth_router.get("/google/callback",include_in_schema=False)
async def google_callback(code: str = None,error: str = None, session: AsyncSession = Depends(get_async_session)):
    if error == "access_denied" or code is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    user_info = await get_google_user_info(code)
    existing_user = await find_user_by_email(user_info['email'], session)
    if existing_user:
        existing_user.photo = user_info['picture']
        existing_user.first_name = user_info['given_name']
        existing_user.last_name = user_info['family_name']
        existing_user.isVerified = user_info['verified_email']
        await session.commit()
        access_token = create_access_token(data={"sub": existing_user.email})
        response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        response.set_cookie("access_token", access_token, httponly=True)
        return response
    user = User(email=user_info['email'], firstname=user_info['given_name'],lastname=user_info['family_name'],
                photo=user_info['picture'], isVerified=user_info['verified_email'])

    session.add(user)
    await session.commit()
    access_token = create_access_token(data={"sub": user.email})
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie("access_token", access_token, httponly=True)
    return response




@auth_router.get("/login",include_in_schema=False)
async def login_page(request: Request, msg: str | None=""):
    google_login_url = get_google_login_url()
    return templates.TemplateResponse("login.html", {"request": request, "google_login_url": google_login_url,"msg": msg})


@auth_router.post("/login", response_class=HTMLResponse,include_in_schema=False)
async def login(request: Request, user_login: UserLogin = Depends(UserLogin.as_form),
                session: AsyncSession = Depends(get_async_session)):
    existing_user = await find_user_by_email(user_login.email, session)
    if existing_user is None:
        msg = "User with this email does not exist"
        return templates.TemplateResponse("login.html", {"request": request, "msg": msg})
    if not verify_password(plain_password=user_login.password, hashed_password=existing_user.hashed_password):
        msg = "Wrong password provided"
        return templates.TemplateResponse("login.html", {"request": request, "msg": msg})
    if existing_user.isVerified:
        access_token = create_access_token(data={"sub": existing_user.email})
        response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        response.set_cookie("access_token", access_token, httponly=True)
        return response
    msg = "User still not verified.Verification email resend again"
    html_message = await prepare_email_with_token("verify",existing_user.email)
    send_email.apply_async(args=[[existing_user.email], "Verify your email", html_message])
    return templates.TemplateResponse("login.html", {"request": request, "msg": msg})




async def prepare_email_with_token(path:str,email:str):
    token = create_email_token(email)
    link = f"http://{DOMAIN}/auth/{path}/{token}"
    html_message = f"""
            <h1>Verify your Email</h1>
            <p>Please click this <a href="{link}">link</a> to verify your email</p>
            """
    return html_message


@auth_router.get("/logout",response_class=HTMLResponse,include_in_schema=False)
async def logout():
    response = RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("access_token")
    return response


@auth_router.get("/forgot_password", response_class=HTMLResponse,include_in_schema=False)
async def forgot_password(request: Request):
    return templates.TemplateResponse("forgot_password.html", {"request": request})


@auth_router.post("/resend", response_class=HTMLResponse,include_in_schema=False)
async def resend(request: Request, email: str = Form(), session: AsyncSession = Depends(get_async_session)):
    user = await find_user_by_email(email, session)
    if user is None:
        msg = "User with this email does not exist"
        return templates.TemplateResponse("token_expired.html", {"request": request, "msg": msg})
    html_message=await prepare_email_with_token(path="verify",email=user.email)
    send_email.apply_async(args=[[user.email], "Verify your email", html_message])
    msg = "sent"
    return templates.TemplateResponse("/login.html", {"request": request, "msg": msg})


@auth_router.post("/password_confirmed", response_class=HTMLResponse,include_in_schema=False)
async def confirmed_page(request: Request,user_confirm: UserPasswordConfirm = Depends(UserPasswordConfirm.as_form), session: AsyncSession = Depends(get_async_session)):
    user = await find_user_by_email(user_confirm.email, session)
    if user is None:
        msg="Token expired"
        return templates.TemplateResponse("token_expired.html", {"request": request, "msg": msg})
    if confirm_password(password1=user_confirm.password1, password2=user_confirm.password2):
        user.hashed_password = get_password_hash(user_confirm.password1)
        user.isVerified=True
        await session.commit()
        msg = "changed"
        return templates.TemplateResponse("login.html", {"request": request, "msg": msg})
    msg="passwords do not match"
    return templates.TemplateResponse("reset_password.html", {"request": request, "msg": msg})



@auth_router.get("/token_expired", response_class=HTMLResponse,include_in_schema=False)
async def resend_page(request: Request):
    msg = "Token expired"
    return templates.TemplateResponse("token_expired.html", {"request": request, "msg": msg})





@auth_router.post("/request_for_password", response_class=HTMLResponse,include_in_schema=False)
async def resend(request: Request, email: str = Form(), session: AsyncSession = Depends(get_async_session)):
    user = await find_user_by_email(email, session)
    if user is None:
        msg = "User with this email does not exist"
        return templates.TemplateResponse("forgot_password.html", {"request": request, "msg": msg})
    html_message=await prepare_email_with_token(path="recovery",email=user.email)
    send_email.apply_async(args=[[user.email], "Verify your email", html_message])
    msg = "recovery"
    return templates.TemplateResponse("login.html", {"request": request, "msg": msg})
@auth_router.get("/verify/{token}", response_class=HTMLResponse,include_in_schema=False)
async def verify_user_account(request: Request, token: str, session: AsyncSession = Depends(get_async_session)):
    user_email = verify_email_token(token)
    if user_email == "Token expired":
        msg = "Token has been expired"
        return templates.TemplateResponse("token_expired.html", {"request": request, "msg": msg})
    elif user_email == "Invalid token":
        msg = "Invalid Token detected"
        return templates.TemplateResponse("token_expired.html", {"request": request, "msg": msg})
    else:
        user = await find_user_by_email(user_email, session)
        user.isVerified = True
        await session.commit()
        await session.refresh(user)
        msg = "success"
        return templates.TemplateResponse("login.html", {"request": request, "msg": msg})


@auth_router.get("/recovery/{token}", response_class=HTMLResponse,include_in_schema=False)
async def verify_user_account(request: Request, token: str, session: AsyncSession = Depends(get_async_session)):
    user_email = verify_email_token(token)
    if user_email == "Token expired":
        msg = "Recovery token has been expired"
        return templates.TemplateResponse("forgot_password.html", {"request": request, "msg": msg})
    elif user_email == "Invalid token":
        msg = "Invalid Recovery Token detected"
        return templates.TemplateResponse("reset_password.html", {"request": request, "msg": msg})
    else:
        user = await find_user_by_email(user_email, session)
        user.hashed_password = None
        return templates.TemplateResponse("reset_password.html", {"request": request, "email": user.email, })

async def get_current_user(token: Annotated[str | None, Cookie(alias='access_token')] = None,
                           session: AsyncSession = Depends(get_async_session)):
    if token is None:
        user = None
        return user
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if email is None:
            user = None
            return user
    except InvalidTokenError:
        user = None
        return user
    user = await find_user_by_email(email, session)
    if user is None:
        user = None
    return user