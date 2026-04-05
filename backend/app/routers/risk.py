from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.trade import Trade
from backend.app.schemas import RiskValidationRequest, RiskValidationResponse
from backend.app.services.risk import RiskManager

router = APIRouter(prefix="/risk", tags=["Risk Management"])


@router.post("/validate", response_model=RiskValidationResponse)
def validate_trade(req: RiskValidationRequest, db: Session = Depends(get_db)):
    rm = RiskManager(db)
    starting = req.starting_balance or req.account_balance
    result = rm.validate_trade(
        account_balance=req.account_balance,
        starting_balance=starting,
        entry=req.entry_price,
        stop_loss=req.stop_loss,
        take_profit=req.take_profit,
        instrument=req.instrument,
    )
    return RiskValidationResponse(**result)


@router.get("/status")
def risk_status(db: Session = Depends(get_db)):
    open_trades = db.query(Trade).filter(Trade.status == "open").all()
    return {
        "open_positions": len(open_trades),
        "open_instruments": [t.instrument for t in open_trades],
        "total_risk": sum(t.risk_amount for t in open_trades),
    }
