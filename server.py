from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import ROOT_DIR, get_settings
from app.payment_log import install_payment_log
from app.payments import install_x402
from app.routes.certificates import router as certificates_router

settings = get_settings()

app = FastAPI(
    title="Walcert Agent",
    description="Hot-analysis certificates for wallet maturity (ERC-8004 agent on Celo).",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Paywall x402 sobre /v1/certificates/* (no-op si X402_ENABLED=false).
install_x402(app)

# Registro de compras x402. Se monta DESPUES de x402 para quedar por fuera
# (add_middleware apila LIFO) y ver el header PAYMENT-RESPONSE del settle.
install_payment_log(app)

app.include_router(certificates_router)


@app.get("/")
async def root():
    dashboard = ROOT_DIR / "dashboard.html"
    if dashboard.exists():
        return FileResponse(dashboard)
    return {
        "agent": "Walcert",
        "agent_id": settings.agent_id,
        "docs": "/docs",
        "certificates": [
            "/v1/certificates/origins",
            "/v1/certificates/activity",
            "/v1/certificates/multichain",
            "/v1/certificates/portfolio",
        ],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
