from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_account
from app.models import Account, DocumentType, Document, DocumentStatus
from app.schemas import SignupRequest, TokenResponse, AccountOut, PlanChangeRequest, BrandingUpdateRequest
from app.security import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(Account).filter(Account.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    account = Account(
        company_name=payload.company_name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        plan=payload.plan,
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    token = create_access_token(subject=account.id)
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.email == form_data.username).first()
    if not account or not verify_password(form_data.password, account.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    token = create_access_token(subject=account.id)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=AccountOut)
def me(current: Account = Depends(get_current_account)):
    return current


@router.patch("/branding", response_model=AccountOut)
def update_branding(
    payload: BrandingUpdateRequest,
    db: Session = Depends(get_db),
    current: Account = Depends(get_current_account),
):
    """
    Set what subcontractors see at the top of their upload page: a logo and a
    short welcome message. brand_logo_url should be a direct link to an image
    (e.g. a logo already hosted on your website, or an image-hosting link) —
    this API doesn't host image files itself.
    """
    if payload.brand_logo_url is not None:
        current.brand_logo_url = payload.brand_logo_url
    if payload.brand_welcome_message is not None:
        current.brand_welcome_message = payload.brand_welcome_message
    db.commit()
    db.refresh(current)
    return current


@router.patch("/plan", response_model=AccountOut)
def change_plan(payload: PlanChangeRequest, db: Session = Depends(get_db), current: Account = Depends(get_current_account)):
    from app.models import PLAN_LIMITS

    new_limit = PLAN_LIMITS[payload.plan]["max_subcontractors"]
    if new_limit is not None:
        current_count = db.query(Account).get(current.id)
        sub_count = len(current_count.subcontractors)
        if sub_count > new_limit:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot downgrade: you have {sub_count} subcontractors, "
                       f"which exceeds the {payload.plan.value} plan limit of {new_limit}.",
            )

    current.plan = payload.plan
    db.commit()
    db.refresh(current)
    return current
