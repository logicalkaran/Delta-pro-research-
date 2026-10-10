"""Deterministic research-only async execution and perpetual ledger. No live orders."""
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
import heapq
from typing import Any
D = Decimal
ZERO = D('0')
EIGHT_HOURS_MS = 8 * 60 * 60 * 1000

class OrderState(str, Enum):
    SUBMITTING='SUBMITTING'; ACKNOWLEDGED='ACKNOWLEDGED'; PARTIAL_FILL='PARTIAL_FILL'
    CANCEL_PENDING='CANCEL_PENDING'; FILLED='FILLED'; CANCELED='CANCELED'
    CANCEL_REJECTED='CANCEL_REJECTED'; REJECTED='REJECTED'

@dataclass
class SimOrder:
    order_id:int; side:str; price:Decimal; quantity:Decimal; submitted_ms:int
    state:OrderState=OrderState.SUBMITTING
    acknowledged_ms:int|None=None
    queue_ahead:Decimal=ZERO
    filled_quantity:Decimal=ZERO
    average_fill_price:Decimal=ZERO
    events:list[dict[str,Any]]=field(default_factory=list)
    @property
    def remaining(self)->Decimal:
        return max(ZERO,self.quantity-self.filled_quantity)

@dataclass(order=True)
class _Delayed:
    due_ms:int; seq:int
    kind:str=field(compare=False); order_id:int=field(compare=False)

