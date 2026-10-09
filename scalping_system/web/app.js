const $=id=>document.getElementById(id),canvas=$("chart"),ctx=canvas.getContext("2d");
function num(v,d=2){return v==null||!Number.isFinite(Number(v))?"—":Number(v).toFixed(d)}
function draw(candles,levels){
 const r=canvas.getBoundingClientRect(),d=devicePixelRatio||1,W=r.width,H=Math.max(300,W*.42);canvas.width=W*d;canvas.height=H*d;ctx.setTransform(d,0,0,d,0,0);ctx.clearRect(0,0,W,H);
 if(!candles.length){ctx.fillStyle="#82909e";ctx.fillText("Waiting for live candles…",14,24);return}
 const a=candles.slice(-100),lo=Math.min(...a.map(x=>+x.low)),hi=Math.max(...a.map(x=>+x.high)),pad=(hi-lo)*.08||1;let mn=lo-pad,mx=hi+pad;
 const L=48,T=12,B=24,w=W-L-10,step=w/a.length;
 const y=p=>T+(mx-p)/(mx-mn)*(H-T-B);
 ctx.font="10px system-ui";ctx.strokeStyle="#1e2933";
 for(let i=0;i<5;i++){let yy=T+i*(H-T-B)/4;ctx.beginPath();ctx.moveTo(L,yy);ctx.lineTo(W-10,yy);ctx.stroke();ctx.fillStyle="#697785";ctx.fillText(num(mx-(mx-mn)*i/4,0),3,yy+3)}
 function line(price,label,kind){if(price==null||price<=mn||price>=mx)return;let yy=y(price);ctx.setLineDash([5,4]);ctx.strokeStyle=kind==="s"?"#50d89b":"#f06b76";ctx.beginPath();ctx.moveTo(L,yy);ctx.lineTo(W-10,yy);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=ctx.strokeStyle;ctx.fillText(label+" "+num(price,2),L+5,yy-4)}
 line(levels.nearest_support,"S","s");line(levels.nearest_resistance,"R","r");line(levels.poc,"POC","r");
 a.forEach((x,i)=>{let px=L+i*step+step/2,oy=y(+x.open),cy=y(+x.close),hy=y(+x.high),ly=y(+x.low);ctx.strokeStyle="#9aa6b2";ctx.beginPath();ctx.moveTo(px,hy);ctx.lineTo(px,ly);ctx.stroke();ctx.fillStyle=+x.close>=+x.open?"#50d89b":"#f06b76";ctx.fillRect(px-Math.max(2,step*.3),Math.min(oy,cy),Math.max(3,step*.6),Math.max(1,Math.abs(cy-oy)))})
}
async function load(){
 try{
  const res=await fetch("/api/state",{cache:"no-store"});if(!res.ok)throw Error("api");
  const x=await res.json(),m=x.live_market||{},ms=x.microstructure||{},ob=ms.order_book||{},w5=ms.windows?.["5"]||{},w30=ms.windows?.["30"]||{},w60=ms.windows?.["60"]||{},p5=ms.price?.["5"]||{},lv=x.predictive_levels||{},f=x.monthly_fisher?.latest||{},v=x.paper_v3||{},g=x.live_gate||{},h=x.health||{};
  draw(x.candles||[],lv);
  $("price").textContent=num(m.mid_price);$("ba").textContent=num(m.best_bid)+"/"+num(m.best_ask);$("spread").textContent=num(m.spread);
  $("regime").textContent=ms.regime||"—";$("decision").textContent=x.signal?.decision||"WAIT";$("confidence").textContent="confidence "+num((x.signal?.confidence||0)*100,0)+"%";
  $("health").textContent=h.status||"UNKNOWN";$("marketAge").textContent=h.market_age_seconds==null?"—":"age "+h.market_age_seconds+"s";
  $("support").textContent=num(lv.nearest_support);$("resistance").textContent=num(lv.nearest_resistance);$("poc").textContent=num(lv.poc);$("valueArea").textContent=num(lv.value_low)+" — "+num(lv.value_high);$("levelRegime").textContent=lv.regime||"—";
  $("bidDepth").textContent=num(ob.bid_depth_5,0);$("askDepth").textContent=num(ob.ask_depth_5,0);$("obi5").textContent=num(ob.imbalance_5,3);$("obi10").textContent=num(ob.imbalance_10,3);
  $("delta5").textContent=num(w5.delta,0);$("delta30").textContent=num(w30.delta,0);$("delta60").textContent=num(w60.delta,0);$("cvd").textContent=num(ms.cvd,0);$("ret5").textContent=num(p5.return_pct,3)+"%";$("avgTrade").textContent=num(w5.avg_trade_size,2);$("flowSide").textContent=(m.last_trade_side||"—").toUpperCase();
  $("fv").textContent=num(f.fisher,5);$("tv").textContent=num(f.trigger,5);$("fc").textContent=f.bullish_cross?"YES":"NO";
  $("trades").textContent=v.trades??"—";$("winRate").textContent=v.win_rate==null?"—":num(v.win_rate*100,1)+"%";$("expectancy").textContent=v.expectancy_bps==null?"—":num(v.expectancy_bps,2)+" bps";$("pf").textContent=v.profit_factor==null?"—":num(v.profit_factor,2);$("netUsd").textContent=v.sum_net_usd==null?"—":num(v.sum_net_usd,4);$("levelBlocks").textContent=v.level_blocks??"—";$("paperStatus").textContent=v.status||"PAPER_ONLY";
  $("liveMode").textContent=g.locked===false&&g.eligible?"ELIGIBLE*":"LOCKED";$("gate").textContent=g.locked===false&&g.eligible?"Live gate eligible — operator approval still required.":"Live execution locked: "+((g.missing_requirements||[]).join(", ")||"paper-only policy");
  $("updated").textContent=m.updated_at?new Date(m.updated_at*1000).toLocaleTimeString():"—";$("candleInfo").textContent=(x.candles||[]).length+" candles";
  $("system").textContent=h.status==="OK"?"Market feed, collector, dashboard and paper engine checks are healthy.":"Platform degraded. Review health checks before relying on signals.";
 }catch(e){$("health").textContent="OFFLINE";$("system").textContent="Dashboard API unavailable."}
}
if("serviceWorker"in navigator)navigator.serviceWorker.register("/service-worker.js").catch(()=>{});addEventListener("resize",load);load();setInterval(load,1000);