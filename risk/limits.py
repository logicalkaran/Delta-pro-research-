from dataclasses import dataclass

from risk.sizing import PositionSize, PositionSizer


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str
    position_size: PositionSize | None = None


class RiskEngine:

    def __init__(
        self,
        live_trading: bool = False,
        max_positions: int = 1,
        max_position_notional_inr: float = 5000.0,
        max_daily_loss_inr: float = 250.0,
        max_order_notional_inr: float = 5000.0,
        kill_switch: bool = True,
        contract_value_btc: float = 0.001,
    ):
        self.live_trading = live_trading
        self.max_positions = max_positions
        self.max_position_notional_inr = (
            max_position_notional_inr
        )
        self.max_daily_loss_inr = max_daily_loss_inr
        self.max_order_notional_inr = (
            max_order_notional_inr
        )
        self.kill_switch = kill_switch

        self.sizer = PositionSizer(
            contract_value_btc=contract_value_btc,
        )

    def check(
        self,
        order_notional_inr: float,
        current_positions: int,
        daily_loss_inr: float,
        btc_usd_price: float | None = None,
        usd_inr: float | None = None,
        kill_switch_active: bool = False,
    ) -> RiskDecision:

        if self.kill_switch and kill_switch_active:
            return RiskDecision(
                False,
                "kill_switch_active",
            )

        if order_notional_inr <= 0:
            return RiskDecision(
                False,
                "invalid_order_notional",
            )

        if order_notional_inr > self.max_order_notional_inr:
            return RiskDecision(
                False,
                "order_notional_limit",
            )

        if current_positions >= self.max_positions:
            return RiskDecision(
                False,
                "max_positions_reached",
            )

        if daily_loss_inr >= self.max_daily_loss_inr:
            return RiskDecision(
                False,
                "daily_loss_limit",
            )

        if order_notional_inr > self.max_position_notional_inr:
            return RiskDecision(
                False,
                "position_notional_limit",
            )

        if btc_usd_price is None or usd_inr is None:
            return RiskDecision(
                False,
                "missing_fx_or_market_price",
            )

        position_size = self.sizer.calculate(
            max_inr_notional=order_notional_inr,
            btc_usd_price=btc_usd_price,
            usd_inr=usd_inr,
        )

        if not position_size.allowed:
            return RiskDecision(
                False,
                position_size.reason,
                position_size,
            )

        return RiskDecision(
            True,
            "risk_checks_passed",
            position_size,
        )
