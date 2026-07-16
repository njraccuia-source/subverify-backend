from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_current_account(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Account:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    account_id = decode_access_token(token)
    if account_id is None:
        raise credentials_exception
    account = db.query(Account).filter(Account.id == account_id).first()
    if account is None:
        raise credentials_exception
    return account
