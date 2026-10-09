from dataclasses import dataclass
from math import floor


@dataclass(frozen=True)
class PositionSize:
    allowed: bool
    reason: str
    quantity_btc: float
    contracts: int
    usd_notional: float
    inr_notional: float


class PositionSizer:

    def __init__(
        self,
        contract_value_btc: float = 0.001,
        quantity_precision: int = 3,
    ):
        if contract_value_btc <= 0:
            raise ValueError(
                "contract_value_btc must be positive"
            )

        self.contract_value_btc = contract_value_btc
        self.quantity_precision = quantity_precision

    def calculate(
        self,
        max_inr_notional: float,
        btc_usd_price: float,
        usd_inr: float,
    ) -> PositionSize:

        if max_inr_notional <= 0:
            raise ValueError(
                "max_inr_notional must be positive"
            )

        if btc_usd_price <= 0:
            raise ValueError(
                "btc_usd_price must be positive"
            )

        if usd_inr <= 0:
            raise ValueError(
                "usd_inr must be positive"
            )

        max_usd = max_inr_notional / usd_inr

        one_contract_usd = (
            btc_usd_price
            * self.contract_value_btc
        )

        one_contract_inr = (
            one_contract_usd
            * usd_inr
        )

        contracts = floor(
            max_usd / one_contract_usd
        )

        if contracts < 1:
            return PositionSize(
                allowed=False,
                reason="minimum_contract_exceeds_inr_limit",
                quantity_btc=0.0,
                contracts=0,
                usd_notional=0.0,
                inr_notional=0.0,
            )

        quantity = (
            contracts
            * self.contract_value_btc
        )

        usd_notional = (
            quantity
            * btc_usd_price
        )

        inr_notional = (
            usd_notional
            * usd_inr
        )

        return PositionSize(
            allowed=True,
            reason="sizing_allowed",
            quantity_btc=round(
                quantity,
                self.quantity_precision,
            ),
            contracts=contracts,
            usd_notional=usd_notional,
            inr_notional=inr_notional,
        )
