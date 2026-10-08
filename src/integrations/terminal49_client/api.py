from contextlib import asynccontextmanager
import hmac
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .config import Terminal49Settings
from .core import PayloadError, parse_notification, valid_signature
from .store import IdentityConflict, Store


class MappingRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    odoo_container_id: int = Field(gt=0)
    number: str = Field(min_length=1, max_length=32)
    active: bool = True
    refresh: bool = False


class InitiationRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    company_id: int = Field(gt=0)
    odoo_container_id: int = Field(gt=0)
    number: str = Field(min_length=1, max_length=32)
    request_type: str = 'container'
    request_number: str = Field(default='', max_length=64)
    scac: str = Field(default='', max_length=4)


class ShipmentRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    company_id: int = Field(gt=0)
    odoo_shipment_id: int = Field(gt=0)
    request_type: str
    request_number: str = Field(min_length=1, max_length=64)
    scac: str = Field(default='', max_length=4)


def create_app(config=None, store=None):
    # No configuration or network I/O at module import; helps isolated tests.
    @asynccontextmanager
    async def lifespan(app):
        app.state.config = config or Terminal49Settings()
        app.state.config.require_enabled()
        app.state.store = store or Store(app.state.config)
        await app.state.store.health()
        yield

    app = FastAPI(title='Bokser Terminal49', lifespan=lifespan, docs_url=None, redoc_url=None)

    def authenticate(request: Request, authorization: str | None = Header(default=None)):
        expected = request.app.state.config.pull_token.get_secret_value()
        scheme, _, token = (authorization or '').partition(' ')
        if scheme.lower() != 'bearer' or not expected or not hmac.compare_digest(token.encode(), expected.encode()):
            raise HTTPException(401, 'Invalid pull credentials')

    @app.get('/health')
    async def health(request: Request):
        try:
            return await request.app.state.store.health()
        except Exception:
            raise HTTPException(503, 'Terminal49 storage unavailable') from None

    @app.post('/webhooks/terminal49', status_code=202)
    async def webhook(request: Request):
        cfg, db = request.app.state.config, request.app.state.store
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > cfg.max_body_bytes:
                raise HTTPException(413, 'Payload too large')
            raw.extend(chunk)
        raw = bytes(raw)
        valid = valid_signature(raw, request.headers.get('X-T49-Webhook-Signature'),
                                cfg.webhook_secret.get_secret_value())
        doc, reason = None, None
        if valid:
            try:
                doc = parse_notification(raw, max_bytes=cfg.max_body_bytes)
            except PayloadError:
                reason = 'Invalid notification envelope'
        else:
            reason = 'Invalid signature'
        try:
            result = await db.accept(raw, valid, doc, reason)
        except IdentityConflict:
            raise HTTPException(409, 'Notification identity conflict') from None
        except Exception:
            raise HTTPException(503, 'Delivery could not be durably accepted') from None
        if not valid:
            raise HTTPException(401, reason)
        if doc is None:
            raise HTTPException(400, reason)
        return result

    @app.post('/v1/containers/{cid}/mapping', dependencies=[Depends(authenticate)])
    async def mapping(cid: UUID, body: MappingRequest, request: Request):
        try:
            await request.app.state.store.mapping(str(cid), body.odoo_container_id,
                ''.join(body.number.split()).upper(), body.active, refresh=body.refresh)
        except IdentityConflict:
            raise HTTPException(409, 'Mapping identity conflict') from None
        return {'ok': True}

    @app.post('/v1/tracking/requests', status_code=202, dependencies=[Depends(authenticate)])
    async def initiate(body: InitiationRequest, request: Request):
        if body.company_id != request.app.state.config.odoo_company_id:
            raise HTTPException(409, 'Tracking service company does not match Odoo')
        try:
            return await request.app.state.store.initiate(body.odoo_container_id,
                body.number, body.request_type, body.request_number, body.scac)
        except IdentityConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get('/v1/tracking/requests/{odoo_id}', dependencies=[Depends(authenticate)])
    async def initiation_status(odoo_id: int, request: Request, company_id: int = Query(gt=0)):
        if company_id != request.app.state.config.odoo_company_id:
            raise HTTPException(409, 'Tracking service company does not match Odoo')
        result = await request.app.state.store.initiation_status(odoo_id)
        if result is None:
            raise HTTPException(404, 'Tracking operation not found')
        return result

    @app.post('/v1/shipments/tracking/requests', status_code=202, dependencies=[Depends(authenticate)])
    async def shipment_start(body: ShipmentRequest, request: Request):
        if body.company_id != request.app.state.config.odoo_company_id:
            raise HTTPException(409, 'Tracking service company does not match Odoo')
        from .shipments import ShipmentStore
        try:
            return await ShipmentStore(request.app.state.store).start(body.odoo_shipment_id,
                body.request_type, body.request_number, body.scac)
        except IdentityConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get('/v1/shipments/tracking/requests/{odoo_id}', dependencies=[Depends(authenticate)])
    async def shipment_status(odoo_id: int, request: Request, company_id: int = Query(gt=0)):
        if company_id != request.app.state.config.odoo_company_id:
            raise HTTPException(409, 'Tracking service company does not match Odoo')
        from .shipments import ShipmentStore
        result = await ShipmentStore(request.app.state.store).status(odoo_id)
        if result is None:
            raise HTTPException(404, 'Shipment tracking operation not found')
        return result

    @app.get('/v1/updates', dependencies=[Depends(authenticate)])
    async def updates(request: Request, after: int = Query(default=0, ge=0),
                      limit: int = Query(default=50, ge=1, le=200)):
        return await request.app.state.store.feed(after, limit)

    @app.get('/v1/status', dependencies=[Depends(authenticate)])
    async def status(request: Request):
        return await request.app.state.store.status()

    return app


app = create_app()