class AsyncOrderSimulator:
    """Caller-driven exchange state machine with deterministic latency and queue."""
    def __init__(self,latency_ms:int=50):
        if latency_ms<0: raise ValueError('latency_ms must be non-negative')
        self.latency_ms=latency_ms; self.now_ms=0; self._seq=0; self._order_seq=0
        self._delay:list[_Delayed]=[]; self.orders:dict[int,SimOrder]={}
        self.inventory=ZERO; self.cash_flow=ZERO; self.audit:list[dict[str,Any]]=[]
        self.book:dict[Decimal,Decimal]={}; self.mark_price=None; self.index_price=None
    def _record(self,o:SimOrder,event:str,**details:Any)->None:
        row={'at_ms':self.now_ms,'order_id':o.order_id,'state':o.state.value,'event':event,**details}
        o.events.append(row); self.audit.append(row.copy())
    def _schedule(self,due:int,kind:str,oid:int)->None:
        self._seq+=1; heapq.heappush(self._delay,_Delayed(due,self._seq,kind,oid))
    def submit(self,side:str,price:Decimal|str,quantity:Decimal|str,now_ms:int)->SimOrder:
        side=side.lower(); p=D(str(price)); q=D(str(quantity))
        if side not in {'buy','sell'}: raise ValueError('side must be buy or sell')
        if p<=0 or q<=0: raise ValueError('price and quantity must be positive')
        self.advance(now_ms); self._order_seq+=1
        o=SimOrder(self._order_seq,side,p,q,now_ms); self.orders[o.order_id]=o
        self._record(o,'SUBMIT_SENT'); self._schedule(now_ms+self.latency_ms,'ACK',o.order_id)
        return o
    def advance(self,now_ms:int)->None:
        if now_ms<self.now_ms: raise ValueError('simulation clock cannot move backwards')
        while self._delay and self._delay[0].due_ms<=now_ms:
            item=heapq.heappop(self._delay); self.now_ms=item.due_ms; o=self.orders[item.order_id]
            if item.kind=='ACK':
                if o.state!=OrderState.SUBMITTING: continue
                o.acknowledged_ms=self.now_ms; o.queue_ahead=max(ZERO,self.book.get(o.price,ZERO))
                o.state=OrderState.ACKNOWLEDGED; self._record(o,'EXCHANGE_ACK',queue_ahead=str(o.queue_ahead))
            elif item.kind=='CANCEL':
                if o.state in {OrderState.FILLED,OrderState.CANCELED}:
                    o.state=OrderState.CANCEL_REJECTED; self._record(o,'CANCEL_REJECTED',reason='ORDER_ALREADY_TERMINAL')
                else:
                    o.state=OrderState.CANCELED; self._record(o,'CANCEL_ACK')
        self.now_ms=now_ms

    def cancel(self,order_id:int,now_ms:int)->None:
        self.advance(now_ms); o=self.orders[order_id]
        if o.state not in {OrderState.ACKNOWLEDGED,OrderState.PARTIAL_FILL}:
            self._record(o,'CANCEL_NOT_SENT',reason='ORDER_NOT_CANCELABLE'); return
        o.state=OrderState.CANCEL_PENDING; self._record(o,'CANCEL_SENT')
        self._schedule(now_ms+self.latency_ms,'CANCEL',order_id)

    def update_book(self,bids:dict[Decimal|str,Decimal|str],asks:dict[Decimal|str,Decimal|str],now_ms:int)->None:
        self.advance(now_ms)
        b={D(str(p)):D(str(q)) for p,q in bids.items()}; a={D(str(p)):D(str(q)) for p,q in asks.items()}
        if any(p<=0 or q<0 for p,q in list(b.items())+list(a.items())): raise ValueError('invalid book level')
        if b and a and max(b)>=min(a): raise ValueError('crossed or locked book snapshot')
        self.book=b

    def trade(self,price:Decimal|str,quantity:Decimal|str,aggressor:str,now_ms:int)->list[dict[str,Any]]:
        self.advance(now_ms); p=D(str(price)); q=D(str(quantity)); aggressor=aggressor.lower()
        if p<=0 or q<=0 or aggressor not in {'buy','sell'}: raise ValueError('invalid trade')
        emitted=[]
        for o in sorted(self.orders.values(),key=lambda x:x.order_id):
            if o.state not in {OrderState.ACKNOWLEDGED,OrderState.PARTIAL_FILL,OrderState.CANCEL_PENDING}: continue
            if o.price!=p or (o.side=='buy' and aggressor!='sell') or (o.side=='sell' and aggressor!='buy'): continue
            used=min(o.queue_ahead,q); o.queue_ahead-=used; available=q-used
            fill=min(o.remaining,available)
            if fill<=0: continue
            notional=o.average_fill_price*o.filled_quantity+p*fill
            o.filled_quantity+=fill; o.average_fill_price=notional/o.filled_quantity
            self.inventory += fill if o.side=='buy' else -fill
            self.cash_flow += -p*fill if o.side=='buy' else p*fill
            o.state=OrderState.FILLED if o.remaining==0 else OrderState.PARTIAL_FILL
            self._record(o,'FILL',fill_qty=str(fill),price=str(p),queue_ahead_remaining=str(o.queue_ahead))
            emitted.append(o.events[-1]); q-=used+fill
            if q<=0: break
        return emitted

    def update_mark_index(self,mark_price:Decimal|str,index_price:Decimal|str,now_ms:int)->None:
        self.advance(now_ms); m=D(str(mark_price)); i=D(str(index_price))
        if m<=0 or i<=0: raise ValueError('mark/index price must be positive')
        self.mark_price=m; self.index_price=i

    def snapshot(self)->dict[str,Any]:
        return {'now_ms':self.now_ms,'inventory':str(self.inventory),'cash_flow':str(self.cash_flow),
          'mark_price':str(self.mark_price) if self.mark_price is not None else None,
          'index_price':str(self.index_price) if self.index_price is not None else None,
          'orders':{k:{'state':v.state.value,'filled':str(v.filled_quantity),'remaining':str(v.remaining),
                       'queue_ahead':str(v.queue_ahead)} for k,v in self.orders.items()}}

