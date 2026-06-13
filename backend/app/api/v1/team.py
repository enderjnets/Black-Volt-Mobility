"""Team / access API — super-admin management of the dashboard access list.

Backs the Settings → Team panel: the owner adds a friend's Gmail, toggles them
active/inactive (grant/revoke access without losing their data), or removes them.
Mounted under require_admin in main.py. Two lockout guards: env-pinned admins
(GOOGLE_ADMIN_EMAILS) are immutable, and the last active admin can't be
deactivated or removed.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.base import get_db
from app.models import AllowedUser, Tenant
from app.models.allowed_user import ROLE_ADMIN, ROLE_DRIVER
from app.services.dashboard import team_member_detail, team_stats_by_tenant
from app.services.email import send_team_welcome

router = APIRouter(prefix="/team", tags=["team"])


class TeamMemberOut(BaseModel):
    email: str
    role: str
    active: bool
    name: str | None = None
    tenant_slug: str | None = None
    immutable: bool = False
    created_at: str | None = None
    last_login: str | None = None
    rides: int = 0
    revenue: float = 0.0
    last_activity: str | None = None
    # Set only on add / resend: "sent" | "simulated" | "failed". None on plain list.
    email_status: str | None = None


class TeamAddIn(BaseModel):
    email: str = Field(max_length=254)
    name: str | None = Field(default=None, max_length=200)
    lang: str | None = Field(default=None, max_length=5)  # welcome-email language

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if "@" not in v or "." not in v.split("@")[-1] or len(v) < 5:
            raise ValueError("invalid_email")
        return v


class TeamPatchIn(BaseModel):
    active: bool | None = None
    name: str | None = Field(default=None, max_length=200)
    role: str | None = None

    @field_validator("role")
    @classmethod
    def _valid_role(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().lower()
        if v not in (ROLE_ADMIN, ROLE_DRIVER):
            raise ValueError("invalid_role")
        return v


def _norm(email: str) -> str:
    return (email or "").lower().strip()


async def _pinned() -> set[str]:
    return set(get_settings().google_admin_emails_list)


async def _other_active_admins_remain(db: AsyncSession, *, excluding: str) -> bool:
    """True if at least one active admin remains after excluding `email` —
    counting env-pinned admins (always present/active) plus other admin rows."""
    pinned = {e for e in get_settings().google_admin_emails_list if e != excluding}
    if pinned:
        return True
    rows = (
        await db.execute(
            select(AllowedUser.email).where(
                AllowedUser.role == ROLE_ADMIN, AllowedUser.active.is_(True)
            )
        )
    ).all()
    return any(r[0] != excluding for r in rows)


async def _slugs(db: AsyncSession, ids: list[int]) -> dict[int, str]:
    real = [i for i in ids if i]
    if not real:
        return {}
    rows = (await db.execute(select(Tenant.id, Tenant.slug).where(Tenant.id.in_(real)))).all()
    return {r[0]: r[1] for r in rows}


def _out(
    u: AllowedUser,
    *,
    slug: str | None,
    pinned: set[str],
    stats: dict | None = None,
    email_status: str | None = None,
) -> TeamMemberOut:
    st = stats or {}
    return TeamMemberOut(
        email=u.email,
        role=u.role,
        active=u.active,
        name=u.name,
        tenant_slug=slug,
        immutable=u.email in pinned,
        created_at=u.created_at.isoformat() if u.created_at else None,
        last_login=u.last_login.isoformat() if u.last_login else None,
        rides=st.get("rides", 0),
        revenue=st.get("revenue", 0.0),
        last_activity=st.get("last_activity"),
        email_status=email_status,
    )


@router.get("")
async def list_team(db: AsyncSession = Depends(get_db)) -> list[TeamMemberOut]:
    pinned = await _pinned()
    rows = (
        await db.execute(select(AllowedUser).order_by(AllowedUser.role, AllowedUser.email))
    ).scalars().all()
    slugs = await _slugs(db, [u.tenant_id for u in rows if u.tenant_id])
    stats = await team_stats_by_tenant(db)
    return [
        _out(
            u,
            slug=slugs.get(u.tenant_id) if u.tenant_id else None,
            pinned=pinned,
            stats=stats.get(u.tenant_id) if u.tenant_id else None,
        )
        for u in rows
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_member(body: TeamAddIn, db: AsyncSession = Depends(get_db)) -> TeamMemberOut:
    email = _norm(str(body.email))
    existing = (
        await db.execute(select(AllowedUser).where(AllowedUser.email == email))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="already_on_list")
    row = AllowedUser(
        email=email, role=ROLE_DRIVER, active=True,
        name=(body.name or "").strip() or None, added_by="admin",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    email_status = await send_team_welcome(to=email, name=row.name, lang=body.lang or "en")
    return _out(row, slug=None, pinned=await _pinned(), email_status=email_status)


@router.patch("/{email}")
async def patch_member(
    email: str, body: TeamPatchIn, db: AsyncSession = Depends(get_db)
) -> TeamMemberOut:
    email = _norm(email)
    pinned = await _pinned()
    if email in pinned and body.active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="pinned_admin_immutable"
        )
    row = (
        await db.execute(select(AllowedUser).where(AllowedUser.email == email))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_on_list")
    if (
        body.active is False
        and row.role == ROLE_ADMIN
        and not await _other_active_admins_remain(db, excluding=email)
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="last_admin")
    # Role change (admin↔driver). A pinned admin can't be demoted, and the last
    # active admin can't be demoted to driver (mirrors the deactivate/remove guards).
    if body.role is not None and body.role != row.role:
        if body.role == ROLE_DRIVER and email in pinned:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="pinned_admin_immutable"
            )
        if (
            body.role == ROLE_DRIVER
            and row.role == ROLE_ADMIN
            and not await _other_active_admins_remain(db, excluding=email)
        ):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="last_admin")
        row.role = body.role
    if body.active is not None:
        row.active = body.active
    if body.name is not None:
        row.name = body.name.strip() or None
    await db.commit()
    await db.refresh(row)
    slugs = await _slugs(db, [row.tenant_id]) if row.tenant_id else {}
    return _out(row, slug=slugs.get(row.tenant_id) if row.tenant_id else None, pinned=pinned)


@router.delete("/{email}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(email: str, db: AsyncSession = Depends(get_db)):
    email = _norm(email)
    if email in await _pinned():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="pinned_admin_immutable"
        )
    row = (
        await db.execute(select(AllowedUser).where(AllowedUser.email == email))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_on_list")
    if row.role == ROLE_ADMIN and not await _other_active_admins_remain(db, excluding=email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="last_admin")
    await db.delete(row)
    await db.commit()


class ResendOut(BaseModel):
    email_status: str


@router.get("/{email}/detail")
async def member_detail(email: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Full per-driver read-model for the Team detail drawer: identity/access,
    subscription, business KPIs, 30-day engagement, recent rides + activity.
    404 if the email isn't on the access list."""
    data = await team_member_detail(db, email=_norm(email), pinned=await _pinned())
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_on_list")
    return data


@router.post("/{email}/resend-invite")
async def resend_invite(email: str, db: AsyncSession = Depends(get_db)) -> ResendOut:
    """Re-send the welcome email to an existing member. Returns the send status
    ("sent" | "simulated" | "failed"); 404 if the member isn't on the list."""
    email = _norm(email)
    row = (
        await db.execute(select(AllowedUser).where(AllowedUser.email == email))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_on_list")
    return ResendOut(email_status=await send_team_welcome(to=email, name=row.name, lang="en"))
