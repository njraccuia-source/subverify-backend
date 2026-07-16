import io

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_account
from app.models import Account, Client
from app.schemas import ClientCreate, ClientUpdate, ClientOut

router = APIRouter(prefix="/clients", tags=["clients"])


@router.post("", response_model=ClientOut, status_code=201)
def create_client(payload: ClientCreate, db: Session = Depends(get_db), current: Account = Depends(get_current_account)):
    client = Client(
        account_id=current.id,
        name=payload.name,
        brand_logo_url=payload.brand_logo_url,
        brand_welcome_message=payload.brand_welcome_message,
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@router.get("", response_model=list[ClientOut])
def list_clients(db: Session = Depends(get_db), current: Account = Depends(get_current_account)):
    return db.query(Client).filter(Client.account_id == current.id).order_by(Client.created_at.desc()).all()


def _owned_client(db: Session, client_id: str, account: Account) -> Client:
    client = db.query(Client).filter(Client.id == client_id, Client.account_id == account.id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")
    return client


@router.get("/{client_id}", response_model=ClientOut)
def get_client(client_id: str, db: Session = Depends(get_db), current: Account = Depends(get_current_account)):
    return _owned_client(db, client_id, current)


@router.patch("/{client_id}", response_model=ClientOut)
def update_client(client_id: str, payload: ClientUpdate, db: Session = Depends(get_db), current: Account = Depends(get_current_account)):
    client = _owned_client(db, client_id, current)
    if payload.name is not None:
        client.name = payload.name
    if payload.brand_logo_url is not None:
        client.brand_logo_url = payload.brand_logo_url
    if payload.brand_welcome_message is not None:
        client.brand_welcome_message = payload.brand_welcome_message
    db.commit()
    db.refresh(client)
    return client


@router.delete("/{client_id}", status_code=204)
def delete_client(client_id: str, db: Session = Depends(get_db), current: Account = Depends(get_current_account)):
    client = _owned_client(db, client_id, current)
    db.delete(client)
    db.commit()
    return None


@router.get("/{client_id}/intake-qrcode")
def client_intake_qrcode(client_id: str, request: Request, db: Session = Depends(get_db), current: Account = Depends(get_current_account)):
    client = _owned_client(db, client_id, current)
    base = str(request.base_url).rstrip("/")
    join_url = f"{base}/join/{client.intake_token}"
    img = qrcode.make(join_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")