@dataclass
class PerpetualLedger:
    """Linear perpetual accounting model; exchange-specific fees/tier rules remain inputs."""
    initial_margin_rate:Decimal=D('0.005')
    maintenance_margin_rate:Decimal=D('0.0025')
    funding_interval_ms:int=EIGHT_HOURS_MS
    position_qty:Decimal=ZERO
    entry_price:Decimal=ZERO
    cash:Decimal=ZERO
    realized_funding:Decimal=ZERO
    funding_rate:Decimal=ZERO
    last_settlement_ms:int|None=None
    next_settlement_ms:int|None=None
    liquidated:bool=False
    liquidation_penalty_rate:Decimal=D('0.005')
    def __post_init__(self)->None:
        if not ZERO<self.maintenance_margin_rate<self.initial_margin_rate<D('1'):
            raise ValueError('maintenance margin must be below initial margin')
        if self.funding_interval_ms<=0 or self.liquidation_penalty_rate<0:
            raise ValueError('invalid funding interval or liquidation penalty')
    def set_position(self,quantity:Decimal|str,entry_price:Decimal|str)->None:
        q=D(str(quantity)); p=D(str(entry_price))
        if p<=0: raise ValueError('entry price must be positive')
        self.position_qty=q; self.entry_price=p; self.liquidated=False
    def set_funding_rate(self,rate:Decimal|str,now_ms:int)->None:
        self.funding_rate=D(str(rate))
        if self.last_settlement_ms is None:
            self.last_settlement_ms=(now_ms//self.funding_interval_ms)*self.funding_interval_ms
            self.next_settlement_ms=self.last_settlement_ms+self.funding_interval_ms
    def settle_through(self,now_ms:int,rate_at_boundary:Decimal|str|None=None)->list[dict[str,str|int]]:
        if self.last_settlement_ms is None: self.set_funding_rate(self.funding_rate,now_ms)
        out=[]
        while self.next_settlement_ms is not None and self.next_settlement_ms<=now_ms:
            rate=self.funding_rate if rate_at_boundary is None else D(str(rate_at_boundary))
            payment=-abs(self.position_qty)*self.entry_price*rate if self.position_qty>0 else abs(self.position_qty)*self.entry_price*rate if self.position_qty<0 else ZERO
            self.cash+=payment; self.realized_funding+=payment; boundary=self.next_settlement_ms
            out.append({'settlement_ms':boundary,'payment':str(payment),'rate':str(rate)})
            self.last_settlement_ms=boundary; self.next_settlement_ms+=self.funding_interval_ms
        return out
    def unrealized_funding_drift(self,now_ms:int)->Decimal:
        if self.last_settlement_ms is None: return ZERO
        elapsed=max(0,min(now_ms,self.next_settlement_ms or now_ms)-self.last_settlement_ms)
        notional=abs(self.position_qty)*self.entry_price
        sign=D('-1') if self.position_qty>0 else D('1') if self.position_qty<0 else ZERO
        return sign*notional*self.funding_rate*D(elapsed)/D(self.funding_interval_ms)
    def unrealized_pnl(self,mark_price:Decimal|str)->Decimal:
        mark=D(str(mark_price))
        if mark<=0: raise ValueError('mark price must be positive')
        return self.position_qty*(mark-self.entry_price)
    def margin_snapshot(self,mark_price:Decimal|str)->dict[str,Any]:
        mark=D(str(mark_price))
        if mark<=0: raise ValueError('mark price must be positive')
        notional=abs(self.position_qty)*mark; pnl=self.unrealized_pnl(mark); equity=self.cash+pnl
        initial=notional*self.initial_margin_rate; maintenance=notional*self.maintenance_margin_rate
        ratio=equity/notional if notional else D('Infinity')
        return {'mark_price':str(mark),'notional':str(notional),'unrealized_pnl':str(pnl),'equity':str(equity),
          'initial_margin_required':str(initial),'maintenance_margin_required':str(maintenance),'equity_ratio':str(ratio),
          'maintenance_breached':bool(notional and equity<maintenance),'initial_margin_breached':bool(notional and equity<initial),
          'liquidated':self.liquidated}
    def check_liquidation(self,mark_price:Decimal|str)->dict[str,Any]:
        snap=self.margin_snapshot(mark_price)
        if snap['maintenance_breached'] and not self.liquidated and self.position_qty!=0:
            penalty=abs(self.position_qty)*D(str(mark_price))*self.liquidation_penalty_rate
            self.cash-=penalty; self.position_qty=ZERO; self.liquidated=True
            snap.update({'liquidated':True,'liquidation_penalty':str(penalty),'position_after_liquidation':'0'})
        else: snap['liquidation_penalty']='0'
        return snap
